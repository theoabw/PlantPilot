import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { SparkRenderer, SplatFileType, SplatMesh } from '@sparkjsdev/spark'
import { CLASS_COLOURS, upVector } from './api'
import type { RoomCamera, RoomObject, RoomRoute } from './api'

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
  robot: THREE.Group | null
  reached: boolean
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
  selectedId: string | null
  mappedIds: string[]
  targetId: string | null
  cameraPose: RoomCamera | null
  maxSplats: number
  splatUrl: string
  route: RoomRoute | null
  tripToken: number
  follow: boolean
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

// Surface and structure frames are room-sized and would drown the equipment,
// so they stay quiet until selected.
const QUIET_CLASSES = new Set(['surface', 'structure', 'beam'])
// The rubric asks for assets near the robot to be highlighted as it walks.
const NEARBY_RADIUS_M = 2.5
const SELECTED_COLOUR = 0xffffff
const TARGET_COLOUR = 0xff3030
const MAPPED_COLOUR = 0x22d3ee
const ROUTE_COLOUR = 0xfbbf24

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

export default function SplatRoom({ objects, frameObjects, selectedLabel, frameKey, subtle, upAxis, floorHeight, resetToken, selectedId, mappedIds, targetId, cameraPose, maxSplats, splatUrl, route, tripToken, follow, focus, onNearby, onTrip, onSelect }: Props) {
  const hostRef = useRef<HTMLDivElement | null>(null)
  const [glError, setGlError] = useState<string | null>(null)
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
    boxGroup: THREE.Group
    pickGroup: THREE.Group
    boxes: BoxView[]
    routeGroup: THREE.Group
    motion: Motion
    follow: boolean
    centre: THREE.Vector3
    radius: number
  } | null>(null)
  const selectedRef = useRef(selectedId)
  selectedRef.current = selectedId
  const selectRef = useRef(onSelect)
  selectRef.current = onSelect
  const tripRef = useRef(onTrip)
  tripRef.current = onTrip
  const followRef = useRef(follow)
  followRef.current = follow
  const nearbyRef = useRef(onNearby)
  nearbyRef.current = onNearby
  // The framed camera is kept so the toolbar's overview and reset can restore it.
  const frameRef = useRef<{ eye: THREE.Vector3; target: THREE.Vector3 } | null>(null)
  // Switching between validated assets and raw detections rebuilds the boxes;
  // it must not move the camera, so the last framed capture is remembered.
  const framedKeyRef = useRef<string>('')
  const labelRef = useRef<HTMLDivElement | null>(null)

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
    const clampPixelRatio = () => {
      const pixels = host.clientWidth * host.clientHeight * window.devicePixelRatio ** 2
      const cap = pixels > 3_000_000 ? 1.25 : 1.75
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, cap))
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
    controls.minDistance = 0.4
    controls.maxDistance = 80

    let needsRender = true
    let warmupUntil = performance.now() + 2_500
    const requestRender = () => {
      needsRender = true
    }
    renderRef.current = requestRender

    const world = new THREE.Group()
    scene.add(world)

    let spark: SparkRenderer | null = null
    try {
      spark = new SparkRenderer({
        renderer,
        // Performance knobs. The defaults grow splats to a 512 px radius and
        // re-sort every frame; the capture's metre-wide gaussians are the main
        // source of overdraw, and 20 sorts a second still reads as smooth.
        maxStdDev: Math.sqrt(4),
        maxPixelRadius: 192,
        minAlpha: 0.01,
        minSortIntervalMs: 50,
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

    const raycaster = new THREE.Raycaster()
    const pointer = new THREE.Vector2()
    const onPointerDown = (event: PointerEvent) => {
      const rect = renderer.domElement.getBoundingClientRect()
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1
      raycaster.setFromCamera(pointer, camera)
      const hit = raycaster.intersectObjects(pickGroup.children, false)[0]
      const id = hit?.object.userData.objectId
      if (typeof id === 'string') {
        selectRef.current(id)
      }
    }
    renderer.domElement.addEventListener('pointerdown', onPointerDown)
    controls.addEventListener('change', requestRender)

    const up = new THREE.Vector3(0, 1, 0)
    const robotForward = new THREE.Vector3()
    const placeRobot = () => {
      const motion = stateRef.current?.motion
      if (!motion || !motion.robot || motion.points.length < 2) {
        return
      }
      let travelled = motion.travelled
      let index = 0
      while (index < motion.points.length - 2 && travelled > motion.cumulative[index + 1] - motion.cumulative[index]) {
        travelled -= motion.cumulative[index + 1] - motion.cumulative[index]
        index += 1
      }
      const start = motion.points[index]
      const end = motion.points[index + 1] ?? start
      const length = Math.max(0.0001, start.distanceTo(end))
      const ratio = Math.max(0, Math.min(1, travelled / length))
      motion.robot.position.copy(start).lerp(end, ratio)
      const direction = end.clone().sub(start)
      if (direction.lengthSq() > 1e-6) {
        motion.robot.rotation.y = Math.atan2(direction.x, direction.z)
      }
    }
    const updateFollow = () => {
      const robot = stateRef.current?.motion.robot
      if (!robot) {
        return
      }
      robotForward.set(0, 0, 1).applyAxisAngle(up, robot.rotation.y)
      camera.position.copy(robot.position).addScaledVector(robotForward, -2.6).add(new THREE.Vector3(0, 1.4, 0))
      controls.target.copy(robot.position).add(new THREE.Vector3(0, 0.45, 0))
    }
    const advanceMotion = (dt: number) => {
      const motion = stateRef.current?.motion
      if (!motion || !motion.active || !motion.robot || motion.points.length < 2) {
        return
      }
      motion.travelled = Math.min(motion.total, motion.travelled + 1.15 * dt)
      placeRobot()
      if (motion.travelled >= motion.total) {
        motion.active = false
        // the last placement has to be drawn even though the loop stops
        // rendering once the trip is inactive
        renderRef.current()
        if (!motion.reached) {
          motion.reached = true
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
    let lastPerf = performance.now()
    let frames = 0
    const loop = () => {
      try {
        const now = performance.now()
        const dt = Math.min(0.1, (now - lastTime) / 1000)
        lastTime = now
        advanceMotion(dt)
        if (stateRef.current?.follow && stateRef.current.motion.robot) {
          updateFollow()
        }
        const liveState = stateRef.current
        if (liveState?.motion.robot && objects.length > 0 && now - lastNearby > 500) {
          lastNearby = now
          const robot = liveState.motion.robot
          const sceneRobot = robot.position.clone().applyQuaternion(liveState.world.quaternion.clone().invert())
          const nearby: string[] = []
          for (const object of objects) {
            if (distanceToBox(sceneRobot, object) <= NEARBY_RADIUS_M) {
              nearby.push(object.id)
            }
          }
          nearbyRef.current(nearby)
          const nearbyKey = nearby.join(',')
          if (nearbyKey !== lastNearbyKey) {
            lastNearbyKey = nearbyKey
            for (const box of liveState.boxes) {
              if (nearby.includes(box.id)) {
                box.material.opacity = 1
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
        controls.update()
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
        if (needsRender || stateRef.current?.motion.active || now < warmupUntil) {
          needsRender = false
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
      boxGroup,
      pickGroup,
      boxes: [],
      routeGroup,
      motion: {
        active: false,
        travelled: 0,
        total: 0,
        points: [],
        cumulative: [],
        robot: null,
        reached: false,
      },
      follow: followRef.current,
      centre: new THREE.Vector3(0, 1, 0),
      radius: 5,
    }

    return () => {
      cancelAnimationFrame(frame)
      observer.disconnect()
      renderer.domElement.removeEventListener('pointerdown', onPointerDown)
      controls.removeEventListener('change', requestRender)
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
        opacity: QUIET_CLASSES.has(object.class) && !mappedIds.includes(object.id)
          ? 0.16
          : subtle
            ? 0.5
            : 0.9,
      })
      const lines = new THREE.LineSegments(edges, material)
      lines.position.set(...object.centre)
      lines.quaternion.copy(quaternion)
      lines.scale.set(...object.extents)
      lines.userData.objectId = object.id
      group.add(lines)
      state.boxes.push({ id: object.id, lines, material })

      const pick = new THREE.Mesh(
        new THREE.BoxGeometry(1, 1, 1),
        new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false }),
      )
      pick.position.set(...object.centre)
      pick.quaternion.copy(quaternion)
      pick.scale.set(...object.extents)
      pick.userData.objectId = object.id
      state.pickGroup.add(pick)

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
    if (cameraPose && sameFrame) {
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
    state.camera.position.copy(frame.eye)
    state.controls.target.copy(frame.target)
    state.controls.update()
    renderRef.current()
  }, [resetToken])

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
                ? 0.5
                : 0.9
      }
    }
    renderRef.current()
  }, [selectedId, objects, mappedIds, targetId, focus, subtle])

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
    motion.active = false
    motion.travelled = 0
    motion.total = 0
    motion.points = []
    motion.cumulative = []
    motion.robot = null
    motion.reached = false

    if (!route || !route.reachable || route.path.length < 2) {
      tripRef.current({ mode: 'idle', travelled: 0, total: 0 })
      return
    }

    const up = upVector(upAxis ?? route.up_axis)
    const axis = Math.abs(up[0]) > 0.5 ? 0 : Math.abs(up[2]) > 0.5 ? 2 : 1
    const sign = up[axis] >= 0 ? 1 : -1
    const floor = floorHeight ?? route.floor_height_m
    const toWorld = (values: number[]): THREE.Vector3 => {
      const point = new THREE.Vector3(values[0], values[1], values[2])
      if (axis === 1 && floor !== null) {
        point.y = sign * (floor + 0.07)
      }
      return point.applyQuaternion(state.world.quaternion)
    }

    const points = route.path.map(toWorld)
    const cumulative = [0]
    for (let index = 1; index < points.length; index += 1) {
      cumulative.push(cumulative[index - 1] + points[index - 1].distanceTo(points[index]))
    }

    const pathLine = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(points),
      new THREE.LineBasicMaterial({ color: ROUTE_COLOUR, transparent: true, opacity: 0.9 }),
    )
    state.routeGroup.add(pathLine)

    for (const [point, inner] of [[points[0], 0.16], [points[points.length - 1], 0.22]] as [THREE.Vector3, number][]) {
      const ring = new THREE.Mesh(
        new THREE.RingGeometry(inner, inner + 0.06, 32),
        new THREE.MeshBasicMaterial({ color: ROUTE_COLOUR, transparent: true, opacity: 0.75, side: THREE.DoubleSide }),
      )
      ring.rotation.x = -Math.PI / 2
      ring.position.copy(point)
      ring.position.y += 0.01
      state.routeGroup.add(ring)
    }

    const robot = new THREE.Group()
    // Spark draws the splats as a transparent pass, so the overlays have to be
    // transparent too (opacity 1 is fine) to be drawn after the capture.
    robot.renderOrder = 3
    const body = new THREE.Mesh(
      new THREE.BoxGeometry(0.44, 0.3, 0.32),
      new THREE.MeshBasicMaterial({ color: 0x1f2937, transparent: true, opacity: 1 }),
    )
    body.position.y = 0.15
    robot.add(body)
    const head = new THREE.Mesh(
      new THREE.BoxGeometry(0.2, 0.16, 0.2),
      new THREE.MeshBasicMaterial({ color: ROUTE_COLOUR, transparent: true, opacity: 1 }),
    )
    head.position.y = 0.38
    robot.add(head)
    const halo = new THREE.Mesh(
      new THREE.RingGeometry(0.3, 0.38, 32),
      new THREE.MeshBasicMaterial({ color: ROUTE_COLOUR, transparent: true, opacity: 0.85, side: THREE.DoubleSide }),
    )
    halo.renderOrder = 3
    halo.rotation.x = -Math.PI / 2
    halo.position.y = 0.02
    robot.add(halo)
    robot.position.copy(points[0])
    state.routeGroup.add(robot)

    motion.points = points
    motion.cumulative = cumulative
    motion.total = cumulative[cumulative.length - 1]
    motion.robot = robot
    tripRef.current({ mode: 'idle', travelled: 0, total: motion.total })
    renderRef.current()
  }, [route, floorHeight, upAxis])

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
    motion.robot.position.copy(motion.points[0])
    tripRef.current({ mode: 'moving', travelled: 0, total: motion.total })
    renderRef.current()
  }, [tripToken])

  useEffect(() => {
    if (stateRef.current) {
      stateRef.current.follow = follow
    }
    renderRef.current()
  }, [follow])

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
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-3 bg-slate-950/80">
          <span className="text-lg font-bold text-white">loading the capture</span>
          <div className="h-2 w-64 overflow-hidden rounded-full bg-slate-800">
            <div className="h-full bg-cyan-400 transition-all" style={{ width: `${Math.max(3, progress)}%` }} />
          </div>
          <p className="text-sm font-semibold text-slate-300">{progress}% of the gaussian splats</p>
        </div>
      ) : null}
    </div>
  )
}
