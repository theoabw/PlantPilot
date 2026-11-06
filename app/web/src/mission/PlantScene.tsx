import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import type { Asset, Cloud, RouteResult } from './api'

type Props = {
  cloud: Cloud | null
  assets: Asset[]
  attention: Set<string>
  selectedId: string | null
  route: RouteResult | null
  blocked: boolean
  onSelect: (id: string) => void
}

const SELECTED = new THREE.Color(0x3b82f6)
const ATTENTION = new THREE.Color(0xf0a202)
const DIM = 0.4

export default function PlantScene({ cloud, assets, attention, selectedId, route, blocked, onSelect }: Props) {
  const hostRef = useRef<HTMLDivElement | null>(null)
  const [glError, setGlError] = useState<string | null>(null)
  const sceneRef = useRef<{
    renderer: THREE.WebGLRenderer
    scene: THREE.Scene
    camera: THREE.PerspectiveCamera
    controls: OrbitControls
    pickers: THREE.Group
    waypoint: THREE.Object3D | null
    routeLine: THREE.Object3D | null
    points: THREE.Points | null
    colourAttr: THREE.BufferAttribute | null
    base: Float32Array | null
    target: THREE.Vector3
    goal: THREE.Vector3
  } | null>(null)
  const selectRef = useRef(onSelect)
  selectRef.current = onSelect

  useEffect(() => {
    const host = hostRef.current
    if (!host) {
      return
    }
    let renderer: THREE.WebGLRenderer
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true })
    } catch (problem) {
      setGlError(problem instanceof Error ? problem.message : String(problem))
      return
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setSize(host.clientWidth, host.clientHeight)
    renderer.setClearColor(0x080d12, 1)
    host.appendChild(renderer.domElement)

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(55, host.clientWidth / host.clientHeight, 0.1, 200)
    camera.position.set(19, 11, 19)
    const controls = new OrbitControls(camera, renderer.domElement)
    controls.target.set(8, 1.2, 6)
    controls.enableDamping = true
    controls.maxPolarAngle = Math.PI / 2.05
    controls.minDistance = 3
    controls.maxDistance = 60

    scene.add(new THREE.AmbientLight(0xffffff, 1.1))
    const key = new THREE.DirectionalLight(0xffffff, 1.4)
    key.position.set(12, 18, 10)
    scene.add(key)

    const floor = new THREE.Mesh(
      new THREE.PlaneGeometry(16, 12),
      new THREE.MeshBasicMaterial({ color: 0x0d151b }),
    )
    floor.rotation.x = -Math.PI / 2
    floor.position.set(8, -0.02, 6)
    scene.add(floor)

    // Invisible pick spheres: selecting a machine in the 3D view should work, but
    // the visible highlight is the machine's own points, not a floating marker.
    const pickers = new THREE.Group()
    scene.add(pickers)

    const raycaster = new THREE.Raycaster()
    const pointer = new THREE.Vector2()
    const onPointerDown = (event: PointerEvent) => {
      const rect = renderer.domElement.getBoundingClientRect()
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1
      raycaster.setFromCamera(pointer, camera)
      const hit = raycaster.intersectObjects(pickers.children, false)[0]
      const id = hit?.object.userData.assetId
      if (typeof id === 'string') {
        selectRef.current(id)
      }
    }
    renderer.domElement.addEventListener('pointerdown', onPointerDown)

    let frame = 0
    const loop = () => {
      const state = sceneRef.current
      if (state) {
        state.camera.position.lerp(state.goal, 0.07)
        state.controls.target.lerp(state.target, 0.07)
      }
      controls.update()
      renderer.render(scene, camera)
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

    sceneRef.current = {
      renderer, scene, camera, controls, pickers,
      waypoint: null, routeLine: null, points: null, colourAttr: null, base: null,
      target: new THREE.Vector3(8, 1.2, 6),
      goal: new THREE.Vector3(19, 11, 19),
    }

    return () => {
      cancelAnimationFrame(frame)
      observer.disconnect()
      renderer.domElement.removeEventListener('pointerdown', onPointerDown)
      renderer.dispose()
      host.removeChild(renderer.domElement)
      sceneRef.current = null
    }
  }, [])

  useEffect(() => {
    const state = sceneRef.current
    if (!state || !cloud) {
      return
    }
    if (state.points) {
      state.scene.remove(state.points)
      state.points.geometry.dispose()
    }
    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute('position', new THREE.BufferAttribute(cloud.positions, 3))
    const base = new Float32Array(cloud.count * 3)
    for (let i = 0; i < base.length; i += 1) {
      base[i] = cloud.colors[i] / 255
    }
    const colours = new Float32Array(base)
    const colourAttr = new THREE.BufferAttribute(colours, 3)
    geometry.setAttribute('color', colourAttr)
    const material = new THREE.PointsMaterial({ size: 2, vertexColors: true, sizeAttenuation: false })
    const points = new THREE.Points(geometry, material)
    state.scene.add(points)
    state.points = points
    state.colourAttr = colourAttr
    state.base = base
  }, [cloud])

  // The highlight is the geometry itself: the selected machine's own points turn
  // blue, overdue machines' points turn amber, and the rest of the hall dims.
  useEffect(() => {
    const state = sceneRef.current
    if (!state || !cloud || !state.colourAttr || !state.base) {
      return
    }
    const selectedIndex = assets.findIndex((asset) => asset.id === selectedId)
    const attentionIndex = new Set(assets.map((asset, index) => (attention.has(asset.id) ? index : -1)).filter((index) => index >= 0))
    const colours = state.colourAttr.array as Float32Array
    const dim = selectedIndex >= 0 ? DIM : 1
    for (let i = 0; i < cloud.count; i += 1) {
      const instance = cloud.instances[i]
      const at = i * 3
      if (instance === selectedIndex && selectedIndex >= 0) {
        colours[at] = SELECTED.r
        colours[at + 1] = SELECTED.g
        colours[at + 2] = SELECTED.b
      } else if (attentionIndex.has(instance)) {
        colours[at] = ATTENTION.r * dim
        colours[at + 1] = ATTENTION.g * dim
        colours[at + 2] = ATTENTION.b * dim
      } else {
        colours[at] = state.base[at] * dim
        colours[at + 1] = state.base[at + 1] * dim
        colours[at + 2] = state.base[at + 2] * dim
      }
    }
    state.colourAttr.needsUpdate = true
  }, [cloud, assets, attention, selectedId])

  useEffect(() => {
    const state = sceneRef.current
    if (!state) {
      return
    }
    state.pickers.clear()
    for (const asset of assets) {
      const picker = new THREE.Mesh(
        new THREE.SphereGeometry(0.55, 10, 8),
        new THREE.MeshBasicMaterial({ visible: false }),
      )
      picker.position.set(asset.pos[0], 0.9, asset.pos[2])
      picker.userData.assetId = asset.id
      state.pickers.add(picker)
    }
    if (state.waypoint) {
      state.scene.remove(state.waypoint)
      state.waypoint = null
    }
    const selected = assets.find((asset) => asset.id === selectedId)
    if (selected) {
      const clamp = (value: number, low: number, high: number) => Math.min(high, Math.max(low, value))
      state.target.set(selected.pos[0], 1.1, selected.pos[2])
      state.goal.set(
        clamp(selected.pos[0] + 2.2, 2.0, 14.0),
        clamp(selected.pos[1] + 7.5, 4.0, 9.5),
        clamp(selected.pos[2] + 2.2, 2.0, 10.0),
      )
      const ring = new THREE.Mesh(
        new THREE.TorusGeometry(0.42, 0.045, 8, 28),
        new THREE.MeshBasicMaterial({ color: 0x3b82f6 }),
      )
      ring.rotation.x = -Math.PI / 2
      ring.position.set(selected.waypoint[0], 0.06, selected.waypoint[1])
      state.scene.add(ring)
      state.waypoint = ring
    }
  }, [assets, selectedId])

  useEffect(() => {
    const state = sceneRef.current
    if (!state) {
      return
    }
    if (state.routeLine) {
      state.scene.remove(state.routeLine)
      ;(state.routeLine as THREE.Mesh).geometry.dispose()
      state.routeLine = null
    }
    if (!route || !route.reachable || route.path.length < 2) {
      return
    }
    const points = route.path.map(([x, z]) => new THREE.Vector3(x, 0.16, z))
    const curve = new THREE.CatmullRomCurve3(points)
    const geometry = new THREE.TubeGeometry(curve, Math.max(32, points.length), 0.06, 6, false)
    const tube = new THREE.Mesh(
      geometry,
      new THREE.MeshBasicMaterial({ color: blocked ? 0xf0a202 : 0x3b82f6 }),
    )
    state.scene.add(tube)
    state.routeLine = tube
  }, [route, blocked])

  if (glError) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center gap-2 bg-[#080d12] px-6 text-center">
        <p className="text-xl font-bold text-white">3D view unavailable on this machine</p>
        <p className="text-base font-semibold text-slate-200">{glError}</p>
        <p className="text-base text-slate-300">The work order panel still works.</p>
      </div>
    )
  }

  return <div ref={hostRef} className="h-full w-full overflow-hidden bg-[#080d12]" />
}
