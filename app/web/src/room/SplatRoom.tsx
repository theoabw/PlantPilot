import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { PLYLoader } from 'three/examples/jsm/loaders/PLYLoader.js'
import { SparkRenderer, SplatFileType, SplatMesh } from '@sparkjsdev/spark'
import { CLASS_COLOURS, STATE_COLOURS, upVector } from './api'
import { boxSplatFilter } from './boxSplatFilter'
import { cameraGridClearance, cameraGridIsFree } from './cameraGrid'
import { followCameraGoal, FollowOrbitInput } from './followOrbit'
import { stableHalfDepthShader } from './depthSplatShader'
import { nextRenderScale } from './renderScale'
import { draggedSincePress, splatOcclusionEnabled, isPickable, nestedPick, visiblePick } from './pickObject'
import { heightSplatFilter } from './heightSplatFilter'
import { topDownPose } from './topDownPose'
import { selectionSplatEdit } from './selectionSplatEdit'
import type { RoomCamera, RoomObject, RoomRoute } from './api'
import { boundedStep, CAMERA_FAST_SPEED_M_S, CAMERA_MAX_SPEED_M_S, cappedStep, headingFromTangent, easeFollowOffset, joinRouteToRobot, nearestAlongPolyline, remapAlong, sightClear, slideStep, turnHeading } from './routeMotion'

export type TripState = {
  mode: 'idle' | 'moving' | 'arrived'
  travelled: number
  total: number
}

type Motion = {
  active: boolean
  travelled: number
  total: number
  points: THREE.Vector3[]
  cumulative: number[]
  curve: THREE.CatmullRomCurve3 | null
  heading: number | null
  arrow: THREE.InstancedMesh | null
  arrowOffset: number
  arrowSpacing: number
  robot: THREE.Group | null
  reached: boolean
  faceHeading: number | null
  // Arc length along the curve at each vertex, next to `cumulative` (polyline
  // metres), and where the planner's own metres start on that polyline.
  arcAtVertex: number[]
  plannedFromM: number
}

type WalkMask = {
  x0: number
  z0: number
  cell_m: number
  rows: number
  cols: number
  axes: [number, number]
  bits: Uint8Array
}

type Props = {
  objects: RoomObject[]
  frameObjects: RoomObject[]
  selectedLabel: string
  frameKey: string
  subtle: boolean
  upAxis: string | undefined
  floorHeight: number | null
  resetToken: number
  topDownToken: number
  heightCutoff: number | null
  characterResetToken: number
  characterStart: [number, number, number] | null
  selectedId: string | null
  mappedIds: string[]
  targetId: string | null
  targetPoint: [number, number, number] | null
  cameraPose: RoomCamera | null
  maxSplats: number
  splatUrl: string
  filterUrl: string | null
  contourUrl: string | null
  objectOverlayUrl: string | null
  showLabels: boolean
  framesVisible: boolean
  boxedSplatsOnly: boolean
  filterBoxes: RoomObject[]
  objectMode: boolean
  hideSplat: boolean
  occlusion: boolean
  explode: number
  objectAssets: { id: string; label: string; url: string; kind: 'splat' | 'mesh' }[]
  mappedFrames: { id: string; tag: string; state: string; centre: [number, number, number]; axes: [number, number, number][]; extents: [number, number, number] }[]
  showMappedFrames: boolean
  obstacleMode: boolean
  obstacles: [number, number][]
  robotPositionRef: { current: [number, number] | null }
  motionPausedRef: { current: boolean }
  arrivalCentre: [number, number, number] | null
  onPlaceObstacle: (point: [number, number]) => void
  showOccupancy: boolean
  showRoute: boolean
  frameOpacity: number
  focusTarget: { centre: [number, number, number]; radius: number } | null
  focusToken: number
  robotProfile: 'humanoid' | 'amr' | 'cargo'
  manualControl: boolean
  firstPerson: boolean
  crouchSpans: [number, number][]
  showRobot: boolean
  route: RoomRoute | null
  tripToken: number
  follow: boolean
  cameraMove: boolean
  focus: boolean
  onNearby: (ids: string[]) => void
  onTrip: (state: TripState) => void
  onSelect: (id: string) => void
}

type BoxView = {
  id: string
  lines: THREE.LineSegments
  material: THREE.LineBasicMaterial
}

function movementKey(key: string): string {
  switch (key) {
    case 'ArrowUp':
      return 'w'
    case 'ArrowLeft':
      return 'a'
    case 'ArrowDown':
      return 's'
    case 'ArrowRight':
      return 'd'
    default:
      return key.toLowerCase()
  }
}

// Surface and structure frames are room-sized and would drown the equipment,
// so they stay quiet until selected.
const QUIET_CLASSES = new Set(['surface', 'structure', 'beam'])
// Splats below this alpha are composited colour the image barely shows, so they
// must not change the depth the overlays test against. The fog and veil
// gaussians that made objects vanish in mid air sit below it, while the paint
// that actually forms a machine surface sits above it.
const DEPTH_ALPHA_CUT = 0.08
// The rubric asks for assets near the robot to be highlighted as it walks.
const NEARBY_RADIUS_M = 2.5
const SELECTED_COLOUR = 0xffffff
const TARGET_COLOUR = 0xff3030
const MAPPED_COLOUR = 0x22d3ee
const ROBOT_TRIM_COLOUR = 0x26d6bc
const ROUTE_COLOUR = 0xfbbf24
// What an overlay looks like where structure hides it: faint, so the robot and
// the route stay findable behind a machine and a false occlusion from the coarse
// splat depth reads as a dim patch instead of a hole.
const GHOST_OPACITY = 0.2
// Only fairly solid splats can hide a box from a click: the default cut of 0.2
// also catches faint floaters hanging in open air between the camera and a box.
const PICK_SURFACE_ALPHA = 0.4
// One ray over the capture takes about 60 to 200 ms on a CPU core: fine once per
// click, far too slow for hover or for labels. A machine slower than this keeps
// the plain box pick rather than a click that visibly lags.
const PICK_RAY_BUDGET_MS = 300
const ROBOT_GHOST_COLOUR = 0x7dd3fc
// After the splats' depth and colour, before every solid overlay. The solid draws
// write depth, so a ghost drawn after any of them would show through it: the
// robot's own body, or the robot standing in front of the target.
const GHOST_RENDER_ORDER = 0.5

function ghostMaterial(color: number): THREE.MeshBasicMaterial {
  return new THREE.MeshBasicMaterial({
    color,
    transparent: true,
    opacity: GHOST_OPACITY,
    depthFunc: THREE.GreaterDepth,
    depthWrite: false,
    side: THREE.DoubleSide,
  })
}

/**
 * Draw `mesh` faintly wherever the capture hides it. The ghost is a child of the
 * mesh so it follows every animation.
 */
function addGhost(mesh: THREE.Mesh, color: number): void {
  const ghost = new THREE.Mesh(mesh.geometry, ghostMaterial(color))
  ghost.renderOrder = GHOST_RENDER_ORDER
  mesh.add(ghost)
}

// The procedural humanoid reads this while animating; a single viewer instance
// owns it, so a module-level value avoids rebuilding the model on crouch changes.
let robotCrouchSpans: [number, number][] = []

function boxColour(object: RoomObject, mapped: Set<string>, targetId: string | null): number {
  if (targetId === object.id) {
    return TARGET_COLOUR
  }
  if (mapped.has(object.id)) {
    return MAPPED_COLOUR
  }
  const value = CLASS_COLOURS[object.class] ?? CLASS_COLOURS.unknown
  return new THREE.Color(value).getHex()
}

/** Distance from a scene point to an oriented box, zero inside the box. */
function distanceToBox(point: THREE.Vector3, object: RoomObject): number {
  const quaternion = boxQuaternion(object.axes)
  const local = point.clone().sub(new THREE.Vector3(...object.centre)).applyQuaternion(quaternion.clone().invert())
  const outside = new THREE.Vector3(
    Math.max(Math.abs(local.x) - object.extents[0] / 2, 0),
    Math.max(Math.abs(local.y) - object.extents[1] / 2, 0),
    Math.max(Math.abs(local.z) - object.extents[2] / 2, 0),
  )
  return outside.length()
}

function boxQuaternion(axes: [number, number, number][]): THREE.Quaternion {
  const x = new THREE.Vector3(...axes[0]).normalize()
  const y = new THREE.Vector3(...axes[1]).normalize()
  const z = new THREE.Vector3(...axes[2]).normalize()
  return new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().makeBasis(x, y, z))
}


type RobotProfile = 'humanoid' | 'amr' | 'cargo'

const firstPersonEyeHeight: Record<RobotProfile, number> = {
  humanoid: 1.2,
  amr: 0.42,
  cargo: 0.68,
}

const followTargetHeight: Record<RobotProfile, number> = {
  humanoid: 0.78,
  amr: 0.28,
  cargo: 0.45,
}

// Route points and the robot's origin sit this far above the floor.
const ROBOT_FLOOR_OFFSET_M = 0.07
// The room's overhead structure starts around 1.95 m, and the camera's obstacle
// band ends at 1.85 m: above this the band says nothing about the camera.
const CAMERA_MAX_HEIGHT_M = 1.75
// The first attempts stay near the wanted view; the later ones are closer or
// from the other side, for a robot boxed in where only one direction sees it.
const CAMERA_ATTEMPTS: [number, number, number][] = [
  [0.3, 1, 1.0], [-0.3, 1, 1.0], [0.6, 0.92, 1.15], [-0.6, 0.92, 1.15],
  [0.9, 0.8, 0.85], [-0.9, 0.8, 0.85], [1.25, 0.75, 1.1], [-1.25, 0.75, 1.1],
  [0, 0.8, 1.5], [0.45, 0.62, 0.7], [-0.45, 0.62, 0.7], [0, 0.6, 1.85],
  [1.7, 0.7, 0.9], [-1.7, 0.7, 0.9], [2.3, 0.6, 0.9], [-2.3, 0.6, 0.9],
  [Math.PI, 0.6, 0.9], [0.3, 0.5, 0.75], [-0.3, 0.5, 0.75],
]

// How much lower a fully crouched humanoid's eyes are, matching its folded body.
const CROUCH_EYE_DROP_M = 0.31
// Off the route by more than this, its crouch spans say nothing about the place.
const CROUCH_ROUTE_REACH_M = 0.6

// The orbit may look up from low down, but never swing fully under its target.
const ORBIT_MAX_POLAR_RAD = Math.PI * 0.7
const CAMERA_FLOOR_CLEARANCE_M = 0.12
// How far past the mapped floor the free camera may wander.
const FREE_CAMERA_MARGIN_M = 1

const followDistances: Record<RobotProfile, number> = {
  humanoid: 2.55,
  amr: 2.05,
  cargo: 2.35,
}

/**
 * A procedural service robot. A walking humanoid is a small industrial worker
 * (about 1.3 m after scaling), with a pelvis, two-segment legs and arms, a
 * hi-vis vest and a helmet. The wheeled AMR has a proper chassis, wheels,
 * payload deck, sensor mast and lidar. Both animate from distance travelled so
 * feet and wheels match the route speed.
 */
function buildRobot(profile: RobotProfile): THREE.Group {
  const group = buildRobotBody(profile)
  const parts: THREE.Mesh[] = []
  group.traverse((child) => {
    if (child instanceof THREE.Mesh && !child.userData.noGhost) {
      parts.push(child)
    }
  })
  for (const part of parts) {
    addGhost(part, ROBOT_GHOST_COLOUR)
  }
  return group
}

function buildRobotBody(profile: RobotProfile): THREE.Group {
  // No renderOrder on this group or on the pivots under it. three.js takes a
  // group's renderOrder as the sort key of everything below it, and the ghosts
  // only sort before the solid parts when all of them share one key.
  const group = new THREE.Group()
  group.userData.profile = profile
  const material = (color: number, opacity = 1) =>
    new THREE.MeshBasicMaterial({ color, transparent: true, opacity })
  const mesh = (geometry: THREE.BufferGeometry, color: number, opacity = 1) => {
    const part = new THREE.Mesh(geometry, material(color, opacity))
    part.renderOrder = 3
    return part
  }
  const shadow = mesh(new THREE.RingGeometry(0.2, 0.32, 36), 0x0b1220, 0.38)
  shadow.rotation.x = -Math.PI / 2
  shadow.position.y = 0.005
  shadow.userData.noGhost = true
  group.add(shadow)

  if (profile === 'humanoid') {
    const bob = new THREE.Group()
    group.add(bob)
    const HIP_Y = 0.8
    const THIGH = 0.38
    const SHIN = 0.36

    const pelvis = mesh(new THREE.BoxGeometry(0.3, 0.16, 0.2), 0x1f2937)
    pelvis.position.y = 0.88
    bob.add(pelvis)
    const belt = mesh(new THREE.BoxGeometry(0.32, 0.05, 0.22), 0x111827)
    belt.position.y = 0.98
    bob.add(belt)

    const torso = mesh(new THREE.BoxGeometry(0.33, 0.5, 0.23), 0x334155)
    torso.position.y = 1.2
    bob.add(torso)
    const vest = mesh(new THREE.BoxGeometry(0.345, 0.34, 0.245), 0xd4f22a, 0.95)
    vest.position.y = 1.22
    bob.add(vest)
    const bandLow = mesh(new THREE.BoxGeometry(0.355, 0.025, 0.255), 0xe2e8f0, 0.85)
    bandLow.position.y = 1.1
    bob.add(bandLow)
    const bandHigh = mesh(new THREE.BoxGeometry(0.355, 0.025, 0.255), 0xe2e8f0, 0.85)
    bandHigh.position.y = 1.34
    bob.add(bandHigh)
    const frontPack = mesh(new THREE.BoxGeometry(0.16, 0.1, 0.05), 0x1f2937)
    frontPack.position.set(0, 1.16, 0.145)
    bob.add(frontPack)
    const frontLight = mesh(new THREE.BoxGeometry(0.1, 0.02, 0.02), ROBOT_TRIM_COLOUR, 0.9)
    frontLight.position.set(0, 1.18, 0.175)
    bob.add(frontLight)
    const shoulders = mesh(new THREE.BoxGeometry(0.42, 0.1, 0.21), 0x475569)
    shoulders.position.y = 1.44
    bob.add(shoulders)
    const backpack = mesh(new THREE.BoxGeometry(0.26, 0.3, 0.12), 0x1e293b)
    backpack.position.set(0, 1.22, -0.17)
    bob.add(backpack)
    const packLight = mesh(new THREE.BoxGeometry(0.18, 0.035, 0.02), ROBOT_TRIM_COLOUR, 0.8)
    packLight.position.set(0, 1.24, -0.235)
    bob.add(packLight)
    const neck = mesh(new THREE.CylinderGeometry(0.05, 0.055, 0.08, 10), 0x1f2937)
    neck.position.y = 1.5
    bob.add(neck)
    const head = mesh(new THREE.SphereGeometry(0.105, 20, 16), 0xe2a679)
    head.position.y = 1.58
    head.scale.set(1, 1.05, 0.95)
    bob.add(head)
    const visor = mesh(new THREE.BoxGeometry(0.15, 0.045, 0.03), 0x0f172a, 0.95)
    visor.position.set(0, 1.59, 0.1)
    bob.add(visor)
    const visorStripe = mesh(new THREE.BoxGeometry(0.12, 0.012, 0.012), ROBOT_TRIM_COLOUR, 0.9)
    visorStripe.position.set(0, 1.6, 0.112)
    bob.add(visorStripe)
    const helmet = mesh(new THREE.CylinderGeometry(0.12, 0.12, 0.07, 20), 0xf8fafc)
    helmet.position.y = 1.66
    bob.add(helmet)
    const dome = mesh(new THREE.SphereGeometry(0.12, 20, 12, 0, Math.PI * 2, 0, Math.PI / 2), 0xf8fafc)
    dome.position.y = 1.69
    bob.add(dome)
    const brim = mesh(new THREE.BoxGeometry(0.25, 0.018, 0.09), 0xf1f5f9)
    brim.position.set(0, 1.645, 0.1)
    bob.add(brim)

    const legPivots: THREE.Group[] = []
    const kneePivots: THREE.Group[] = []
    for (const side of [-1, 1]) {
      const hip = new THREE.Group()
      hip.position.set(side * 0.1, HIP_Y, 0)
      const hipJoint = mesh(new THREE.SphereGeometry(0.062, 12, 10), 0x111827)
      hip.add(hipJoint)
      const thigh = mesh(new THREE.BoxGeometry(0.12, THIGH, 0.14), 0x1f2937)
      thigh.position.y = -THIGH / 2
      hip.add(thigh)
      const knee = new THREE.Group()
      knee.position.y = -THIGH
      const kneeCap = mesh(new THREE.SphereGeometry(0.058, 12, 10), 0x334155)
      knee.add(kneeCap)
      const shin = mesh(new THREE.BoxGeometry(0.1, SHIN + 0.04, 0.12), 0x334155)
      shin.position.y = -(SHIN + 0.04) / 2
      knee.add(shin)
      const boot = mesh(new THREE.BoxGeometry(0.13, 0.08, 0.24), 0x0f172a)
      boot.position.set(0, -SHIN + 0.02, 0.045)
      knee.add(boot)
      const sole = mesh(new THREE.BoxGeometry(0.135, 0.02, 0.25), 0x020617)
      sole.position.set(0, -SHIN - 0.02, 0.045)
      knee.add(sole)
      hip.add(knee)
      bob.add(hip)
      legPivots.push(hip)
      kneePivots.push(knee)
    }

    const armPivots: THREE.Group[] = []
    const elbowPivots: THREE.Group[] = []
    for (const side of [-1, 1]) {
      const shoulder = new THREE.Group()
      shoulder.position.set(side * 0.235, 1.4, 0)
      const shoulderCap = mesh(new THREE.SphereGeometry(0.055, 12, 10), 0x475569)
      shoulder.add(shoulderCap)
      const upper = mesh(new THREE.BoxGeometry(0.085, 0.27, 0.1), 0x334155)
      upper.position.y = -0.135
      shoulder.add(upper)
      const sleeveBand = mesh(new THREE.BoxGeometry(0.095, 0.05, 0.11), 0xd4f22a, 0.95)
      sleeveBand.position.y = -0.22
      shoulder.add(sleeveBand)
      const elbow = new THREE.Group()
      elbow.position.y = -0.285
      const elbowJoint = mesh(new THREE.SphereGeometry(0.05, 12, 10), 0x475569)
      elbow.add(elbowJoint)
      const fore = mesh(new THREE.BoxGeometry(0.078, 0.26, 0.092), 0x475569)
      fore.position.y = -0.135
      elbow.add(fore)
      const cuff = mesh(new THREE.BoxGeometry(0.082, 0.03, 0.096), 0x0f172a)
      cuff.position.y = -0.25
      elbow.add(cuff)
      const hand = mesh(new THREE.BoxGeometry(0.075, 0.09, 0.07), 0x0f172a)
      hand.position.y = -0.29
      elbow.add(hand)
      shoulder.add(elbow)
      bob.add(shoulder)
      armPivots.push(shoulder)
      elbowPivots.push(elbow)
    }

    // About 1.34 m standing. Crouched routes fold the body to roughly 1.0 m,
    // matching the height the planner used for them.
    group.scale.setScalar(0.79)
    let crouch = 0

    group.userData.crouch = 0
    group.userData.animate = (_time: number, travelled: number, moving: boolean, spanAt = -1) => {
      const withinSpan = robotCrouchSpans.some(
        ([from, to]) => spanAt >= from - 0.12 && spanAt <= to + 0.12,
      )
      const wantCrouch = withinSpan ? 1 : 0
      crouch += (wantCrouch - crouch) * 0.22
      group.userData.crouch = crouch
      const phase = travelled * 3.9
      const swing = moving ? 0.55 : 0
      legPivots[0].rotation.x = Math.sin(phase) * swing + crouch * 0.35
      legPivots[1].rotation.x = -Math.sin(phase) * swing + crouch * 0.35
      kneePivots[0].rotation.x = Math.max(0, -Math.sin(phase)) * swing * 1.1 + crouch * 0.7
      kneePivots[1].rotation.x = Math.max(0, Math.sin(phase)) * swing * 1.1 + crouch * 0.7
      armPivots[0].rotation.x = -Math.sin(phase) * swing * 0.75 - crouch * 0.35
      armPivots[1].rotation.x = Math.sin(phase) * swing * 0.75 - crouch * 0.35
      elbowPivots[0].rotation.x = -0.3 - Math.max(0, Math.sin(phase)) * swing * 0.45 - crouch * 0.35
      elbowPivots[1].rotation.x = -0.3 - Math.max(0, -Math.sin(phase)) * swing * 0.45 - crouch * 0.35
      // Crouched head sits near 0.89 m against a 0.95 m planned band. The extra
      // margin covers the walking bob and the helmet brim, so the head does not
      // graze the underside of a pipe the route cleared.
      bob.rotation.x = (moving ? 0.04 : 0) + crouch * 0.14
      bob.position.y = (moving ? Math.abs(Math.sin(phase)) * 0.025 * (1 - crouch * 0.8) : 0) - crouch * 0.02
      bob.scale.y = 1 - crouch * 0.34
      bob.scale.x = 1 + crouch * 0.08
      bob.scale.z = 1 + crouch * 0.08
    }
    return group
  }

  const scale = profile === 'cargo' ? 1.5 : 0.85
  const chassisWidth = 0.56
  const chassisLength = 0.84
  const wheelRadius = 0.105
  const body = new THREE.Group()
  group.add(body)

  const wheels: THREE.Group[] = []
  for (const side of [-1, 1]) {
    for (const end of [-1, 1]) {
      const hub = new THREE.Group()
      hub.position.set(side * (chassisWidth / 2 + 0.02), wheelRadius, end * (chassisLength / 2 - 0.16))
      const tyre = mesh(new THREE.CylinderGeometry(wheelRadius, wheelRadius, 0.06, 18), 0x0f172a)
      tyre.rotation.z = Math.PI / 2
      hub.add(tyre)
      const rim = mesh(new THREE.CylinderGeometry(wheelRadius * 0.55, wheelRadius * 0.55, 0.065, 14), 0x64748b)
      rim.rotation.z = Math.PI / 2
      hub.add(rim)
      body.add(hub)
      wheels.push(hub)
    }
  }

  const skirt = mesh(new THREE.BoxGeometry(chassisWidth + 0.02, 0.06, chassisLength + 0.02), 0x111827)
  skirt.position.y = 0.08
  body.add(skirt)
  const lower = mesh(new THREE.BoxGeometry(chassisWidth, 0.16, chassisLength), 0x1f2937)
  lower.position.y = 0.2
  body.add(lower)
  const upper = mesh(new THREE.BoxGeometry(chassisWidth - 0.03, 0.14, chassisLength - 0.04), 0x334155)
  upper.position.y = 0.34
  body.add(upper)
  const deck = mesh(new THREE.BoxGeometry(chassisWidth + 0.04, 0.05, chassisLength + 0.04), 0x475569)
  deck.position.y = 0.43
  body.add(deck)
  for (const side of [-1, 1]) {
    const bumperFront = mesh(new THREE.BoxGeometry(0.1, 0.12, 0.07), 0x0b1220)
    bumperFront.position.set(side * (chassisWidth / 2 - 0.03), 0.17, chassisLength / 2 + 0.02)
    body.add(bumperFront)
    const bumperBack = mesh(new THREE.BoxGeometry(0.1, 0.12, 0.07), 0x0b1220)
    bumperBack.position.set(side * (chassisWidth / 2 - 0.03), 0.17, -chassisLength / 2 - 0.02)
    body.add(bumperBack)
    const sideStrip = mesh(new THREE.BoxGeometry(0.015, 0.04, chassisLength * 0.55), ROBOT_TRIM_COLOUR, 0.7)
    sideStrip.position.set(side * (chassisWidth / 2 + 0.005), 0.26, 0)
    body.add(sideStrip)
    const rail = mesh(new THREE.BoxGeometry(0.04, 0.03, chassisLength - 0.12), 0x64748b)
    rail.position.set(side * (chassisWidth / 2 - 0.06), 0.47, 0)
    body.add(rail)
  }
  for (const end of [-1, 1]) {
    const roller = mesh(new THREE.CylinderGeometry(0.025, 0.025, chassisWidth - 0.14, 10), 0x94a3b8)
    roller.rotation.z = Math.PI / 2
    roller.position.set(0, 0.47, end * (chassisLength / 2 - 0.18))
    body.add(roller)
  }
  const frontBar = mesh(new THREE.BoxGeometry(0.34, 0.05, 0.03), 0x0f172a)
  frontBar.position.set(0, 0.3, chassisLength / 2 + 0.01)
  body.add(frontBar)
  for (const side of [-1, 1]) {
    const lamp = mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.02, 12), ROBOT_TRIM_COLOUR, 0.95)
    lamp.rotation.x = Math.PI / 2
    lamp.position.set(side * 0.16, 0.3, chassisLength / 2 + 0.02)
    body.add(lamp)
  }
  const rearBar = mesh(new THREE.BoxGeometry(0.3, 0.04, 0.02), 0x991b1b, 0.85)
  rearBar.position.set(0, 0.3, -chassisLength / 2 - 0.02)
  body.add(rearBar)

  const mast = new THREE.Group()
  mast.position.set(-chassisWidth / 2 + 0.11, 0.43, 0)
  const mastPole = mesh(new THREE.CylinderGeometry(0.03, 0.04, 0.32, 10), 0x64748b)
  mastPole.position.y = 0.16
  mast.add(mastPole)
  const mastBase = mesh(new THREE.CylinderGeometry(0.07, 0.075, 0.04, 16), 0x334155)
  mastBase.position.y = 0.33
  mast.add(mastBase)
  const lidar = new THREE.Group()
  lidar.position.y = 0.38
  const lidarBand = mesh(new THREE.CylinderGeometry(0.075, 0.075, 0.05, 18), 0x0b1220)
  lidar.add(lidarBand)
  const lidarGlass = mesh(new THREE.CylinderGeometry(0.077, 0.077, 0.022, 18), ROBOT_TRIM_COLOUR, 0.8)
  lidarGlass.position.y = 0.01
  lidar.add(lidarGlass)
  const lidarCap = mesh(new THREE.CylinderGeometry(0.07, 0.07, 0.03, 18), 0x475569)
  lidarCap.position.y = 0.04
  lidar.add(lidarCap)
  mast.add(lidar)
  body.add(mast)

  const cameraBar = mesh(new THREE.BoxGeometry(0.22, 0.055, 0.05), 0x0f172a)
  cameraBar.position.set(0.12, 0.55, -0.18)
  body.add(cameraBar)
  for (const side of [-1, 1]) {
    const lens = mesh(new THREE.CylinderGeometry(0.018, 0.018, 0.03, 10), ROBOT_TRIM_COLOUR, 0.9)
    lens.rotation.x = Math.PI / 2
    lens.position.set(0.12 + side * 0.06, 0.55, -0.15)
    body.add(lens)
  }
  const antenna = new THREE.Group()
  antenna.position.set(0.18, 0.47, -chassisLength / 2 + 0.12)
  const antennaPole = mesh(new THREE.CylinderGeometry(0.008, 0.008, 0.4, 6), 0x64748b)
  antennaPole.position.y = 0.2
  antenna.add(antennaPole)
  const antennaTip = mesh(new THREE.SphereGeometry(0.025, 10, 8), 0xf59e0b, 0.95)
  antennaTip.position.y = 0.42
  antenna.add(antennaTip)
  body.add(antenna)
  const estop = mesh(new THREE.CylinderGeometry(0.04, 0.04, 0.03, 14), 0xdc2626, 0.95)
  estop.position.set(0.18, 0.46, 0.18)
  body.add(estop)
  const eStopRing = mesh(new THREE.CylinderGeometry(0.055, 0.055, 0.01, 14), 0xfacc15, 0.9)
  eStopRing.position.set(0.18, 0.445, 0.18)
  body.add(eStopRing)
  const plate = mesh(new THREE.BoxGeometry(0.14, 0.006, 0.1), 0xe2e8f0, 0.85)
  plate.position.set(0.02, 0.46, 0.02)
  body.add(plate)

  if (profile === 'cargo') {
    const bed = mesh(new THREE.BoxGeometry(chassisWidth + 0.06, 0.06, chassisLength + 0.02), 0x1e293b)
    bed.position.y = 0.49
    body.add(bed)
    const crate = mesh(new THREE.BoxGeometry(0.42, 0.3, 0.44), 0xb45309)
    crate.position.y = 0.67
    body.add(crate)
    const crateBand = mesh(new THREE.BoxGeometry(0.43, 0.04, 0.45), 0xf59e0b, 0.9)
    crateBand.position.y = 0.63
    body.add(crateBand)
  }

  group.scale.setScalar(scale)

  group.userData.animate = (time: number, travelled: number, moving: boolean) => {
    for (const hub of wheels) {
      hub.rotation.x = travelled / (wheelRadius * scale)
    }
    lidar.rotation.y = time * 2.4
    const blink = moving ? 0.55 + 0.45 * Math.abs(Math.sin(time * 3)) : 0.6
    ;(antennaTip.material as THREE.MeshBasicMaterial).opacity = blink
  }
  return group
}

// The view counts as still once nothing has drawn for this long, and the frame
// time is averaged over this window before the moving resolution changes.
const SHARPEN_AFTER_MS = 400
const SCALE_WINDOW_MS = 400

export default function SplatRoom({ objects, frameObjects, selectedLabel, frameKey, subtle, upAxis, floorHeight, resetToken, topDownToken, heightCutoff, characterResetToken, characterStart, selectedId, mappedIds, targetId, targetPoint, cameraPose, maxSplats, splatUrl, filterUrl, contourUrl, objectOverlayUrl, showLabels, framesVisible, boxedSplatsOnly, filterBoxes, objectMode, hideSplat, occlusion, explode, objectAssets, mappedFrames, showMappedFrames, obstacleMode, obstacles, robotPositionRef, motionPausedRef, arrivalCentre, onPlaceObstacle, showOccupancy, showRoute, frameOpacity, focusTarget, focusToken, robotProfile, manualControl, firstPerson, crouchSpans, showRobot, route, tripToken, follow, cameraMove, focus, onNearby, onTrip, onSelect }: Props) {
  const hostRef = useRef<HTMLDivElement | null>(null)
  const [glError, setGlError] = useState<string | null>(null)
  robotCrouchSpans = crouchSpans
  const [progress, setProgress] = useState(0)
  const [loaded, setLoaded] = useState(false)
  const [perf, setPerf] = useState<{ draws: number; ms: number; calls: number; splats: number } | null>(null)
  const perfEnabled = useRef(new URLSearchParams(window.location.search).has('perf')).current
  // Effects outside the render effect need a way to say "the scene changed".
  const renderRef = useRef<() => void>(() => undefined)
  const stateRef = useRef<{
    renderer: THREE.WebGLRenderer
    scene: THREE.Scene
    camera: THREE.PerspectiveCamera
    controls: OrbitControls
    world: THREE.Group
    splat: SplatMesh | null
    splatUrl: string
    contours: THREE.Points | null
    overlay: SplatMesh | null
    objectGroup: THREE.Group
    meshGroups: Map<string, { group: THREE.Group; index: number }>
    obstacleGroup: THREE.Group
    occupancy: THREE.InstancedMesh | null
    decorGroup: THREE.Group | null
    depthSplats: THREE.Mesh | null
    mappedGroup: THREE.Group | null
    placeRobotAt: ((dt: number) => void) | null
    updateArrows: (() => void) | null
    focusTween: {
      start: number
      duration: number
      fromPosition: THREE.Vector3
      toPosition: THREE.Vector3
      fromTarget: THREE.Vector3
      toTarget: THREE.Vector3
    } | null
    cameraMask: {
      x0: number
      z0: number
      cell_m: number
      rows: number
      cols: number
      axes: [number, number]
      bits: Uint8Array
    } | null
    safeCameraPosition: ((desired: THREE.Vector3, focus: THREE.Vector3) => THREE.Vector3) | null
    cameraFree: ((world: THREE.Vector3, marginM?: number) => boolean) | null
    stickyCamera: THREE.Vector3 | null
    smoothedCamera: THREE.Vector3 | null
    followTransitionStart: number
    cameraBlockedSince: number | null
    boxGroup: THREE.Group
    pickGroup: THREE.Group
    boxes: BoxView[]
    routeGroup: THREE.Group
    beaconGroup: THREE.Group
    motion: Motion
    follow: boolean
    followOffset: THREE.Vector3 | null
    followOffsetFromUser: boolean
    followOrbit: FollowOrbitInput
    cameraMove: boolean
    movementKeys: Set<string>
    manualControl: boolean
    firstPerson: boolean
    manualYaw: number
    manualPitch: number
    manualTravelled: number
    pointerLookActive: boolean
    lastPointerX: number
    lastPointerY: number
    walkMask: WalkMask | null
    cameraFloorY: number | null
    centre: THREE.Vector3
    radius: number
  } | null>(null)
  const selectedRef = useRef(selectedId)
  selectedRef.current = selectedId
  const objectsRef = useRef(objects)
  objectsRef.current = objects
  const mappedRef = useRef(mappedIds)
  mappedRef.current = mappedIds
  const targetRef = useRef(targetId)
  targetRef.current = targetId
  const focusRef = useRef(focus)
  focusRef.current = focus
  const selectRef = useRef(onSelect)
  selectRef.current = onSelect
  const tripRef = useRef(onTrip)
  tripRef.current = onTrip
  const followRef = useRef(follow)
  followRef.current = follow
  const cameraMoveRef = useRef(cameraMove)
  cameraMoveRef.current = cameraMove
  const manualControlRef = useRef(manualControl)
  manualControlRef.current = manualControl
  const arrivalCentreRef = useRef(arrivalCentre)
  arrivalCentreRef.current = arrivalCentre
  const robotProfileRef = useRef(robotProfile)
  robotProfileRef.current = robotProfile
  const firstPersonRef = useRef(firstPerson)
  firstPersonRef.current = firstPerson
  const initialRobotTransformRef = useRef<{
    position: THREE.Vector3
    heading: number
  } | null>(null)
  const nearbyRef = useRef(onNearby)
  nearbyRef.current = onNearby
  // The framed camera is kept so the toolbar's overview and reset can restore it.
  const frameRef = useRef<{ eye: THREE.Vector3; target: THREE.Vector3 } | null>(null)
  const heightCutoffRef = useRef(heightCutoff)
  heightCutoffRef.current = heightCutoff
  // Switching between validated assets and raw detections rebuilds the boxes;
  // it must not move the camera, so the last framed capture is remembered.
  const framedKeyRef = useRef<string>('')
  const labelRef = useRef<HTMLDivElement | null>(null)
  const beaconWorldRef = useRef<THREE.Vector3 | null>(null)
  const labelsRef = useRef<HTMLDivElement | null>(null)
  const showLabelsRef = useRef(showLabels)
  showLabelsRef.current = showLabels
  const objectModeRef = useRef(objectMode)
  objectModeRef.current = objectMode
  const obstacleModeRef = useRef(obstacleMode)
  obstacleModeRef.current = obstacleMode
  const placeObstacleRef = useRef(onPlaceObstacle)
  placeObstacleRef.current = onPlaceObstacle
  const explodeRef = useRef(explode)
  explodeRef.current = explode
  const boxedSplatsOnlyRef = useRef(boxedSplatsOnly)
  boxedSplatsOnlyRef.current = boxedSplatsOnly

  // One effect owns the canvas and the render loop; the others only add content.
  useEffect(() => {
    const host = hostRef.current
    if (!host) {
      return
    }
    let renderer: THREE.WebGLRenderer
    try {
      renderer = new THREE.WebGLRenderer({ antialias: false })
    } catch (problem) {
      setGlError(problem instanceof Error ? problem.message : String(problem))
      return
    }
    // The splat pass is fill bound, and a 2x ratio on a large canvas is four
    // times the fragments of 1x. Cap it by canvas area rather than globally.
    // While the view moves, a slow GPU draws fewer pixels (see nextRenderScale);
    // the still image always goes back to the full ratio.
    let movingScale = 1
    let drawnSharp = true
    const clampPixelRatio = () => {
      const pixels = host.clientWidth * host.clientHeight * window.devicePixelRatio ** 2
      const cap = pixels > 3_000_000 ? 1.25 : 1.75
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, cap) * (drawnSharp ? 1 : movingScale))
    }
    clampPixelRatio()
    renderer.setSize(host.clientWidth, host.clientHeight)
    renderer.setClearColor(0x05070d, 1)
    host.appendChild(renderer.domElement)

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(60, host.clientWidth / host.clientHeight, 0.05, 500)
    camera.position.set(4, 1.6, 4)
    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    // The default tail sends tiny changes for seconds after a drag, and each one
    // redraws every splat and delays the sharp still image.
    controls.dampingFactor = 0.15
    controls.minDistance = 0.4
    controls.maxDistance = 80
    controls.maxPolarAngle = ORBIT_MAX_POLAR_RAD

    let needsRender = true
    let warmupUntil = performance.now() + 2_500
    const requestRender = () => {
      needsRender = true
    }
    renderRef.current = requestRender

    const world = new THREE.Group()
    scene.add(world)
    const objectGroup = new THREE.Group()
    objectGroup.name = 'objects'
    world.add(objectGroup)
    const obstacleGroup = new THREE.Group()
    world.add(obstacleGroup)
    // Faint proposal frames for every Excel record that was mapped to a raw
    // object, so the demo shows the full mapping without calling them reviewed.
    const mappedGroup = new THREE.Group()
    scene.add(mappedGroup)
    // the splat needs no lights, the extracted meshes do
    scene.add(new THREE.HemisphereLight(0xf2f6ff, 0x1b2430, 1.1))
    const keyLight = new THREE.DirectionalLight(0xffffff, 1.25)
    keyLight.position.set(4, 6, 3)
    scene.add(keyLight)

    let spark: SparkRenderer | null = null
    let depthSplats: THREE.Mesh | null = null
    try {
      spark = new SparkRenderer({
        renderer,
        // Performance knobs. The defaults grow splats to a 512 px radius and
        // re-sort every frame; the capture's metre-wide gaussians are the main
        // source of overdraw. Each sort makes the main thread wait for the GPU to
        // read distances back, and 6 sorts a second still reads as smooth.
        maxStdDev: Math.sqrt(4),
        maxPixelRadius: 192,
        minAlpha: 0.01,
        minSortIntervalMs: 150,
        // The colour pass is unchanged painter's order: no depth test, no depth
        // write, so the splat image is exactly the one this viewer drew before.
        // Depth for occlusion comes from a second, colourless draw below.
        depthTest: false,
        depthWrite: false,
        onDirty: requestRender,
      })
      // Spark caps the splats it accumulates (2^19 by default); a capture above
      // that budget would silently render only part of the room.
      if (maxSplats > 0) {
        spark.maxSplats = maxSplats
      }
      // Draw the splats first, so every ordinary mesh in the scene (the robot,
      // the route line, the object frames) depth-tests against them and stays
      // visible. Drawn in the default order the splat pass covers them.
      spark.renderOrder = -1
      scene.add(spark)

      // Depth pass. The overlays need the distance of the surface the image
      // shows, and the alpha-blended colour pass cannot provide it: it blends
      // back to front and writes no depth. This is the same accumulated splats
      // drawn again before the colour pass with colour writes off and a much
      // higher opacity cut, so only splats that actually paint the picture
      // reach the depth buffer. A faint veil of large, low-alpha gaussians is
      // not a surface: under the colour pass' cut (0.01) it writes depth across
      // a wide footprint and punches invisible holes in anything behind it,
      // which is why the cut here is high. The draw shares the accumulation and
      // geometry with the SparkRenderer and refreshes Spark's per-frame uniforms
      // itself, because it runs first.
      //
      // It is fill bound like the colour pass, so it draws every second splat,
      // always the same ones (see stableHalfDepthShader), at half the fill.
      const stableDepthShader = stableHalfDepthShader(spark.material.vertexShader)
      if (!stableDepthShader) {
        console.warn('depth pass: the splat shader lookup moved, drawing every splat')
      }
      const depthVertexShader = stableDepthShader ?? spark.material.vertexShader
      const depthMaterial = new THREE.ShaderMaterial({
        glslVersion: THREE.GLSL3,
        vertexShader: depthVertexShader,
        fragmentShader: spark.material.fragmentShader,
        uniforms: { ...spark.uniforms, minAlpha: { value: DEPTH_ALPHA_CUT } },
        premultipliedAlpha: true,
        transparent: true,
        depthTest: true,
        depthWrite: true,
        colorWrite: false,
        side: THREE.DoubleSide,
      })
      // GL only updates depth while the depth test runs. Always pass: the
      // splats are already drawn in radial order, and a normal test would reject
      // splats whose centres sit farther than a neighbour drawn first.
      depthMaterial.depthFunc = THREE.AlwaysDepth
      const depthMesh = new THREE.Mesh(spark.geometry, depthMaterial)
      depthMesh.frustumCulled = false
      depthMesh.renderOrder = -2
      depthMesh.onBeforeRender = (target, render, camera) => {
        spark?.onBeforeRender(target, render, camera)
      }
      scene.add(depthMesh)
      depthSplats = depthMesh
    } catch (problem) {
      setGlError(problem instanceof Error ? problem.message : String(problem))
    }

    let splat: SplatMesh | null = null
    if (spark) {
      splat = new SplatMesh({
        // The API route has no file extension, so the format is declared here
        // rather than guessed from the URL.
        url: splatUrl,
        fileType: SplatFileType.PLY,
        minRaycastOpacity: PICK_SURFACE_ALPHA,
        onProgress: (event: ProgressEvent) => {
          if (event.lengthComputable && event.total > 0) {
            setProgress(Math.round((event.loaded / event.total) * 100))
          }
        },
        onLoad: () => setLoaded(true),
      })
      splat.initialized
        .then(() => {
          setLoaded(true)
          warmupUntil = performance.now() + 2_500
          requestRender()
          // Paint a few frames once the capture is ready. requestAnimationFrame
          // is throttled when the tab is in the background, and the room should
          // not be blank the first time someone looks at it.
          let tries = 0
          const paint = () => {
            requestRender()
            renderer.render(scene, camera)
            tries += 1
            if (tries < 6) {
              window.setTimeout(paint, 400)
            }
          }
          paint()
        })
        .catch((problem: unknown) => {
          setGlError(problem instanceof Error ? problem.message : String(problem))
        })
      splat.rotation.set(0, 0, 0)
      world.add(splat)
    }

    const boxGroup = new THREE.Group()
    world.add(boxGroup)
    const pickGroup = new THREE.Group()
    world.add(pickGroup)
    const routeGroup = new THREE.Group()
    scene.add(routeGroup)
    const beaconGroup = new THREE.Group()
    scene.add(beaconGroup)

    const raycaster = new THREE.Raycaster()
    const pointer = new THREE.Vector2()
    let hoveredBox: { material: THREE.LineBasicMaterial; opacity: number; color: number } | null = null
    const clearHover = () => {
      if (hoveredBox) {
        hoveredBox.material.opacity = hoveredBox.opacity
        hoveredBox.material.color.setHex(hoveredBox.color)
        hoveredBox = null
        requestRender()
      }
    }
    const onPointerMove = (event: PointerEvent) => {
      if (pressed?.pointerId === event.pointerId) {
        pressed.dragged = draggedSincePress(pressed, { x: event.clientX, y: event.clientY })
      }
      const liveState = stateRef.current
      if (liveState?.pointerLookActive && liveState.firstPerson) {
        liveState.manualYaw -= (event.clientX - liveState.lastPointerX) * 0.004
        liveState.manualPitch = THREE.MathUtils.clamp(
          liveState.manualPitch - (event.clientY - liveState.lastPointerY) * 0.004,
          -1.35,
          1.35,
        )
        liveState.lastPointerX = event.clientX
        liveState.lastPointerY = event.clientY
        requestRender()
      }
      if (!liveState || !liveState.boxGroup.visible) {
        return
      }
      const rect = renderer.domElement.getBoundingClientRect()
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1
      raycaster.setFromCamera(pointer, camera)
      const hit = nestedPick(raycaster.intersectObjects(pickGroup.children, false))
      const id = hit?.object.userData.objectId
      const box = typeof id === 'string' ? liveState.boxes.find((entry) => entry.id === id) : undefined
      if (box && hoveredBox?.material !== box.material) {
        clearHover()
        hoveredBox = { material: box.material, opacity: box.material.opacity, color: box.material.color.getHex() }
        box.material.color.setHex(0x7dd3fc)
        box.material.opacity = Math.max(0.9, box.material.opacity)
        requestRender()
      } else if (!box) {
        clearHover()
      }
    }
    const onPointerLeave = () => clearHover()
    const stopPointerLook = () => {
      if (stateRef.current) {
        stateRef.current.pointerLookActive = false
      }
    }
    renderer.domElement.addEventListener('pointermove', onPointerMove)
    renderer.domElement.addEventListener('pointerleave', onPointerLeave)
    renderer.domElement.addEventListener('pointerup', stopPointerLook)
    renderer.domElement.addEventListener('pointercancel', stopPointerLook)
    // Selection waits for the release: a press can start an orbit, and selecting
    // on it would rebuild the highlight for every drag that begins over an object.
    let pressed: { x: number; y: number; pointerId: number; dragged: boolean } | null = null
    let splatPickAllowed = true
    // The source splats include what a filter hides on screen, so the test only
    // applies while the whole capture is drawn.
    const splatRayDistances = (): number[] => {
      const liveSplat = stateRef.current?.splat
      if (!splatPickAllowed || !liveSplat?.visible || !splatOcclusionEnabled(boxedSplatsOnlyRef.current, heightCutoffRef.current)) {
        return []
      }
      const started = performance.now()
      const crossed: THREE.Intersection[] = []
      liveSplat.raycast(raycaster, crossed)
      if (performance.now() - started > PICK_RAY_BUDGET_MS) {
        splatPickAllowed = false
      }
      return crossed.map((entry) => entry.distance)
    }
    const onPointerDown = (event: PointerEvent) => {
      const current = stateRef.current
      if (current?.manualControl && current.firstPerson) {
        current.pointerLookActive = true
        current.lastPointerX = event.clientX
        current.lastPointerY = event.clientY
        renderer.domElement.setPointerCapture(event.pointerId)
        event.preventDefault()
        return
      }
      pressed = { x: event.clientX, y: event.clientY, pointerId: event.pointerId, dragged: false }
    }
    const onPointerCancel = () => {
      pressed = null
    }
    const onPointerUp = (event: PointerEvent) => {
      const press = pressed
      pressed = null
      if (
        !press
        || press.pointerId !== event.pointerId
        || draggedSincePress(press, { x: event.clientX, y: event.clientY })
      ) {
        return
      }
      const rect = renderer.domElement.getBoundingClientRect()
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1
      raycaster.setFromCamera(pointer, camera)
      const liveState = stateRef.current
      if (obstacleModeRef.current && liveState) {
        const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -(floorHeight ?? 0))
        const hitPoint = new THREE.Vector3()
        if (raycaster.ray.intersectPlane(plane, hitPoint)) {
          const scenePoint = hitPoint.clone().applyQuaternion(liveState.world.quaternion.clone().invert())
          const upAxisName = (upAxis ?? '+y').replace(/[+-]/, '')
          const upIndex = upAxisName === 'z' ? 2 : 1
          const horizontal = [0, 1, 2].filter((axis) => axis !== upIndex)
          placeObstacleRef.current([scenePoint.getComponent(horizontal[0]), scenePoint.getComponent(horizontal[1])])
          return
        }
      }
      if (objectModeRef.current && liveState) {
        const meshHit = raycaster.intersectObjects(liveState.objectGroup.children, true)[0]
        const meshId = meshHit?.object.userData.objectId
        if (typeof meshId === 'string') {
          selectRef.current(meshId)
          return
        }
      }
      // A hidden frame is not on screen to point at.
      if (!liveState?.boxGroup.visible) {
        return
      }
      // A frame behind a wall is hidden by the depth test, so its click is too.
      const hit = visiblePick(raycaster.intersectObjects(pickGroup.children, false), splatRayDistances)
      const id = hit?.object.userData.objectId
      if (typeof id === 'string') {
        selectRef.current(id)
      }
    }
    renderer.domElement.addEventListener('pointerdown', onPointerDown)
    renderer.domElement.addEventListener('pointerup', onPointerUp)
    renderer.domElement.addEventListener('pointercancel', onPointerCancel)
    const followOrbit = new FollowOrbitInput()
    const noteOrbitStart = () => {
      const state = stateRef.current
      if (state?.follow) {
        followOrbit.start()
      }
    }
    const noteOrbitEnd = () => {
      followOrbit.end()
    }
    const captureOrbit = () => {
      const state = stateRef.current
      if (!state?.follow) return
      state.followOffset = camera.position.clone().sub(controls.target)
      state.followOffsetFromUser = true
      state.smoothedCamera = camera.position.clone()
    }
    const onControlsChange = () => {
      requestRender()
      if (followOrbit.isInputChange()) captureOrbit()
    }
    controls.addEventListener('start', noteOrbitStart)
    controls.addEventListener('end', noteOrbitEnd)
    controls.addEventListener('change', onControlsChange)
    const onCameraKeyDown = (event: KeyboardEvent) => {
      if (
        (!cameraMoveRef.current && !manualControlRef.current)
        || event.altKey
        || event.metaKey
      ) {
        return
      }
      const target = event.target
      if (
        target instanceof HTMLElement
        && target.closest('input, textarea, select, [contenteditable="true"]')
      ) {
        return
      }
      const key = movementKey(event.key)
      // Allow w/a/s/d for horizontal movement, space/control for vertical in camera mode
      const allowedKeys = cameraMoveRef.current
        ? ['w', 'a', 's', 'd', ' ', 'control']
        : ['w', 'a', 's', 'd']
      if (!allowedKeys.includes(key)) {
        return
      }
      event.preventDefault()
      stateRef.current?.movementKeys.add(key)
      renderRef.current()
    }
    const onCameraKeyUp = (event: KeyboardEvent) => {
      stateRef.current?.movementKeys.delete(movementKey(event.key))
    }
    const clearCameraKeys = () => stateRef.current?.movementKeys.clear()
    window.addEventListener('keydown', onCameraKeyDown)
    window.addEventListener('keyup', onCameraKeyUp)
    window.addEventListener('blur', clearCameraKeys)

    const up = new THREE.Vector3(0, 1, 0)
    const robotForward = new THREE.Vector3()
    const smoothFactor = (rate: number, dt: number) => 1 - Math.exp(-rate * dt)
    const updateArrowTrail = () => {
      const motion = stateRef.current?.motion
      if (!motion?.curve || !motion.arrow) {
        return
      }
      const count = motion.arrow.count
      const total = Math.max(0.01, motion.total)
      const tangent = new THREE.Vector3()
      const position = new THREE.Vector3()
      const quaternion = new THREE.Quaternion()
      const forward = new THREE.Vector3(0, 0, -1)
      const matrix = new THREE.Matrix4()
      const scale = new THREE.Vector3(0.4, 0.4, 0.4)
      for (let index = 0; index < count; index += 1) {
        const distance = (motion.arrowOffset + 0.3 + index * motion.arrowSpacing) % total
        const t = Math.min(0.999, Math.max(0.001, distance / total))
        motion.curve.getPointAt(t, position)
        motion.curve.getTangentAt(t, tangent)
        tangent.y = 0
        if (tangent.lengthSq() < 1e-6) {
          tangent.set(0, 0, -1)
        }
        tangent.normalize()
        quaternion.setFromUnitVectors(forward, tangent)
        position.y += 0.02
        matrix.compose(position, quaternion, scale)
        motion.arrow.setMatrixAt(index, matrix)
      }
      motion.arrow.instanceMatrix.needsUpdate = true
    }
    const placeRobot = (dt: number) => {
      const motion = stateRef.current?.motion
      if (!motion || !motion.robot || !motion.curve) {
        return
      }
      const t = Math.max(0, Math.min(1, motion.total > 0 ? motion.travelled / motion.total : 0))
      const position = motion.curve.getPointAt(t)
      const tangent = motion.curve.getTangentAt(t)
      motion.robot.position.copy(position)
      const targetHeading = headingFromTangent(tangent.x, tangent.z, motion.heading ?? motion.robot.rotation.y)
      if (motion.heading === null) {
        motion.heading = targetHeading
      } else {
        let delta = targetHeading - motion.heading
        while (delta > Math.PI) delta -= Math.PI * 2
        while (delta < -Math.PI) delta += Math.PI * 2
        motion.heading += delta * smoothFactor(9, Math.max(dt, 0.001))
      }
      motion.robot.rotation.y = motion.heading
    }
    // Camera avoidance works from the route's eye-level occupancy band, so it
    // is scene agnostic: walls, machine bodies and pipework at camera height
    // are avoided, and an escape above the robot guarantees the camera can
    // always re-enter the scene instead of being trapped outside it.
    const sceneXZOf = (world: THREE.Vector3): [number, number] | null => {
      const mask = stateRef.current?.cameraMask
      if (!mask) {
        return null
      }
      const live = stateRef.current
      if (!live) {
        return null
      }
      const scene = world.clone().applyQuaternion(live.world.quaternion.clone().invert())
      return [scene.getComponent(mask.axes[0]), scene.getComponent(mask.axes[1])]
    }
    const cellBlocked = (col: number, row: number): boolean => {
      const mask = stateRef.current?.cameraMask
      if (!mask) {
        return false
      }
      if (col < 0 || row < 0 || col >= mask.cols || row >= mask.rows) {
        return true
      }
      const index = row * mask.cols + col
      return (mask.bits[index >> 3] & (0x80 >> (index & 7))) !== 0
    }
    const cameraClearance = (world: THREE.Vector3, limit = 1.5): number => {
      const mask = stateRef.current?.cameraMask
      const xz = sceneXZOf(world)
      if (!mask || !xz) {
        return limit
      }
      return cameraGridClearance(mask, xz[0], xz[1], limit)
    }
    const cameraFree = (world: THREE.Vector3, marginM = 0.2): boolean => {
      const mask = stateRef.current?.cameraMask
      const xz = sceneXZOf(world)
      if (!mask || !xz) {
        return true
      }
      return cameraGridIsFree(mask, xz[0], xz[1], marginM)
    }
    const nearestStructure = (world: THREE.Vector3): number => {
      return cameraClearance(world)
    }
    const hasSight = (focus: THREE.Vector3, candidate: THREE.Vector3): boolean => {
      const mask = stateRef.current?.cameraMask
      if (!mask) {
        return true
      }
      const probe = new THREE.Vector3()
      return sightClear(focus, candidate, (point) => {
        const xz = sceneXZOf(probe.set(point.x, point.y, point.z))
        return xz
          ? cellBlocked(Math.floor((xz[0] - mask.x0) / mask.cell_m), Math.floor((xz[1] - mask.z0) / mask.cell_m))
          : false
      })
    }
    const safeCameraPosition = (desired: THREE.Vector3, focus: THREE.Vector3): THREE.Vector3 => {
      const state = stateRef.current
      if (!state?.cameraMask) {
        return desired
      }
      const robot = state.motion.robot
      const maxY = robot
        ? robot.position.y - ROBOT_FLOOR_OFFSET_M + CAMERA_MAX_HEIGHT_M
        : Number.POSITIVE_INFINITY
      // A user-set view may be above the automatic camera height.
      const heightFine = state.followOffsetFromUser || desired.y <= maxY
      if (
        heightFine
        && cameraFree(desired, 0.12)
        && nearestStructure(desired) > 0.25
        && (state.followOffsetFromUser || hasSight(focus, desired))
      ) {
        state.stickyCamera = desired.clone().sub(focus)
        return desired
      }
      const baseDirection = desired.clone().sub(focus)
      const length = Math.max(0.9, baseDirection.length())
      baseDirection.y = 0
      if (baseDirection.lengthSq() < 1e-5) {
        baseDirection.set(0, 0, -1)
      }
      baseDirection.normalize()
      const up = new THREE.Vector3(0, 1, 0)
      // A position that cannot see the robot only wins when no other is free.
      let best: THREE.Vector3 | null = null
      let bestScore = -Infinity
      let blind: THREE.Vector3 | null = null
      let blindScore = -Infinity
      for (const [angle, distanceScale, heightM] of CAMERA_ATTEMPTS) {
        const direction = baseDirection.clone().applyAxisAngle(up, angle)
        const horizontal = Math.max(0.85, length * distanceScale)
        const candidate = new THREE.Vector3(
          focus.x + direction.x * horizontal,
          Math.min(maxY, Math.max(focus.y + heightM, desired.y - 0.4)),
          focus.z + direction.z * horizontal,
        )
        if (!cameraFree(candidate, 0.1)) {
          continue
        }
        const score = nearestStructure(candidate) - 0.14 * Math.abs(angle) - 0.18 * (1 - distanceScale)
        if (hasSight(focus, candidate)) {
          if (score > bestScore) {
            bestScore = score
            best = candidate
          }
        } else if (score > blindScore) {
          blindScore = score
          blind = candidate
        }
      }
      const previous = state.stickyCamera ? focus.clone().add(state.stickyCamera) : null
      let chosen = best ?? blind
      // Keep the previous spot unless the new one is clearly better. Without
      // this the candidate search flips between symmetric aisle positions and
      // the camera appears to flicker while tracking.
      if (
        previous
        && previous.y <= maxY + 0.01
        && cameraFree(previous, 0.1)
        && hasSight(focus, previous)
        && (!best || nearestStructure(previous) >= bestScore - 0.2)
      ) {
        chosen = previous
      }
      if (chosen) {
        state.stickyCamera = chosen.clone().sub(focus)
        return chosen
      }
      // Nothing is free: stand over the robot, as high as the room allows.
      const escape = new THREE.Vector3(focus.x + 0.18, Math.min(maxY, focus.y + 2.35), focus.z + 0.18)
      state.stickyCamera = escape.clone().sub(focus)
      return escape
    }
    if (stateRef.current) {
      stateRef.current.safeCameraPosition = safeCameraPosition
      stateRef.current.cameraFree = cameraFree
    }

    const updateFollow = (dt: number, robotMoving: boolean) => {
      const robot = stateRef.current?.motion.robot
      if (!robot) {
        return
      }
      const heading = stateRef.current?.motion.heading ?? robot.rotation.y
      robotForward.set(0, 0, 1).applyAxisAngle(up, heading)
      const profile = robotProfileRef.current
      const lookHeight = followTargetHeight[profile]
      const distance = followDistances[profile]
      const rawDesired = robot.position
        .clone()
        .addScaledVector(robotForward, -distance)
        .add(new THREE.Vector3(0, lookHeight + 0.8, 0))
      const desiredTarget = robot.position.clone().add(new THREE.Vector3(0, lookHeight, 0))
      const state = stateRef.current
      // Drift back behind a driving robot, so it walks away from the camera
      // instead of toward it. A view the user orbited to stays, and manual walking
      // is relative to the camera, so turning the camera there would curve it.
      if (state?.followOffset && state.motion.active && !state.manualControl && !state.followOffsetFromUser) {
        const eased = easeFollowOffset(state.followOffset, rawDesired.clone().sub(desiredTarget), dt)
        state.followOffset.set(eased.x, eased.y, eased.z)
      }
      const followPosition = state?.followOffset
        ? desiredTarget.clone().add(state.followOffset)
        : safeCameraPosition(rawDesired, desiredTarget)
      const safeDesired = followCameraGoal(
        followPosition,
        state?.followOffsetFromUser ?? false,
        robotMoving,
        (position) => safeCameraPosition(position, desiredTarget),
      )
      if (state) {
        if (!state.followOffsetFromUser && (!state.followOffset || safeDesired.distanceTo(followPosition) > 0.05)) {
          state.followOffset = safeDesired.clone().sub(desiredTarget)
        }
        if (!state.smoothedCamera) {
          state.smoothedCamera = safeDesired.clone()
        } else {
          state.smoothedCamera.lerp(safeDesired, smoothFactor(7, Math.max(dt, 0.001)))
        }
      }
      const smoothed = state?.smoothedCamera ?? safeDesired
      const now = performance.now()
      const transitioning = state ? now - state.followTransitionStart < 900 : false
      const blocked = !cameraFree(camera.position, 0.12)
      if (state) {
        if (blocked) {
          if (state.cameraBlockedSince === null) {
            state.cameraBlockedSince = now
          }
        } else {
          state.cameraBlockedSince = null
        }
      }
      const blockedFor = state?.cameraBlockedSince === null || state?.cameraBlockedSince === undefined
        ? 0
        : now - state.cameraBlockedSince
      const recovery = 1 - Math.exp(-blockedFor / 700)
      const rate = transitioning ? 3.2 : 6 + 14 * recovery
      const factor = smoothFactor(rate, Math.max(dt, 0.001))
      const lerpGoal = camera.position.clone().lerp(smoothed, factor)
      const maxSpeed = transitioning
        ? CAMERA_MAX_SPEED_M_S
        : CAMERA_MAX_SPEED_M_S + (CAMERA_FAST_SPEED_M_S - CAMERA_MAX_SPEED_M_S) * recovery
      const capped = cappedStep(camera.position, lerpGoal, maxSpeed * Math.max(dt, 0.001))
      camera.position.set(capped.x, capped.y, capped.z)
      controls.target.lerp(desiredTarget, factor)
    }
    const walkCell = (worldPosition: THREE.Vector3): 'free' | 'blocked' | 'outside' => {
      const state = stateRef.current
      const mask = state?.walkMask
      if (!state || !mask) {
        return 'free'
      }
      const point = worldPosition.clone().applyQuaternion(state.world.quaternion.clone().invert())
      const col = Math.floor((point.getComponent(mask.axes[0]) - mask.x0) / mask.cell_m)
      const row = Math.floor((point.getComponent(mask.axes[1]) - mask.z0) / mask.cell_m)
      if (row < 0 || row >= mask.rows || col < 0 || col >= mask.cols) {
        return 'outside'
      }
      const index = row * mask.cols + col
      return (mask.bits[index >> 3] & (0x80 >> (index & 7))) === 0 ? 'free' : 'blocked'
    }
    // Where the character is, in the planner's metres along the route: the crouch
    // spans are in those. A driving robot converts its curve progress; a manual
    // character can be anywhere, so it goes by where it stands.
    const crouchSpanPosition = (): number => {
      const state = stateRef.current
      const motion = state?.motion
      if (!state || !motion?.robot || motion.points.length < 2) {
        return -1
      }
      if (state.manualControl) {
        const nearest = nearestAlongPolyline(motion.robot.position, motion.points, motion.cumulative)
        return nearest && nearest.off <= CROUCH_ROUTE_REACH_M ? nearest.along - motion.plannedFromM : -1
      }
      return remapAlong(motion.travelled, motion.arcAtVertex, motion.cumulative) - motion.plannedFromM
    }
    const moveManualHuman = (dt: number): boolean => {
      const state = stateRef.current
      const person = state?.motion.robot
      if (!state?.manualControl || !person || state.movementKeys.size === 0) {
        return false
      }
      const forward = camera.getWorldDirection(new THREE.Vector3())
      forward.y = 0
      if (forward.lengthSq() < 1e-5) {
        return false
      }
      forward.normalize()
      const right = new THREE.Vector3().crossVectors(forward, up).normalize()
      const direction = new THREE.Vector3()
      if (state.movementKeys.has('w')) direction.add(forward)
      if (state.movementKeys.has('s')) direction.sub(forward)
      if (state.movementKeys.has('d')) direction.add(right)
      if (state.movementKeys.has('a')) direction.sub(right)
      if (direction.lengthSq() === 0) {
        return false
      }
      direction.normalize().multiplyScalar(1.5 * dt)
      const distance = direction.length()
      const steps = Math.max(1, Math.ceil(distance / 0.05))
      const step = direction.clone().divideScalar(steps)
      const probe = person.position.clone()
      const cellAt = (point: { x: number; z: number }) => walkCell(probe.set(point.x, person.position.y, point.z))
      let moved = 0
      for (let index = 0; index < steps; index += 1) {
        const from = { x: person.position.x, z: person.position.z }
        const next = slideStep(
          from,
          { x: step.x, z: step.z },
          (point) => cellAt(point) === 'free',
          (point) => cellAt(point) !== 'outside',
        )
        if (!next) {
          break
        }
        person.position.x = next.x
        person.position.z = next.z
        moved += Math.hypot(next.x - from.x, next.z - from.z)
      }
      if (moved === 0) {
        return false
      }
      state.manualTravelled += moved
      const heading = Math.atan2(direction.x, direction.z)
      person.rotation.y = heading
      state.motion.heading = heading
      const animate = person.userData.animate as
        | ((time: number, travelled: number, moving: boolean, spanAt?: number) => void)
        | undefined
      animate?.(performance.now() / 1000, state.manualTravelled, true, crouchSpanPosition())
      const scenePosition = person.position
        .clone()
        .applyQuaternion(state.world.quaternion.clone().invert())
      const horizontal = route?.grid?.horizontal_axes ?? [0, 2]
      renderRef.current()
      robotPositionRef.current = [
        scenePosition.getComponent(horizontal[0]),
        scenePosition.getComponent(horizontal[1]),
      ]
      return true
    }
    const updateFirstPersonCamera = () => {
      const state = stateRef.current
      const person = state?.motion.robot
      if (!state?.manualControl || !state.firstPerson || !person) {
        return
      }
      person.visible = false
      camera.position
        .copy(person.position)
        .add(new THREE.Vector3(
          0,
          firstPersonEyeHeight[robotProfileRef.current] - CROUCH_EYE_DROP_M * ((person.userData.crouch as number | undefined) ?? 0),
          0,
        ))
      camera.rotation.order = 'YXZ'
      camera.rotation.set(state.manualPitch, state.manualYaw, 0)
      camera.updateMatrixWorld()
      controls.target.copy(camera.position).add(camera.getWorldDirection(new THREE.Vector3()))
      renderRef.current()
    }
    const moveCameraFromKeys = (dt: number) => {
      const state = stateRef.current
      if (!state?.cameraMove || state.manualControl || state.movementKeys.size === 0) {
        return
      }
      const forward = camera.getWorldDirection(new THREE.Vector3())
      forward.y = 0
      if (forward.lengthSq() < 1e-5) {
        return
      }
      forward.normalize()
      const right = new THREE.Vector3().crossVectors(forward, up).normalize()
      const direction = new THREE.Vector3()
      if (state.movementKeys.has('w')) direction.add(forward)
      if (state.movementKeys.has('s')) direction.sub(forward)
      if (state.movementKeys.has('d')) direction.add(right)
      if (state.movementKeys.has('a')) direction.sub(right)
      if (state.movementKeys.has(' ')) direction.add(up)
      if (state.movementKeys.has('control')) direction.sub(up)
      if (direction.lengthSq() === 0) {
        return
      }
      direction.normalize().multiplyScalar(3 * dt)
      const mask = state.walkMask
      if (mask) {
        const toScene = state.world.quaternion.clone().invert()
        const sceneAt = camera.position.clone().applyQuaternion(toScene)
        const sceneStep = direction.clone().applyQuaternion(toScene)
        const [axisX, axisZ] = mask.axes
        const allowed = boundedStep(
          { x: sceneAt.getComponent(axisX), z: sceneAt.getComponent(axisZ) },
          { x: sceneStep.getComponent(axisX), z: sceneStep.getComponent(axisZ) },
          {
            minX: mask.x0 - FREE_CAMERA_MARGIN_M,
            maxX: mask.x0 + mask.cols * mask.cell_m + FREE_CAMERA_MARGIN_M,
            minZ: mask.z0 - FREE_CAMERA_MARGIN_M,
            maxZ: mask.z0 + mask.rows * mask.cell_m + FREE_CAMERA_MARGIN_M,
          },
        )
        sceneStep.setComponent(axisX, allowed.x)
        sceneStep.setComponent(axisZ, allowed.z)
        direction.copy(sceneStep.applyQuaternion(state.world.quaternion))
      }
      camera.position.add(direction)
      controls.target.add(direction)
      if (state.followOffset) {
        state.followOffset.add(direction)
      }
      if (state.smoothedCamera) {
        state.smoothedCamera.add(direction)
      }
      renderRef.current()
    }
    const faceArrivalAsset = (dt: number) => {
      const motion = stateRef.current?.motion
      if (!motion?.robot || motion.faceHeading === null || motion.active) {
        return
      }
      const heading = motion.heading ?? motion.robot.rotation.y
      const next = turnHeading(heading, motion.faceHeading, smoothFactor(4, Math.max(dt, 0.001)))
      if (Math.abs(next - heading) < 0.002) {
        motion.faceHeading = null
      }
      motion.heading = next
      motion.robot.rotation.y = next
      renderRef.current()
    }
    const advanceMotion = (dt: number) => {
      const live = stateRef.current
      const motion = live?.motion
      if (live?.manualControl) {
        return
      }
      faceArrivalAsset(dt)
      if (!motion || !motion.active || !motion.robot || !motion.curve) {
        return
      }
      // A replan is on its way and will start from here, so hold still instead
      // of being pulled back when the answer arrives.
      if (motionPausedRef.current) {
        return
      }
      // slow enough to watch the proximity highlights change during the demo
      motion.travelled = Math.min(motion.total, motion.travelled + 0.5 * dt)
      motion.arrowOffset = (motion.arrowOffset + 0.9 * dt) % Math.max(0.01, motion.total)
      updateArrowTrail()
      placeRobot(dt)
      if (motion.travelled >= motion.total) {
        motion.active = false
        // the last placement has to be drawn even though the loop stops
        // rendering once the trip is inactive
        renderRef.current()
        if (!motion.reached) {
          motion.reached = true
          // Inspect the asset: the route ends along its last tangent, which is
          // often pointing past it.
          const centre = arrivalCentreRef.current
          if (centre && live) {
            const asset = new THREE.Vector3(...centre).applyQuaternion(live.world.quaternion).sub(motion.robot.position)
            motion.faceHeading = Math.hypot(asset.x, asset.z) > 0.05 ? Math.atan2(asset.x, asset.z) : null
          }
          // No arrival cut: the camera keeps its follow framing so the robot is
          // left standing at the target, ready for the next destination.
          tripRef.current({ mode: 'arrived', travelled: motion.total, total: motion.total })
        }
      }
    }
    let frame = 0
    let lastTime = performance.now()
    let lastReport = 0
    let lastNearby = 0
    let lastNearbyKey = ''
    let lastRenderMs = 0
    let lastDrawAt = 0
    let scaleFrames = 0
    let scaleWindowStart = 0
    let lastPerf = performance.now()
    let frames = 0
    const loop = () => {
      try {
        const now = performance.now()
        const dt = Math.min(0.1, (now - lastTime) / 1000)
        lastTime = now
        advanceMotion(dt)
        let manualMoving = false
        if (stateRef.current?.manualControl) {
          if (stateRef.current.firstPerson) {
            updateFirstPersonCamera()
          }
          manualMoving = moveManualHuman(dt)
          if (stateRef.current.firstPerson) {
            updateFirstPersonCamera()
          } else if (stateRef.current.follow) {
            updateFollow(dt, manualMoving)
          }
        } else if (stateRef.current?.follow && stateRef.current.motion.robot) {
          updateFollow(dt, stateRef.current.motion.active && !motionPausedRef.current)
        }
        moveCameraFromKeys(dt)
        const animated = stateRef.current?.motion.robot?.userData.animate as
          | ((time: number, travelled: number, moving: boolean, spanAt?: number) => void)
          | undefined
        if (animated) {
          const live = stateRef.current
          animated(
            now / 1000,
            live?.manualControl ? live.manualTravelled : live?.motion.travelled ?? 0,
            live?.manualControl ? manualMoving : (live?.motion.active ?? false) && !motionPausedRef.current,
            crouchSpanPosition(),
          )
          if (stateRef.current?.motion.active) {
            renderRef.current()
          }
        }
        const liveState = stateRef.current
        const liveObjects = objectsRef.current
        // With the frames off there is nothing to measure, and a list left as it
        // was would keep naming what the robot passed before they went off.
        if (liveObjects.length === 0 && lastNearbyKey !== '') {
          lastNearbyKey = ''
          nearbyRef.current([])
        }
        if (liveState?.motion.robot && liveObjects.length > 0 && now - lastNearby > 500) {
          lastNearby = now
          const robot = liveState.motion.robot
          const sceneRobot = robot.position.clone().applyQuaternion(liveState.world.quaternion.clone().invert())
          const nearby: string[] = []
          for (const object of liveObjects) {
            if (distanceToBox(sceneRobot, object) <= NEARBY_RADIUS_M) {
              nearby.push(object.id)
            }
          }
          nearbyRef.current(nearby)
          const nearbyKey = nearby.join(',')
          if (nearbyKey !== lastNearbyKey) {
            lastNearbyKey = nearbyKey
            const nearbySet = new Set(nearby)
            const mapped = new Set(mappedRef.current)
            for (const box of liveState.boxes) {
              if (nearbySet.has(box.id)) {
                box.material.opacity = 1
              } else {
                // boxes that leave the radius have to go back to their quiet
                // state, otherwise every visited asset stays lit for the rest
                // of the drive
                const object = liveObjects.find((candidate) => candidate.id === box.id)
                if (!object) {
                  continue
                }
                const isTarget = targetRef.current === box.id
                const isSelected = selectedRef.current === box.id
                box.material.opacity = isSelected
                  ? 1
                  : isTarget
                    ? 1
                    : focusRef.current
                      ? mapped.has(box.id)
                        ? 0.45
                        : 0.08
                      : QUIET_CLASSES.has(object.class) && !mapped.has(box.id)
                        ? 0.16
                        : subtle
                          ? 0.5
                          : 0.9
              }
            }
            requestRender()
          }
        }
        if (stateRef.current?.motion.active && now - lastReport > 400) {
          lastReport = now
          tripRef.current({
            mode: 'moving',
            travelled: stateRef.current.motion.travelled,
            total: stateRef.current.motion.total,
          })
        }
        const tween = stateRef.current?.focusTween
        if (tween) {
          const progress = Math.min(1, (now - tween.start) / tween.duration)
          const eased = progress * progress * (3 - 2 * progress)
          camera.position.lerpVectors(tween.fromPosition, tween.toPosition, eased)
          controls.target.lerpVectors(tween.fromTarget, tween.toTarget, eased)
          if (progress >= 1) {
            if (stateRef.current) {
              stateRef.current.focusTween = null
            }
          }
          renderRef.current()
        }
        if (!stateRef.current?.firstPerson) {
          const beforePosition = camera.position.clone()
          const beforeTarget = controls.target.clone()
          const orbitChanged = followOrbit.update(
            () => controls.update(),
            () => camera.position.distanceToSquared(beforePosition) > 1e-12
              || controls.target.distanceToSquared(beforeTarget) > 1e-12,
          )
          if (orbitChanged) captureOrbit()
          const cameraFloorY = stateRef.current?.cameraFloorY ?? null
          if (cameraFloorY !== null && camera.position.y < cameraFloorY + CAMERA_FLOOR_CLEARANCE_M) {
            camera.position.y = cameraFloorY + CAMERA_FLOOR_CLEARANCE_M
            camera.lookAt(controls.target)
          }
        }
        const label = labelRef.current
        if (label) {
          const chosen = selectedRef.current
          const object = chosen ? objects.find((candidate) => candidate.id === chosen) : null
          const live = stateRef.current
          if (object && live) {
            const worldPoint = new THREE.Vector3(...object.centre).applyQuaternion(live.world.quaternion)
            const projected = worldPoint.clone().project(camera)
            if (projected.z > 0 && projected.z < 1) {
              label.style.left = `${(projected.x * 0.5 + 0.5) * host.clientWidth}px`
              label.style.top = `${(-projected.y * 0.5 + 0.5) * host.clientHeight}px`
              label.style.display = 'block'
            } else {
              label.style.display = 'none'
            }
          } else {
            label.style.display = 'none'
          }
        }
        const liveState2 = stateRef.current
        const liveRobot = liveState2?.motion.robot
        if (liveState2 && liveRobot) {
          const sceneRobot = liveRobot.position.clone().applyQuaternion(liveState2.world.quaternion.clone().invert())
          const upAxisName = (upAxis ?? '+y').replace(/[+-]/, '')
          const upIndex = upAxisName === 'z' ? 2 : 1
          const horizontal = [0, 1, 2].filter((axis) => axis !== upIndex)
          robotPositionRef.current = [sceneRobot.getComponent(horizontal[0]), sceneRobot.getComponent(horizontal[1])]
        }
        if (labelsRef.current && showLabelsRef.current) {
          const live = stateRef.current
          if (live) {
            for (const pill of Array.from(labelsRef.current.children) as HTMLDivElement[]) {
              const object = objectsRef.current.find((candidate) => candidate.id === pill.dataset.objectId)
              if (!object) {
                pill.style.display = 'none'
                continue
              }
              const worldPoint = new THREE.Vector3(...object.centre).applyQuaternion(live.world.quaternion)
              const projected = worldPoint.clone().project(camera)
              if (projected.z > 0 && projected.z < 1) {
                pill.style.left = `${(projected.x * 0.5 + 0.5) * host.clientWidth}px`
                pill.style.top = `${(-projected.y * 0.5 + 0.5) * host.clientHeight}px`
                pill.style.display = 'block'
              } else {
                pill.style.display = 'none'
              }
            }
          }
        }
        const drawing = needsRender || stateRef.current?.motion.active || now < warmupUntil
        if (!drawing && !drawnSharp && now - lastDrawAt > SHARPEN_AFTER_MS) {
          drawnSharp = true
          needsRender = true
          clampPixelRatio()
        }
        if (drawing || needsRender) {
          needsRender = false
          // A draw soon after the last one means the view is moving.
          if (drawing && now - lastDrawAt < SHARPEN_AFTER_MS) {
            scaleFrames += 1
            if (drawnSharp) {
              drawnSharp = false
              clampPixelRatio()
            }
            if (scaleFrames >= 2 && now - scaleWindowStart >= SCALE_WINDOW_MS) {
              const scale = nextRenderScale(movingScale, (now - scaleWindowStart) / scaleFrames)
              if (scale !== movingScale) {
                movingScale = scale
                clampPixelRatio()
              }
              scaleFrames = 0
              scaleWindowStart = now
            }
          } else {
            scaleFrames = 0
            scaleWindowStart = now
          }
          lastDrawAt = now
          const start = perfEnabled ? performance.now() : 0
          renderer.render(scene, camera)
          if (perfEnabled) {
            lastRenderMs = performance.now() - start
            frames += 1
          }
        }
        // report even when nothing was drawn, so the overlay says idle rather
        // than freezing on the warmup numbers
        if (perfEnabled && now - lastPerf > 500) {
          setPerf({
            draws: Math.round((frames * 1000) / Math.max(1, now - lastPerf)),
            ms: Math.round(lastRenderMs * 10) / 10,
            calls: renderer.info.render.calls,
            splats: splat?.numSplats ?? 0,
          })
          frames = 0
          lastPerf = now
        }
      } catch (problem) {
        setGlError(problem instanceof Error ? problem.message : String(problem))
        return
      }
      frame = requestAnimationFrame(loop)
    }
    loop()

    const resize = () => {
      if (!host.clientWidth || !host.clientHeight) {
        return
      }
      clampPixelRatio()
      renderer.setSize(host.clientWidth, host.clientHeight)
      camera.aspect = host.clientWidth / host.clientHeight
      camera.updateProjectionMatrix()
    }
    const observer = new ResizeObserver(resize)
    observer.observe(host)

    stateRef.current = {
      renderer,
      scene,
      camera,
      controls,
      world,
      splat,
      splatUrl,
      contours: null,
      overlay: null,
      objectGroup,
      meshGroups: new Map(),
      obstacleGroup: new THREE.Group(),
      occupancy: null,
      decorGroup: null,
      depthSplats: null,
      mappedGroup: null,
      placeRobotAt: null,
      updateArrows: null,
      focusTween: null,
      cameraMask: null,
      safeCameraPosition: null,
      cameraFree: null,
      stickyCamera: null,
      smoothedCamera: null,
      followTransitionStart: 0,
      cameraBlockedSince: null,
      boxGroup,
      pickGroup,
      boxes: [],
      routeGroup,
      beaconGroup,
      motion: {
        active: false,
        travelled: 0,
        total: 0,
        points: [],
        cumulative: [],
        curve: null,
        heading: null,
        arrow: null,
        arrowOffset: 0,
        arrowSpacing: 0.55,
        robot: null,
        reached: false,
        faceHeading: null,
        arcAtVertex: [],
        plannedFromM: 0,
      },
      follow: followRef.current,
      followOffset: null,
      followOffsetFromUser: false,
      followOrbit,
      cameraMove: cameraMoveRef.current,
      movementKeys: new Set<string>(),
      manualControl: manualControlRef.current,
      firstPerson: firstPersonRef.current,
      manualYaw: Math.PI,
      manualPitch: 0,
      manualTravelled: 0,
      pointerLookActive: false,
      lastPointerX: 0,
      lastPointerY: 0,
      walkMask: null,
      cameraFloorY: null,
      centre: new THREE.Vector3(0, 1, 0),
      radius: 5,
    }
    stateRef.current.mappedGroup = mappedGroup
    stateRef.current.depthSplats = depthSplats
    stateRef.current.placeRobotAt = placeRobot
    stateRef.current.updateArrows = updateArrowTrail

    return () => {
      cancelAnimationFrame(frame)
      observer.disconnect()
      renderer.domElement.removeEventListener('pointerdown', onPointerDown)
      renderer.domElement.removeEventListener('pointerup', onPointerUp)
      renderer.domElement.removeEventListener('pointercancel', onPointerCancel)
      renderer.domElement.removeEventListener('pointermove', onPointerMove)
      renderer.domElement.removeEventListener('pointerleave', onPointerLeave)
      renderer.domElement.removeEventListener('pointerup', stopPointerLook)
      renderer.domElement.removeEventListener('pointercancel', stopPointerLook)
      controls.removeEventListener('start', noteOrbitStart)
      controls.removeEventListener('end', noteOrbitEnd)
      controls.removeEventListener('change', onControlsChange)
      window.removeEventListener('keydown', onCameraKeyDown)
      window.removeEventListener('keyup', onCameraKeyUp)
      window.removeEventListener('blur', clearCameraKeys)
      const state = stateRef.current
      for (const box of state?.boxes ?? []) {
        state?.boxGroup.remove(box.lines)
        box.lines.geometry.dispose()
        box.material.dispose()
      }
      state?.pickGroup.children.forEach((child) => {
        const mesh = child as THREE.Mesh
        mesh.geometry.dispose()
        ;(mesh.material as THREE.Material).dispose()
      })
      state?.pickGroup.clear()
      if (state?.occupancy) {
        state.scene.remove(state.occupancy)
        state.occupancy.geometry.dispose()
        ;(state.occupancy.material as THREE.Material).dispose()
        state.occupancy = null
      }
      if (state?.obstacleGroup) {
        for (const child of [...state.obstacleGroup.children]) {
          const mesh = child as THREE.Mesh
          mesh.geometry?.dispose()
          ;(mesh.material as THREE.Material).dispose()
        }
        state.obstacleGroup.clear()
      }
      if (state?.objectGroup) {
        state.objectGroup.traverse((child) => {
          const mesh = child as THREE.Mesh
          mesh.geometry?.dispose()
          const material = mesh.material as THREE.Material | THREE.Material[] | undefined
          if (Array.isArray(material)) {
            material.forEach((entry) => entry.dispose())
          } else {
            material?.dispose()
          }
        })
        state.objectGroup.clear()
        state.meshGroups.clear()
      }
      if (state?.overlay) {
        state.world.remove(state.overlay)
        state.overlay.dispose()
        state.overlay = null
      }
      if (state?.contours) {
        state.world.remove(state.contours)
        state.contours.geometry.dispose()
        ;(state.contours.material as THREE.Material).dispose()
        state.contours = null
      }
      state?.beaconGroup.children.forEach((child) => {
        const mesh = child as THREE.Mesh
        mesh.geometry?.dispose()
        const material = mesh.material as THREE.Material | THREE.Material[] | undefined
        if (Array.isArray(material)) {
          material.forEach((entry) => entry.dispose())
        } else {
          material?.dispose()
        }
      })
      state?.beaconGroup.clear()
      state?.routeGroup.children.forEach((child) => {
        const mesh = child as THREE.Mesh
        mesh.geometry?.dispose()
        const material = mesh.material as THREE.Material | THREE.Material[] | undefined
        if (Array.isArray(material)) {
          material.forEach((entry) => entry.dispose())
        } else {
          material?.dispose()
        }
      })
      state?.routeGroup.clear()
      splat?.dispose()
      renderer.dispose()
      host.removeChild(renderer.domElement)
      stateRef.current = null
    }
  }, [])

  // The capture's own up axis decides how the room is turned upright. Both
  // supplied captures are -y, but the viewer reads it from the metadata.
  useEffect(() => {
    const state = stateRef.current
    if (!state) {
      return
    }
    const up = new THREE.Vector3(...upVector(upAxis))
    const target = new THREE.Vector3(0, 1, 0)
    state.world.quaternion.setFromUnitVectors(up, target)
    renderRef.current()
  }, [upAxis])

  // Swapping the baked information channel: same geometry, different colours,
  // so the camera, boxes and robot stay exactly where they were.
  useEffect(() => {
    const state = stateRef.current
    if (!state) {
      return
    }
    const wanted = filterUrl ?? splatUrl
    if (state.splatUrl === wanted) {
      return
    }
    const previous = state.splat
    if (previous) {
      state.world.remove(previous)
      previous.dispose()
    }
    setLoaded(false)
    setProgress(0)
    const mesh = new SplatMesh({
      url: wanted,
      fileType: SplatFileType.PLY,
      onProgress: (event: ProgressEvent) => {
        if (event.lengthComputable && event.total > 0) {
          setProgress(Math.round((event.loaded / event.total) * 100))
        }
      },
      onLoad: () => setLoaded(true),
    })
    mesh.rotation.set(0, 0, 0)
    mesh.initialized
      .then(() => {
        if (stateRef.current !== state || state.splat !== mesh) {
          return
        }
        setLoaded(true)
        renderRef.current()
        // the animation loop is throttled in a background tab, so paint a few
        // frames explicitly after a channel swap just as the first load does
        let tries = 0
        const paint = () => {
          state.renderer.render(state.scene, state.camera)
          tries += 1
          if (tries < 5) {
            window.setTimeout(paint, 400)
          }
        }
        paint()
      })
      .catch((problem: unknown) => {
        if (stateRef.current === state && state.splat === mesh) {
          setGlError(problem instanceof Error ? problem.message : String(problem))
        }
      })
    state.splat = mesh
    state.splatUrl = wanted
    state.world.add(mesh)
    renderRef.current()
  }, [filterUrl, splatUrl])

  useEffect(() => {
    const mesh = stateRef.current?.splat
    if (!mesh || !boxedSplatsOnly || filterBoxes.length === 0) {
      return
    }
    const edit = boxSplatFilter(filterBoxes)
    mesh.add(edit)
    renderRef.current()
    return () => {
      mesh.remove(edit)
      renderRef.current()
    }
  }, [boxedSplatsOnly, filterBoxes, filterUrl, splatUrl])

  useEffect(() => {
    const mesh = stateRef.current?.splat
    if (!mesh || heightCutoff === null || floorHeight === null || !upAxis) {
      return
    }
    const edit = heightSplatFilter(upVector(upAxis), floorHeight, heightCutoff)
    mesh.add(edit)
    renderRef.current()
    return () => {
      mesh.remove(edit)
      renderRef.current()
    }
  }, [heightCutoff, floorHeight, upAxis, filterUrl, splatUrl])

  // Selection highlight: add light to the splats inside the selected box, so
  // the viewer shows the surface the box is masking instead of only the box.
  useEffect(() => {
    const mesh = stateRef.current?.splat
    if (!mesh || !selectedId) {
      return
    }
    const object =
      frameObjects.find((candidate) => candidate.id === selectedId) ??
      objects.find((candidate) => candidate.id === selectedId)
    if (!object) {
      return
    }
    const edit = selectionSplatEdit(object)
    mesh.add(edit)
    renderRef.current()
    return () => {
      mesh.remove(edit)
      renderRef.current()
    }
  }, [selectedId, frameObjects, objects, splatUrl, filterUrl])

  useEffect(() => {
    const state = stateRef.current
    if (!state || state.meshGroups.size === 0) {
      return
    }
    const roomCentre = new THREE.Vector3()
    if (objectsRef.current.length > 0) {
      for (const object of objectsRef.current) {
        roomCentre.add(new THREE.Vector3(...object.centre))
      }
      roomCentre.multiplyScalar(1 / objectsRef.current.length)
    }
    state.meshGroups.forEach(({ group, index }) => {
      const centre = group.userData.centre as THREE.Vector3 | undefined
      if (!centre) {
        return
      }
      const direction = centre.clone().sub(roomCentre)
      if (direction.lengthSq() < 0.01) {
        direction.set(0, 1, 0)
      }
      direction.normalize()
      group.position.copy(direction).multiplyScalar(explode * (1.1 + 0.25 * index))
    })
    renderRef.current()
    state.renderer.render(state.scene, state.camera)
  }, [explode])

  // Object mode: the reviewed anchors as separate meshes, each its own node.
  useEffect(() => {
    const state = stateRef.current
    if (!state) {
      return
    }
    for (const { group } of state.meshGroups.values()) {
      state.objectGroup.remove(group)
      group.traverse((child) => {
        const mesh = child as THREE.Mesh
        mesh.geometry?.dispose()
        const material = mesh.material as THREE.Material | THREE.Material[] | undefined
        if (Array.isArray(material)) {
          material.forEach((entry) => entry.dispose())
        } else {
          material?.dispose()
        }
      })
    }
    state.meshGroups.clear()
    if (!objectMode || objectAssets.length === 0) {
      renderRef.current()
      return
    }
    const roomCentre = new THREE.Vector3()
    if (objectsRef.current.length > 0) {
      for (const object of objectsRef.current) {
        roomCentre.add(new THREE.Vector3(...object.centre))
      }
      roomCentre.multiplyScalar(1 / objectsRef.current.length)
    }
    const layout = (group: THREE.Group, index: number) => {
      const centre = group.userData.centre as THREE.Vector3 | undefined
      if (!centre) {
        return
      }
      const direction = centre.clone().sub(roomCentre)
      if (direction.lengthSq() < 0.01) {
        direction.set(0, 1, 0)
      }
      direction.normalize()
      group.position.copy(direction).multiplyScalar(explodeRef.current * (1.1 + 0.25 * index))
    }
    const loader = new PLYLoader()
    objectAssets.forEach((entry, index) => {
      const group = new THREE.Group()
      group.userData.objectId = entry.id
      state.meshGroups.set(entry.id, { group, index })
      state.objectGroup.add(group)
      if (entry.kind === 'splat') {
        const mesh = new SplatMesh({ url: entry.url, fileType: SplatFileType.PLY })
        mesh.rotation.set(0, 0, 0)
        group.add(mesh)
        // an invisible box keeps the object clickable without a mesh surface
        const anchor = objectsRef.current.find((object) => object.id === entry.id)
        if (anchor) {
          const pick = new THREE.Mesh(
            new THREE.BoxGeometry(1, 1, 1),
            new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false }),
          )
          pick.position.set(...anchor.centre)
          pick.quaternion.copy(boxQuaternion(anchor.axes))
          pick.scale.set(...anchor.extents)
          pick.userData.objectId = entry.id
          group.add(pick)
          group.userData.centre = new THREE.Vector3(...anchor.centre)
          layout(group, index)
        }
        renderRef.current()
        return
      }
      loader.load(entry.url, (geometry) => {
        geometry.computeBoundingBox()
        geometry.computeVertexNormals()
        const material = new THREE.MeshStandardMaterial({
          vertexColors: true,
          flatShading: true,
          roughness: 0.88,
          metalness: 0.05,
          side: THREE.DoubleSide,
        })
        const mesh = new THREE.Mesh(geometry, material)
        mesh.userData.objectId = entry.id
        group.add(mesh)
        const boxCentre = geometry.boundingBox?.getCenter(new THREE.Vector3())
        if (boxCentre) {
          group.userData.centre = boxCentre
          layout(group, index)
        }
        renderRef.current()
        // the animation loop is throttled in a background tab, so draw the
        // object meshes directly once they are ready
        state.renderer.render(state.scene, state.camera)
      })
    })
    renderRef.current()
  }, [objectAssets, objectMode])

  useEffect(() => {
    const state = stateRef.current
    if (!state) {
      return
    }
    if (state.splat) {
      state.splat.visible = !hideSplat
    }
    if (state.depthSplats) {
      state.depthSplats.visible = !hideSplat && occlusion
    }
    renderRef.current()
  }, [hideSplat, filterUrl, occlusion])

  // The area the planner understands: every blocked cell of the occupancy grid,
  // drawn as a faint tile on the floor.
  useEffect(() => {
    const state = stateRef.current
    if (!state) {
      return
    }
    if (state.occupancy) {
      state.scene.remove(state.occupancy)
      state.occupancy.geometry.dispose()
      ;(state.occupancy.material as THREE.Material).dispose()
      state.occupancy = null
    }
    const grid = route?.grid
    if (!showOccupancy || !grid) {
      renderRef.current()
      return
    }
    const binary = atob(grid.blocked_packed)
    const bytes = new Uint8Array(binary.length)
    for (let index = 0; index < binary.length; index += 1) {
      bytes[index] = binary.charCodeAt(index)
    }
    const bits = grid.rows * grid.cols
    const blocked: number[] = []
    for (let index = 0; index < bits; index += 1) {
      if (bytes[index >> 3] & (0x80 >> (index & 7))) {
        blocked.push(index)
      }
    }
    if (blocked.length === 0) {
      renderRef.current()
      return
    }
    const upAxisName = (upAxis ?? '+y').replace(/[+-]/, '')
    const upSign = (upAxis ?? '+y').startsWith('-') ? -1 : 1
    const upIndex = upAxisName === 'z' ? 2 : 1
    const upVectorLocal = new THREE.Vector3(...upVector(upAxis)).normalize()
    const geometry = new THREE.PlaneGeometry(grid.cell_m * 0.92, grid.cell_m * 0.92)
    const material = new THREE.MeshBasicMaterial({
      color: 0xff5544,
      transparent: true,
      opacity: 0.3,
      side: THREE.DoubleSide,
      depthWrite: false,
    })
    const mesh = new THREE.InstancedMesh(geometry, material, blocked.length)
    mesh.renderOrder = 2
    const matrix = new THREE.Matrix4()
    const quaternion = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 0, 1), upVectorLocal)
    const live = stateRef.current
    if (!live) {
      geometry.dispose()
      material.dispose()
      return
    }
    blocked.forEach((index, instance) => {
      const row = Math.floor(index / grid.cols)
      const col = index % grid.cols
      const a = grid.x0 + (col + 0.5) * grid.cell_m
      const b = grid.z0 + (row + 0.5) * grid.cell_m
      const scenePoint = new THREE.Vector3()
      scenePoint.setComponent(grid.horizontal_axes[0], a)
      scenePoint.setComponent(grid.horizontal_axes[1], b)
      scenePoint.setComponent(upIndex, upSign * (floorHeight ?? 0) + upSign * 0.05)
      const worldPoint = scenePoint.applyQuaternion(live.world.quaternion)
      matrix.compose(worldPoint, quaternion, new THREE.Vector3(1, 1, 1))
      mesh.setMatrixAt(instance, matrix)
    })
    mesh.instanceMatrix.needsUpdate = true
    live.scene.add(mesh)
    live.occupancy = mesh
    renderRef.current()
    live.renderer.render(live.scene, live.camera)
  }, [showOccupancy, route, upAxis, floorHeight])

  useEffect(() => {
    const state = stateRef.current
    const group = state?.mappedGroup
    if (!state || !group) {
      return
    }
    for (const child of [...group.children]) {
      group.remove(child)
      const line = child as THREE.LineSegments
      line.geometry?.dispose()
      const lineMaterial = line.material as THREE.Material | THREE.Material[] | undefined
      if (Array.isArray(lineMaterial)) {
        lineMaterial.forEach((entry) => entry.dispose())
      } else {
        lineMaterial?.dispose()
      }
    }
    if (!showMappedFrames || mappedFrames.length === 0) {
      renderRef.current()
      return
    }
    const world = state.world.quaternion
    for (const frame of mappedFrames) {
      const geometry = new THREE.EdgesGeometry(new THREE.BoxGeometry(1, 1, 1))
      const colour = new THREE.Color(STATE_COLOURS[frame.state] ?? '#94a3b8')
      const material = new THREE.LineBasicMaterial({
        color: colour,
        transparent: true,
        opacity: 0.55,
        depthWrite: false,
      })
      const lines = new THREE.LineSegments(geometry, material)
      lines.scale.set(frame.extents[0], frame.extents[1], frame.extents[2])
      lines.position.copy(new THREE.Vector3(...frame.centre).applyQuaternion(world))
      const basis = new THREE.Matrix4().makeBasis(
        new THREE.Vector3(...frame.axes[0]),
        new THREE.Vector3(...frame.axes[1]),
        new THREE.Vector3(...frame.axes[2]),
      )
      lines.quaternion.setFromRotationMatrix(basis).premultiply(world)
      lines.renderOrder = 1
      group.add(lines)
    }
    renderRef.current()
    state.renderer.render(state.scene, state.camera)
  }, [mappedFrames, showMappedFrames, frameKey])

  // Obstacle markers: a translucent barrier on the floor where the user placed one.
  useEffect(() => {
    const state = stateRef.current
    if (!state) {
      return
    }
    for (const child of [...state.obstacleGroup.children]) {
      state.obstacleGroup.remove(child)
      const mesh = child as THREE.Mesh
      mesh.geometry?.dispose()
      ;(mesh.material as THREE.Material).dispose()
    }
    const upAxisName = (upAxis ?? '+y').replace(/[+-]/, '')
    const upSign = (upAxis ?? '+y').startsWith('-') ? -1 : 1
    const upIndex = upAxisName === 'z' ? 2 : 1
    const horizontal = [0, 1, 2].filter((axis) => axis !== upIndex)
    for (const obstacle of obstacles) {
      const scene = new THREE.Vector3()
      scene.setComponent(horizontal[0], obstacle[0])
      scene.setComponent(horizontal[1], obstacle[1])
      scene.setComponent(upIndex, upSign * (floorHeight ?? 0))
      const worldPoint = scene.clone().applyQuaternion(state.world.quaternion)
      const marker = new THREE.Mesh(
        new THREE.CylinderGeometry(0.24, 0.24, 1.1, 20),
        new THREE.MeshBasicMaterial({ color: 0xff8c1a, transparent: true, opacity: 0.4 }),
      )
      marker.position.copy(worldPoint).add(new THREE.Vector3(0, 0.55, 0))
      marker.renderOrder = 4
      state.obstacleGroup.add(marker)
    }
    renderRef.current()
    state.renderer.render(state.scene, state.camera)
  }, [obstacles, upAxis, floorHeight])

  // In the derived channels the contours and labels carry the story, so the
  // wireframe boxes step out of the way as the reference clips do.
  useEffect(() => {
    const state = stateRef.current
    if (!state) {
      return
    }
    // Exploding moves the objects and not their frames, so the frames would
    // float around empty space and catch clicks meant for what moved away.
    const shown = framesVisible && explode === 0
    state.boxGroup.visible = shown
    state.pickGroup.visible = shown
    renderRef.current()
  }, [framesVisible, explode])

  useEffect(() => {
    const state = stateRef.current
    if (!state) {
      return
    }
    state.routeGroup.visible = showRobot
    if (state.decorGroup) {
      state.decorGroup.visible = showRoute
    }
    if (state.mappedGroup) {
      state.mappedGroup.visible = showMappedFrames
    }
    state.beaconGroup.visible = showRoute
    renderRef.current()
  }, [showRoute, showRobot, showMappedFrames])

  // Focus tween: ease the camera to a selected object in the loop.
  useEffect(() => {
    const state = stateRef.current
    if (!state || !focusTarget || state.follow) {
      return
    }
    const centre = new THREE.Vector3(...focusTarget.centre).applyQuaternion(state.world.quaternion)
    const radius = Math.max(1.0, focusTarget.radius)
    // Move a short way toward the object and aim at it. A full reposition
    // invented a new viewpoint that could end up inside plant geometry.
    const rawPosition = state.camera.position.clone().lerp(centre, 0.4)
    rawPosition.y = Math.max(centre.y + Math.max(0.9, radius * 1.1), rawPosition.y)
    const toPosition = state.safeCameraPosition
      ? state.safeCameraPosition(rawPosition, centre)
      : rawPosition
    state.focusTween = {
      start: performance.now(),
      duration: 700,
      fromPosition: state.camera.position.clone(),
      toPosition,
      fromTarget: state.controls.target.clone(),
      toTarget: centre.clone(),
    }
    renderRef.current()
  }, [focusTarget, focusToken])

  // Pastel object tint for the semantics channel: one small splat layer with
  // only the reviewed anchors, drawn over the dimmed capture so the photo still
  // reads through and the objects are the only coloured thing.
  useEffect(() => {
    const state = stateRef.current
    if (!state) {
      return
    }
    if (state.overlay) {
      state.world.remove(state.overlay)
      state.overlay.dispose()
      state.overlay = null
    }
    if (!objectOverlayUrl) {
      renderRef.current()
      return
    }
    const overlay = new SplatMesh({
      url: objectOverlayUrl,
      fileType: SplatFileType.PLY,
      onLoad: () => renderRef.current(),
    })
    overlay.rotation.set(0, 0, 0)
    overlay.initialized.catch(() => {
      if (stateRef.current?.overlay === overlay) {
        state.world.remove(overlay)
        overlay.dispose()
        state.overlay = null
      }
    })
    state.overlay = overlay
    state.world.add(overlay)
    renderRef.current()
  }, [objectOverlayUrl])

  // Quiet label pills for the reviewed objects, as in the reference clips:
  // one short label per object, no metadata wall.
  useEffect(() => {
    const host = labelsRef.current
    if (!host) {
      return
    }
    host.replaceChildren()
    if (!showLabels) {
      return
    }
    for (const object of objects) {
      const pill = document.createElement('div')
      pill.className =
        'absolute hidden -translate-x-1/2 -translate-y-1/2 whitespace-nowrap rounded border bg-slate-950/85 px-1 py-0.5 text-[9px] font-black text-slate-100'
      pill.style.borderColor = `#${new THREE.Color(CLASS_COLOURS[object.class] ?? CLASS_COLOURS.unknown).getHexString()}`
      pill.textContent = object.label ?? object.class
      pill.dataset.objectId = object.id
      host.appendChild(pill)
    }
    renderRef.current()
  }, [objects, showLabels])

  // Contour overlay for the edges channel: a thin screen-space point cloud on
  // top of a dimmed capture, so the lines stay 1 to 2 px instead of soft splats.
  useEffect(() => {
    const state = stateRef.current
    if (!state) {
      return
    }
    if (state.contours) {
      state.world.remove(state.contours)
      state.contours.geometry.dispose()
      ;(state.contours.material as THREE.Material).dispose()
      state.contours = null
    }
    if (!contourUrl) {
      renderRef.current()
      return
    }
    let cancelled = false
    fetch(contourUrl)
      .then((response) => {
        if (!response.ok) {
          throw new Error(`contours answered ${response.status}`)
        }
        return response.json() as Promise<{ points: number[][]; colors?: number[][] }>
      })
      .then((payload) => {
        if (cancelled || !stateRef.current) {
          return
        }
        const live = stateRef.current
        const positions = new Float32Array(payload.points.length * 3)
        payload.points.forEach((point, index) => {
          positions[index * 3] = point[0]
          positions[index * 3 + 1] = point[1]
          positions[index * 3 + 2] = point[2]
        })
        const geometry = new THREE.BufferGeometry()
        geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
        let vertexColors = false
        if (payload.colors && payload.colors.length === payload.points.length) {
          const colors = new Float32Array(payload.colors.length * 3)
          payload.colors.forEach((colour, index) => {
            colors[index * 3] = colour[0] / 255
            colors[index * 3 + 1] = colour[1] / 255
            colors[index * 3 + 2] = colour[2] / 255
          })
          geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3))
          vertexColors = true
        }
        const material = new THREE.PointsMaterial({
          color: vertexColors ? 0xffffff : 0xa8e6ff,
          vertexColors,
          size: 1.2,
          sizeAttenuation: false,
          transparent: true,
          opacity: 0.9,
          depthWrite: false,
        })
        const points = new THREE.Points(geometry, material)
        points.renderOrder = 3
        live.contours = points
        live.world.add(points)
        renderRef.current()
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [contourUrl])

  // Frame the room from the extracted objects, then add their boxes.
  useEffect(() => {
    const state = stateRef.current
    if (!state) {
      return
    }
    for (const box of state.boxes) {
      state.boxGroup.remove(box.lines)
      box.lines.geometry.dispose()
      box.material.dispose()
    }
    state.boxes = []
    state.pickGroup.clear()

    if (objects.length === 0) {
      return
    }

    const group = state.boxGroup
    const edges = new THREE.EdgesGeometry(new THREE.BoxGeometry(1, 1, 1))
    const boxMins: THREE.Vector3[] = []
    const boxMaxs: THREE.Vector3[] = []
    const boundMin = new THREE.Vector3(Number.POSITIVE_INFINITY, Number.POSITIVE_INFINITY, Number.POSITIVE_INFINITY)
    const boundMax = new THREE.Vector3(Number.NEGATIVE_INFINITY, Number.NEGATIVE_INFINITY, Number.NEGATIVE_INFINITY)
    for (const object of objects) {
      const quaternion = boxQuaternion(object.axes)
      const material = new THREE.LineBasicMaterial({
        color: boxColour(object, new Set(mappedIds), targetId),
        transparent: true,
        // A frame is a guide, not a surface: writing depth would cut 1 px gaps
        // in the robot wherever even a barely visible quiet frame crosses it.
        depthWrite: false,
        opacity: QUIET_CLASSES.has(object.class) && !mappedIds.includes(object.id)
          ? 0.08
          : subtle
            ? frameOpacity
            : 0.9,
      })
      const lines = new THREE.LineSegments(edges, material)
      lines.position.set(...object.centre)
      lines.quaternion.copy(quaternion)
      lines.scale.set(...object.extents)
      lines.userData.objectId = object.id
      group.add(lines)
      state.boxes.push({ id: object.id, lines, material })

      if (isPickable(object, mappedIds.includes(object.id))) {
        const pick = new THREE.Mesh(
          new THREE.BoxGeometry(1, 1, 1),
          new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false }),
        )
        pick.position.set(...object.centre)
        pick.quaternion.copy(quaternion)
        pick.scale.set(...object.extents)
        pick.userData.objectId = object.id
        state.pickGroup.add(pick)
      }

      // The box is oriented, so its axis aligned extent is the sum of the axis
      // projections of its half extents, not a sphere around the centre.
      const centre = new THREE.Vector3(...object.centre)
      const worldHalf = new THREE.Vector3()
      object.axes.forEach((axis, index) => {
        worldHalf.x += Math.abs(axis[0]) * object.extents[index] * 0.5
        worldHalf.y += Math.abs(axis[1]) * object.extents[index] * 0.5
        worldHalf.z += Math.abs(axis[2]) * object.extents[index] * 0.5
      })
      boundMin.min(new THREE.Vector3().copy(centre).sub(worldHalf))
      boundMax.max(new THREE.Vector3().copy(centre).add(worldHalf))
      boxMins.push(new THREE.Vector3().copy(centre).sub(worldHalf))
      boxMaxs.push(new THREE.Vector3().copy(centre).add(worldHalf))
    }

    const sameFrame = framedKeyRef.current === frameKey && frameRef.current !== null
    framedKeyRef.current = frameKey
    // The extraction ships the view its previews use, a hero camera standing
    // inside the room. Prefer it, so the browser and the rendered stills agree.
    if (sameFrame && (cameraPose || heightCutoffRef.current !== null)) {
      renderRef.current()
      return
    }
    if (cameraPose) {
      const eye = new THREE.Vector3(...cameraPose.eye).applyQuaternion(state.world.quaternion)
      const target = new THREE.Vector3(...cameraPose.target).applyQuaternion(state.world.quaternion)
      frameRef.current = { eye: eye.clone(), target: target.clone() }
      state.camera.position.copy(eye)
      // The artifact's up is the camera's pitched-up vector, not world up. Using
      // it as the orbit pole tilts OrbitControls and renders the room rolled.
      // The pose already carries the pitch in eye and target, so world up is
      // correct here.
      state.camera.up.set(0, 1, 0)
      state.controls.target.copy(target)
      state.controls.minDistance = 0.4
      state.controls.maxDistance = Math.max(10, eye.distanceTo(target) * 4)
      state.camera.updateProjectionMatrix()
      state.controls.update()
      state.centre.copy(target)
      state.radius = Math.max(1.5, eye.distanceTo(target))
      return
    }

    // Without a shipped view, frame the room the way a person sees it: stand inside, at eye height above
    // the floor, and look across the room. A handful of dust objects sit far
    // outside the walls, so the room is the 5th to 95th percentile of the
    // per-object extents, not the bounding box of everything.
    const frameSet = frameObjects.length > 0 ? frameObjects : objects
    const percentile = (values: number[], fraction: number): number => {
      const sorted = [...values].sort((a, b) => a - b)
      const index = Math.min(sorted.length - 1, Math.max(0, Math.round(fraction * (sorted.length - 1))))
      return sorted[index]
    }
    const axisList = [0, 1, 2]
    const lows = axisList.map((axis) => percentile(boxMins.map((point) => point.getComponent(axis)), 0.05))
    const highs = axisList.map((axis) => percentile(boxMaxs.map((point) => point.getComponent(axis)), 0.95))
    const robustMin = new THREE.Vector3(lows[0], lows[1], lows[2])
    const robustMax = new THREE.Vector3(highs[0], highs[1], highs[2])
    const size = new THREE.Vector3().subVectors(robustMax, robustMin)
    const centre = new THREE.Vector3().addVectors(robustMin, robustMax).multiplyScalar(0.5)
    const up = new THREE.Vector3(...upVector(upAxis)).normalize()
    const corners = [
      robustMin,
      robustMax,
      new THREE.Vector3(robustMin.x, robustMin.y, robustMax.z),
      new THREE.Vector3(robustMax.x, robustMax.y, robustMin.z),
    ]
    // The floor comes from the extraction artifact when it is there; the box
    // corners are a fallback because dust objects reach below the slab.
    let floorAt = floorHeight
    if (floorAt === null) {
      floorAt = Number.POSITIVE_INFINITY
      for (const corner of corners) {
        floorAt = Math.min(floorAt, corner.dot(up))
      }
    }
    // the scene axis that is horizontal and longest, for the stand position
    const horizontal = [0, 1, 2]
      .map((axis) => ({ axis, extent: size.getComponent(axis), alignment: Math.abs(up.getComponent(axis)) }))
      .filter((entry) => entry.alignment < 0.9)
      .sort((a, b) => b.extent - a.extent)
    const centreHeight = centre.dot(up)
    // Stand near one end of the room and look along it: a camera dropped in the
    // middle ends up nose to a machine. Among a few end-of-room candidates, take
    // the one with the most space around it, the same idea as the preview
    // renderer's hero camera.
    const longHorizontal = horizontal[0]
    const shortHorizontal = horizontal[1]
    const candidates: THREE.Vector3[] = []
    for (const side of [-1, 1]) {
      for (const lateral of [-0.22, 0, 0.22]) {
        const candidate = centre.clone()
        if (longHorizontal) {
          candidate.setComponent(
            longHorizontal.axis,
            centre.getComponent(longHorizontal.axis) + side * 0.34 * longHorizontal.extent,
          )
        }
        if (shortHorizontal) {
          candidate.setComponent(
            shortHorizontal.axis,
            centre.getComponent(shortHorizontal.axis) + lateral * shortHorizontal.extent,
          )
        }
        candidates.push(candidate)
      }
    }
    const clearanceAt = (point: THREE.Vector3): number => {
      let best = Number.POSITIVE_INFINITY
      for (const object of frameSet) {
        const quaternion = boxQuaternion(object.axes)
        const local = point.clone().sub(new THREE.Vector3(...object.centre)).applyQuaternion(quaternion.clone().invert())
        const outside = new THREE.Vector3(
          Math.max(Math.abs(local.x) - object.extents[0] / 2, 0),
          Math.max(Math.abs(local.y) - object.extents[1] / 2, 0),
          Math.max(Math.abs(local.z) - object.extents[2] / 2, 0),
        )
        best = Math.min(best, outside.length())
      }
      return best
    }
    let stand = candidates[0] ?? centre.clone()
    let standClearance = -1
    for (const candidate of candidates) {
      const clearance = clearanceAt(candidate)
      if (clearance > standClearance) {
        standClearance = clearance
        stand = candidate
      }
    }
    // keep the long axis bias so the view is down the room, but only among the
    // candidates that are already clear of the equipment
    stand.addScaledVector(up, floorAt + 1.45 - centreHeight)
    const lookAt = centre.clone().addScaledVector(up, floorAt + 1.1 - centreHeight)

    const uprightEye = stand.clone().applyQuaternion(state.world.quaternion)
    const uprightTarget = lookAt.clone().applyQuaternion(state.world.quaternion)
    frameRef.current = { eye: uprightEye.clone(), target: uprightTarget.clone() }
    state.camera.position.copy(uprightEye)
    state.controls.target.copy(uprightTarget)
    state.controls.minDistance = 0.4
    state.controls.maxDistance = Math.max(10, size.length() * 2)
    state.camera.updateProjectionMatrix()
    state.controls.update()
    state.centre.copy(uprightTarget)
    state.radius = Math.max(1.5, size.length() / 2)
    renderRef.current()
  }, [objects, frameObjects, frameKey, subtle, floorHeight, upAxis, mappedIds, targetId, cameraPose])

  useEffect(() => {
    const state = stateRef.current
    const frame = frameRef.current
    if (!state || !frame || resetToken === 0) {
      return
    }
    const safeEye = state.safeCameraPosition
      ? state.safeCameraPosition(frame.eye.clone(), frame.target.clone())
      : frame.eye
    state.camera.position.copy(safeEye)
    state.controls.target.copy(frame.target)
    state.controls.update()
    renderRef.current()
  }, [resetToken])

  useEffect(() => {
    const state = stateRef.current
    if (!state || topDownToken === 0 || frameObjects.length === 0) {
      return
    }
    const pose = topDownPose(frameObjects, state.world.quaternion, state.camera.fov, state.camera.aspect)
    state.focusTween = null
    state.controls.maxDistance = Math.max(state.controls.maxDistance, pose.eye.distanceTo(pose.target) * 2)
    state.camera.position.copy(pose.eye)
    state.controls.target.copy(pose.target)
    state.controls.update()
    renderRef.current()
  }, [topDownToken])

  useEffect(() => {
    if (labelRef.current) {
      labelRef.current.textContent = selectedLabel
    }
  }, [selectedLabel])

  useEffect(() => {
    const state = stateRef.current
    if (!state) {
      return
    }
    const mapped = new Set(mappedIds)
    for (const box of state.boxes) {
      const object = objects.find((candidate) => candidate.id === box.id)
      if (box.id === selectedId) {
        box.material.color.setHex(SELECTED_COLOUR)
        box.material.opacity = 1
      } else if (object) {
        box.material.color.setHex(boxColour(object, mapped, targetId))
        const isMapped = mapped.has(object.id)
        const isTarget = targetId === object.id
        // While the robot is driving, keep the frames out of its way: the
        // mapped assets stay readable and the rest of the room recedes.
        box.material.opacity = isTarget
          ? 1
          : focus
            ? isMapped
              ? 0.45
              : 0.08
            : QUIET_CLASSES.has(object.class) && !isMapped
              ? 0.16
              : subtle
                ? frameOpacity
                : 0.9
      }
    }
    renderRef.current()
  }, [selectedId, objects, mappedIds, targetId, focus, subtle])

  // The mapped target is a proposal, so its box may not be in the reviewed
  // layer. A floor beacon marks the place it maps onto, and the arrival camera
  // can frame it.
  useEffect(() => {
    const state = stateRef.current
    if (!state) {
      return
    }
    for (const child of [...state.beaconGroup.children]) {
      state.beaconGroup.remove(child)
      const mesh = child as THREE.Mesh
      mesh.geometry?.dispose()
      const material = mesh.material as THREE.Material | THREE.Material[] | undefined
      if (Array.isArray(material)) {
        material.forEach((entry) => entry.dispose())
      } else {
        material?.dispose()
      }
    }
    beaconWorldRef.current = null
    if (!targetPoint) {
      renderRef.current()
      return
    }
    const up = new THREE.Vector3(...upVector(upAxis)).normalize()
    const scenePoint = new THREE.Vector3(...targetPoint)
    const height = scenePoint.dot(up)
    const floor = floorHeight ?? height
    scenePoint.addScaledVector(up, floor + 0.03 - height)
    const worldPoint = scenePoint.applyQuaternion(state.world.quaternion)
    beaconWorldRef.current = worldPoint.clone()
    const group = new THREE.Group()
    group.position.copy(worldPoint)
    const ring = new THREE.Mesh(
      new THREE.RingGeometry(0.18, 0.26, 36),
      new THREE.MeshBasicMaterial({ color: TARGET_COLOUR, transparent: true, opacity: 0.9, side: THREE.DoubleSide }),
    )
    ring.rotation.x = -Math.PI / 2
    ring.renderOrder = 4
    addGhost(ring, TARGET_COLOUR)
    group.add(ring)
    const pole = new THREE.Mesh(
      new THREE.CylinderGeometry(0.012, 0.012, 1.0, 8),
      new THREE.MeshBasicMaterial({ color: TARGET_COLOUR, transparent: true, opacity: 0.45 }),
    )
    pole.position.y = 0.5
    pole.renderOrder = 4
    addGhost(pole, TARGET_COLOUR)
    group.add(pole)
    const cap = new THREE.Mesh(
      new THREE.SphereGeometry(0.045, 12, 10),
      new THREE.MeshBasicMaterial({ color: TARGET_COLOUR, transparent: true, opacity: 0.6 }),
    )
    cap.position.y = 1.0
    cap.renderOrder = 4
    addGhost(cap, TARGET_COLOUR)
    group.add(cap)
    state.beaconGroup.add(group)
    renderRef.current()
  }, [targetPoint, upAxis, floorHeight])

  // The route artifact is in scene coordinates and its heights are in the up
  // axis, so the viewer puts the path on the detected floor instead of trusting
  // the path's own y.
  useEffect(() => {
    const state = stateRef.current
    if (!state) {
      return
    }
    const dispose = () => {
      state.routeGroup.children.forEach((child) => {
        const mesh = child as THREE.Mesh
        mesh.geometry?.dispose()
        const material = mesh.material as THREE.Material | THREE.Material[] | undefined
        if (Array.isArray(material)) {
          material.forEach((entry) => entry.dispose())
        } else {
          material?.dispose()
        }
      })
      state.routeGroup.clear()
    }
    dispose()
    const motion = state.motion
    const previousRobot = motion.robot
    motion.active = false
    motion.travelled = 0
    motion.total = 0
    motion.points = []
    motion.cumulative = []
    motion.robot = null
    motion.reached = false
    motion.faceHeading = null
    state.manualControl = manualControl
    state.movementKeys.clear()

    const cameraGrid = route?.camera_grid ?? null
    if (cameraGrid) {
      const binary = atob(cameraGrid.blocked_packed)
      const bits = new Uint8Array(binary.length)
      for (let index = 0; index < binary.length; index += 1) {
        bits[index] = binary.charCodeAt(index)
      }
      state.cameraMask = {
        x0: cameraGrid.x0,
        z0: cameraGrid.z0,
        cell_m: cameraGrid.cell_m,
        rows: cameraGrid.rows,
        cols: cameraGrid.cols,
        axes: [
          cameraGrid.horizontal_axes[0] ?? 0,
          cameraGrid.horizontal_axes[1] ?? 2,
        ],
        bits,
      }
    } else {
      state.cameraMask = null
    }
    const walkGrid = route?.grid ?? null
    if (walkGrid) {
      const binary = atob(walkGrid.blocked_packed)
      const bits = new Uint8Array(binary.length)
      for (let index = 0; index < binary.length; index += 1) {
        bits[index] = binary.charCodeAt(index)
      }
      state.walkMask = {
        x0: walkGrid.x0,
        z0: walkGrid.z0,
        cell_m: walkGrid.cell_m,
        rows: walkGrid.rows,
        cols: walkGrid.cols,
        axes: [
          walkGrid.horizontal_axes[0] ?? 0,
          walkGrid.horizontal_axes[1] ?? 2,
        ],
        bits,
      }
    } else {
      state.walkMask = null
    }
    state.stickyCamera = null
    state.smoothedCamera = null
    if (!manualControl && !(state.follow && state.followOffsetFromUser)) {
      state.followOffset = null
      state.followOffsetFromUser = false
    }

    const up = upVector(upAxis ?? route?.up_axis)
    const axis = Math.abs(up[0]) > 0.5 ? 0 : Math.abs(up[2]) > 0.5 ? 2 : 1
    const sign = up[axis] >= 0 ? 1 : -1
    const floor = floorHeight ?? route?.floor_height_m ?? null
    const toWorld = (values: number[]): THREE.Vector3 => {
      const point = new THREE.Vector3(values[0], values[1], values[2])
      if (axis === 1 && floor !== null) {
        point.y = sign * (floor + 0.07)
      }
      return point.applyQuaternion(state.world.quaternion)
    }

    if (!route || !route.reachable || route.path.length === 0) {
      if (previousRobot || characterStart || route?.start) {
        const robot = previousRobot?.userData.profile === robotProfile
          ? previousRobot
          : buildRobot(robotProfile)
        if (previousRobot && robot !== previousRobot) {
          robot.position.copy(previousRobot.position)
          state.manualTravelled = 0
        } else if (!previousRobot) {
          const start = characterStart ?? route?.start
          if (start) robot.position.copy(toWorld(start))
        }
        robot.visible = !(manualControl && firstPersonRef.current)
        state.routeGroup.add(robot)
        motion.robot = robot
        motion.heading = robot.rotation.y
        const scenePosition = robot.position
          .clone()
          .applyQuaternion(state.world.quaternion.clone().invert())
        robotPositionRef.current = [
          scenePosition.getComponent(walkGrid?.horizontal_axes[0] ?? 0),
          scenePosition.getComponent(walkGrid?.horizontal_axes[1] ?? 2),
        ]
        if (!initialRobotTransformRef.current) {
          initialRobotTransformRef.current = {
            position: robot.position.clone(),
            heading: robot.rotation.y,
          }
        }
      }
      tripRef.current({ mode: 'idle', travelled: 0, total: 0 })
      renderRef.current()
      return
    }

    // A repeat visit can already be at the inspection waypoint, so the
    // planner returns a reachable route containing only that point. Keep the
    // robot visible by representing it as a stationary two-point path.
    const routePath = route.path.length === 1 ? [route.path[0], route.path[0]] : route.path
    const planned = routePath.map(toWorld)
    state.cameraFloorY = planned[0].y - ROBOT_FLOOR_OFFSET_M
    const liveRobot = !manualControl && previousRobot
      ? previousRobot.position.clone().setY(planned[0].y)
      : null
    const { points, offsetM } = joinRouteToRobot(planned, liveRobot)
    const curve = new THREE.CatmullRomCurve3(points, false, 'centripetal', 0.5)
    curve.arcLengthDivisions = 400
    const totalLength = Math.max(0.01, curve.getLength())
    const cumulative = [0]
    for (let index = 1; index < points.length; index += 1) {
      cumulative.push(cumulative[index - 1] + points[index - 1].distanceTo(points[index]))
    }
    // The curve passes through each vertex at an even step of its parameter.
    const stepsPerVertex = 8
    const arcLengths = curve.getLengths((points.length - 1) * stepsPerVertex)
    const arcAtVertex = points.map((_, index) => arcLengths[index * stepsPerVertex])
    curve.getLengths(curve.arcLengthDivisions)

    // A moving arrow trail instead of a thin line: flat chevrons spaced along
    // the smoothed path, scrolling in the direction of travel.
    const arrowShape = new THREE.Shape()
    arrowShape.moveTo(0, 0.17)
    arrowShape.lineTo(-0.11, -0.08)
    arrowShape.lineTo(0, -0.02)
    arrowShape.lineTo(0.11, -0.08)
    arrowShape.closePath()
    const arrowGeometry = new THREE.ExtrudeGeometry(arrowShape, { depth: 0.012, bevelEnabled: false })
    arrowGeometry.rotateX(-Math.PI / 2)
    const arrowMaterial = new THREE.MeshBasicMaterial({
      color: ROUTE_COLOUR,
      transparent: true,
      opacity: 0.55,
      side: THREE.DoubleSide,
      depthWrite: false,
    })
    const arrowCount = Math.max(1, Math.min(300, Math.floor(totalLength / 0.45)))
    const arrows = new THREE.InstancedMesh(arrowGeometry, arrowMaterial, arrowCount)
    arrows.renderOrder = 3
    const decor = new THREE.Group()
    // The visibility effect only runs when the toggle changes, and a replan after
    // arrival builds a new trail while the robot stays deployed.
    decor.visible = showRoute
    decor.add(arrows)
    // The trail stays readable behind a machine. Sharing the instance matrices
    // means the ghost chevrons scroll with the solid ones at no extra upload.
    const arrowGhosts = new THREE.InstancedMesh(arrowGeometry, ghostMaterial(ROUTE_COLOUR), arrowCount)
    arrowGhosts.instanceMatrix = arrows.instanceMatrix
    arrowGhosts.frustumCulled = false
    arrowGhosts.renderOrder = GHOST_RENDER_ORDER
    decor.add(arrowGhosts)
    state.routeGroup.add(decor)
    if (stateRef.current) {
      stateRef.current.decorGroup = decor
    }

    for (const [point, inner] of [[points[0], 0.1], [points[points.length - 1], 0.14]] as [THREE.Vector3, number][]) {
      const ring = new THREE.Mesh(
        new THREE.RingGeometry(inner, inner + 0.04, 32),
        new THREE.MeshBasicMaterial({ color: ROUTE_COLOUR, transparent: true, opacity: 0.5, side: THREE.DoubleSide }),
      )
      ring.rotation.x = -Math.PI / 2
      ring.position.copy(point)
      ring.position.y += 0.01
      addGhost(ring, ROUTE_COLOUR)
      decor.add(ring)
    }

    const previousPosition = previousRobot?.position.clone() ?? null
    const keepRobot = previousRobot?.userData.profile === robotProfile
    const robot = keepRobot && previousRobot ? previousRobot : buildRobot(robotProfile)
    if (!keepRobot) {
      state.manualTravelled = 0
    }
    motion.points = points
    motion.cumulative = cumulative
    motion.arcAtVertex = arcAtVertex
    motion.plannedFromM = offsetM
    motion.curve = curve
    motion.total = totalLength
    motion.heading = null
    motion.arrow = arrows
    motion.arrowOffset = 0
    motion.arrowSpacing = 0.45
    robot.position.copy(previousPosition ?? points[0])
    motion.heading = robot.rotation.y
    state.routeGroup.add(robot)
    motion.robot = robot
    if (!previousRobot && !manualControl) {
      state.placeRobotAt?.(0.016)
    }
    if (!initialRobotTransformRef.current) {
      if (characterStart) robot.position.copy(toWorld(characterStart))
      initialRobotTransformRef.current = {
        position: robot.position.clone(),
        heading: robot.rotation.y,
      }
    }
    const scenePosition = robot.position
      .clone()
      .applyQuaternion(state.world.quaternion.clone().invert())
    robotPositionRef.current = [
      scenePosition.getComponent(walkGrid?.horizontal_axes[0] ?? 0),
      scenePosition.getComponent(walkGrid?.horizontal_axes[1] ?? 2),
    ]
    state.updateArrows?.()
    tripRef.current({ mode: 'idle', travelled: 0, total: motion.total })
    renderRef.current()
  }, [route, floorHeight, upAxis, robotProfile, manualControl, characterStart])

  useEffect(() => {
    const state = stateRef.current
    const robot = state?.motion.robot
    const initialTransform = initialRobotTransformRef.current
    if (!state || !robot || !initialTransform || characterResetToken === 0) {
      return
    }
    state.motion.active = false
    state.motion.travelled = 0
    state.motion.reached = false
    state.motion.faceHeading = null
    state.motion.arrowOffset = 0
    state.manualTravelled = 0
    state.movementKeys.clear()
    robot.position.copy(initialTransform.position)
    robot.rotation.y = initialTransform.heading
    state.motion.heading = initialTransform.heading
    const animate = robot.userData.animate as
      | ((time: number, travelled: number, moving: boolean) => void)
      | undefined
    animate?.(performance.now() / 1000, 0, false)
    const scenePosition = robot.position
      .clone()
      .applyQuaternion(state.world.quaternion.clone().invert())
    const axes = state.walkMask?.axes ?? [0, 2]
    robotPositionRef.current = [
      scenePosition.getComponent(axes[0]),
      scenePosition.getComponent(axes[1]),
    ]
    state.followOffset = null
    state.followOffsetFromUser = false
    state.smoothedCamera = null
    state.stickyCamera = null
    state.updateArrows?.()
    tripRef.current({ mode: 'idle', travelled: 0, total: state.motion.total })
    renderRef.current()
  }, [characterResetToken, robotPositionRef])

  useEffect(() => {
    const state = stateRef.current
    if (!state || tripToken === 0) {
      return
    }
    const motion = state.motion
    if (motion.points.length < 2 || !motion.robot) {
      return
    }
    motion.active = true
    motion.travelled = 0
    motion.reached = false
    // Turn from the heading the robot has rather than snapping onto the route.
    // The curve starts under a robot that was on it, so this copy does not move
    // one; only a robot too far away to be on the route is placed on its start.
    motion.heading = motion.robot.rotation.y
    motion.faceHeading = null
    motion.arrowOffset = 0
    if (motion.curve) {
      motion.robot.position.copy(motion.curve.getPointAt(0))
    }
    tripRef.current({ mode: 'moving', travelled: 0, total: motion.total })
    renderRef.current()
  }, [tripToken])

  useEffect(() => {
    if (stateRef.current) {
      stateRef.current.follow = follow
      stateRef.current.followOrbit.reset()
      if (follow) {
        stateRef.current.focusTween = null
        stateRef.current.followTransitionStart = performance.now()
        stateRef.current.smoothedCamera = null
        stateRef.current.followOffset = null
        stateRef.current.followOffsetFromUser = false
        stateRef.current.stickyCamera = null
      }
    }
    renderRef.current()
  }, [follow])

  useEffect(() => {
    const state = stateRef.current
    if (!state) {
      return
    }
    state.cameraMove = cameraMove
    if (!cameraMove) {
      state.movementKeys.clear()
    }
    renderRef.current()
  }, [cameraMove])

  useEffect(() => {
    const state = stateRef.current
    if (!state) {
      return
    }
    state.manualControl = manualControl
    state.firstPerson = firstPerson
    state.pointerLookActive = false
    state.movementKeys.clear()
    if (manualControl) {
      state.motion.active = false
    }
    state.controls.enabled = !firstPerson
    if (state.motion.robot) {
      state.motion.robot.visible = !(manualControl && firstPerson)
    }
    if (firstPerson && state.motion.robot) {
      state.manualYaw = state.motion.robot.rotation.y + Math.PI
      state.manualPitch = 0
      state.followOffset = null
      state.followOffsetFromUser = false
    } else if (manualControl && state.follow && state.motion.robot) {
      const person = state.motion.robot
      const forward = new THREE.Vector3(0, 0, 1)
        .applyAxisAngle(new THREE.Vector3(0, 1, 0), person.rotation.y)
      const targetHeight = followTargetHeight[robotProfile]
      const target = person.position.clone().add(new THREE.Vector3(0, targetHeight, 0))
      const eye = person.position
        .clone()
        .addScaledVector(forward, -followDistances[robotProfile])
        .add(new THREE.Vector3(0, targetHeight + 0.8, 0))
      state.camera.position.copy(eye)
      state.controls.target.copy(target)
      state.camera.lookAt(target)
      state.followOffset = eye.sub(target)
      state.followOffsetFromUser = false
      state.smoothedCamera = state.camera.position.clone()
      state.followTransitionStart = performance.now()
    }
    renderRef.current()
  }, [manualControl, firstPerson, robotProfile, follow])

  if (glError) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center gap-2 rounded-xl border-2 border-slate-900 bg-slate-950 px-6 text-center">
        <p className="text-xl font-bold text-white">The splat view could not start</p>
        <p className="text-base font-semibold text-slate-200">{glError}</p>
        <p className="text-base text-slate-300">
          The room needs WebGL2 and the viewer asset: run make splat-asset, then reload.
        </p>
      </div>
    )
  }

  return (
    <div className="relative h-full w-full overflow-hidden rounded-xl border-2 border-slate-900 bg-slate-950">
      <div ref={hostRef} className="h-full w-full" />
      <div ref={labelsRef} className="pointer-events-none absolute inset-0 z-10" />
      <div
        ref={labelRef}
        className="pointer-events-none absolute z-20 hidden -translate-x-1/2 -translate-y-[125%] whitespace-nowrap rounded border border-white/60 bg-slate-950/90 px-1.5 py-0.5 text-[10px] font-black text-white"
      />
      {perf ? (
        <div className="pointer-events-none absolute left-1/2 top-3 z-20 -translate-x-1/2 rounded-md border border-slate-700 bg-slate-950/85 px-2 py-1 text-[10px] font-bold text-slate-300">
          {perf.draws === 0 ? 'idle' : `${perf.draws} draws/s`} | cpu {perf.ms.toFixed(1)} ms | {perf.calls} calls | {perf.splats.toLocaleString()} splats
        </div>
      ) : null}
      {!loaded ? (
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-3 bg-brand-navy/90">
          <img src="/brand/plantpilot-stacked-on-dark.svg" alt="PlantPilot" className="h-40 w-auto" />
          <p className="text-sm font-semibold text-slate-300">From scan to service.</p>
          <span className="text-lg font-bold text-white">loading the capture</span>
          <div className="h-2 w-64 overflow-hidden rounded-full bg-slate-800">
            <div className="h-full bg-brand-mint transition-all" style={{ width: `${Math.max(3, progress)}%` }} />
          </div>
          <p className="text-sm font-semibold text-slate-300">{progress}% of the gaussian splats</p>
        </div>
      ) : null}
    </div>
  )
}
