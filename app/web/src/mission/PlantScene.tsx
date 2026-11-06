import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import type { Asset, Cloud, RouteResult } from './api'

type Props = {
  cloud: Cloud | null
  assets: Asset[]
  selectedId: string | null
  route: RouteResult | null
  blocked: boolean
  onSelect: (id: string) => void
}

const CRITICALITY: Record<string, number> = {
  high: 0xdc2626,
  medium: 0xd97706,
  low: 0x64748b,
}

export default function PlantScene({ cloud, assets, selectedId, route, blocked, onSelect }: Props) {
  const hostRef = useRef<HTMLDivElement | null>(null)
  const [glError, setGlError] = useState<string | null>(null)
  const sceneRef = useRef<{
    renderer: THREE.WebGLRenderer
    scene: THREE.Scene
    camera: THREE.PerspectiveCamera
    controls: OrbitControls
    markers: THREE.Group
    routeLine: THREE.Line | null
    points: THREE.Points | null
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
    renderer.setClearColor(0x0b1020, 1)
    host.appendChild(renderer.domElement)

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(55, host.clientWidth / host.clientHeight, 0.1, 200)
    camera.position.set(20, 14, 21)
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
      new THREE.MeshBasicMaterial({ color: 0x111a2e }),
    )
    floor.rotation.x = -Math.PI / 2
    floor.position.set(8, -0.02, 6)
    scene.add(floor)

    const markers = new THREE.Group()
    scene.add(markers)

    const raycaster = new THREE.Raycaster()
    const pointer = new THREE.Vector2()
    const onPointerDown = (event: PointerEvent) => {
      const rect = renderer.domElement.getBoundingClientRect()
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1
      raycaster.setFromCamera(pointer, camera)
      const hit = raycaster.intersectObjects(markers.children, false)[0]
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
        state.camera.position.lerp(state.goal, 0.08)
        state.controls.target.lerp(state.target, 0.08)
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
      renderer,
      scene,
      camera,
      controls,
      markers,
      routeLine: null,
      points: null,
      target: new THREE.Vector3(8, 1.2, 6),
      goal: new THREE.Vector3(20, 14, 21),
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
    const colours = new Float32Array(cloud.count * 3)
    for (let i = 0; i < cloud.count * 3; i += 1) {
      colours[i] = cloud.colors[i] / 255
    }
    geometry.setAttribute('color', new THREE.BufferAttribute(colours, 3))
    const material = new THREE.PointsMaterial({ size: 0.045, vertexColors: true, sizeAttenuation: true })
    const points = new THREE.Points(geometry, material)
    state.scene.add(points)
    state.points = points
  }, [cloud])

  useEffect(() => {
    const state = sceneRef.current
    if (!state) {
      return
    }
    state.markers.clear()
    for (const asset of assets) {
      const selected = asset.id === selectedId
      const marker = new THREE.Mesh(
        new THREE.SphereGeometry(selected ? 0.45 : 0.28, 18, 14),
        new THREE.MeshStandardMaterial({
          color: CRITICALITY[asset.criticality] ?? 0x64748b,
          emissive: selected ? 0xffffff : 0x000000,
          emissiveIntensity: selected ? 0.55 : 0,
          roughness: 0.4,
        }),
      )
      marker.position.set(asset.pos[0], 0.9, asset.pos[2])
      marker.userData.assetId = asset.id
      state.markers.add(marker)
      if (selected) {
        state.target.set(asset.pos[0], 1.1, asset.pos[2])
        state.goal.set(asset.pos[0] + 5.5, 4.6, asset.pos[2] + 5.5)
      }
    }
  }, [assets, selectedId])

  useEffect(() => {
    const state = sceneRef.current
    if (!state) {
      return
    }
    if (state.routeLine) {
      state.scene.remove(state.routeLine)
      state.routeLine.geometry.dispose()
      state.routeLine = null
    }
    if (!route || !route.reachable || route.path.length < 2) {
      return
    }
    const geometry = new THREE.BufferGeometry().setFromPoints(
      route.path.map(([x, z]) => new THREE.Vector3(x, 0.12, z)),
    )
    const line = new THREE.Line(
      geometry,
      new THREE.LineBasicMaterial({ color: blocked ? 0xf59e0b : 0x38bdf8, linewidth: 2 }),
    )
    state.scene.add(line)
    state.routeLine = line
  }, [route, blocked])

  if (glError) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center gap-2 rounded-xl border-2 border-slate-900 bg-slate-950 px-6 text-center">
        <p className="text-xl font-bold text-white">3D view unavailable on this machine</p>
        <p className="text-base font-semibold text-slate-200">{glError}</p>
        <p className="text-base text-slate-300">
          The mission panel still works: pick equipment, compute routes and close aisles.
        </p>
      </div>
    )
  }

  return <div ref={hostRef} className="h-full w-full overflow-hidden rounded-xl border-2 border-slate-900 bg-slate-950" />
}
