import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { SparkRenderer, SplatFileType, SplatMesh } from '@sparkjsdev/spark'
import { CLASS_COLOURS, upVector } from './api'
import type { RoomCamera, RoomObject } from './api'

type Props = {
  objects: RoomObject[]
  upAxis: string | undefined
  floorHeight: number | null
  resetToken: number
  selectedId: string | null
  mappedIds: string[]
  targetId: string | null
  cameraPose: RoomCamera | null
  maxSplats: number
  splatUrl: string
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
const SELECTED_COLOUR = 0xffffff
const TARGET_COLOUR = 0xff3030
const MAPPED_COLOUR = 0x22d3ee

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

function boxQuaternion(axes: [number, number, number][]): THREE.Quaternion {
  const x = new THREE.Vector3(...axes[0]).normalize()
  const y = new THREE.Vector3(...axes[1]).normalize()
  const z = new THREE.Vector3(...axes[2]).normalize()
  return new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().makeBasis(x, y, z))
}

export default function SplatRoom({ objects, upAxis, floorHeight, resetToken, selectedId, mappedIds, targetId, cameraPose, maxSplats, splatUrl, onSelect }: Props) {
  const hostRef = useRef<HTMLDivElement | null>(null)
  const [glError, setGlError] = useState<string | null>(null)
  const [progress, setProgress] = useState(0)
  const [loaded, setLoaded] = useState(false)
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
    centre: THREE.Vector3
    radius: number
  } | null>(null)
  const selectRef = useRef(onSelect)
  selectRef.current = onSelect
  // The framed camera is kept so the toolbar's overview and reset can restore it.
  const frameRef = useRef<{ eye: THREE.Vector3; target: THREE.Vector3 } | null>(null)

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
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
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

    const world = new THREE.Group()
    scene.add(world)

    let spark: SparkRenderer | null = null
    try {
      spark = new SparkRenderer({ renderer })
      // Spark caps the splats it accumulates (2^19 by default); a capture above
      // that budget would silently render only part of the room.
      if (maxSplats > 0) {
        spark.maxSplats = maxSplats
      }
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
          // Paint a few frames once the capture is ready. requestAnimationFrame
          // is throttled when the tab is in the background, and the room should
          // not be blank the first time someone looks at it.
          let tries = 0
          const paint = () => {
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

    let frame = 0
    const loop = () => {
      try {
        controls.update()
        renderer.render(scene, camera)
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
      centre: new THREE.Vector3(0, 1, 0),
      radius: 5,
    }

    return () => {
      cancelAnimationFrame(frame)
      observer.disconnect()
      renderer.domElement.removeEventListener('pointerdown', onPointerDown)
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
      splat?.dispose()
      renderer.dispose()
      host.removeChild(renderer.domElement)
      stateRef.current = null
    }
  }, [])

  // The capture's own up axis decides how the room is turned upright: the boiler
  // room is +y and the equipment room is -y, and the metadata carries that.
  useEffect(() => {
    const state = stateRef.current
    if (!state) {
      return
    }
    const up = new THREE.Vector3(...upVector(upAxis))
    const target = new THREE.Vector3(0, 1, 0)
    state.world.quaternion.setFromUnitVectors(up, target)
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
        opacity: QUIET_CLASSES.has(object.class) && !mappedIds.includes(object.id) ? 0.16 : 0.9,
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

    // The extraction ships the view its previews use, a hero camera standing
    // inside the room. Prefer it, so the browser and the rendered stills agree.
    if (cameraPose) {
      const eye = new THREE.Vector3(...cameraPose.eye).applyQuaternion(state.world.quaternion)
      const target = new THREE.Vector3(...cameraPose.target).applyQuaternion(state.world.quaternion)
      const viewUp = new THREE.Vector3(...cameraPose.up).applyQuaternion(state.world.quaternion).normalize()
      frameRef.current = { eye: eye.clone(), target: target.clone() }
      state.camera.position.copy(eye)
      state.camera.up.copy(viewUp)
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
      for (const object of objects) {
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
  }, [objects, floorHeight, upAxis, mappedIds, targetId, cameraPose])

  useEffect(() => {
    const state = stateRef.current
    const frame = frameRef.current
    if (!state || !frame || resetToken === 0) {
      return
    }
    state.camera.position.copy(frame.eye)
    state.controls.target.copy(frame.target)
    state.controls.update()
  }, [resetToken])

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
        box.material.opacity = QUIET_CLASSES.has(object.class) && !mapped.has(object.id) ? 0.16 : 0.9
      }
    }
  }, [selectedId, objects, mappedIds, targetId])

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
