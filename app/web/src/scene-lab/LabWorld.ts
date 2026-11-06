import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { CSS2DObject, CSS2DRenderer } from 'three/examples/jsm/renderers/CSS2DRenderer.js'
import { DOCK, ROOM, type AssetStatus, type LabAsset } from './fixtures'
import {
  approachPoint,
  buildNavGrid,
  findPath,
  pathLength,
  type NavGrid,
  type Point2,
} from './pathfinding'

export type LabMode = 'idle' | 'moving' | 'arrived' | 'blocked'

export type LabProgress = {
  mode: LabMode
  targetId: string | null
  remaining: number
  pathLength: number
  waypoint: number
  waypoints: number
}

type Callbacks = {
  onSelect: (id: string) => void
  onProgress: (progress: LabProgress) => void
}

const STATUS_COLOR: Record<AssetStatus, number> = {
  healthy: 0x22c55e,
  watch: 0xf59e0b,
  fault: 0xef4444,
}

const STATUS_HEX: Record<AssetStatus, string> = {
  healthy: '#22c55e',
  watch: '#f59e0b',
  fault: '#ef4444',
}

function metal(color: number, roughness = 0.55, metalness = 0.45): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({ color, roughness, metalness })
}

function box(w: number, h: number, d: number, color: number, roughness = 0.6): THREE.Mesh {
  return new THREE.Mesh(new THREE.BoxGeometry(w, h, d), metal(color, roughness))
}

function cylinder(
  radiusTop: number,
  radiusBottom: number,
  height: number,
  color: number,
  segments = 24,
): THREE.Mesh {
  return new THREE.Mesh(
    new THREE.CylinderGeometry(radiusTop, radiusBottom, height, segments),
    metal(color),
  )
}

function addEdges(mesh: THREE.Mesh, color: number, threshold = 25): void {
  const edges = new THREE.LineSegments(
    new THREE.EdgesGeometry(mesh.geometry, threshold),
    new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.4 }),
  )
  mesh.add(edges)
}

function statusLight(status: AssetStatus, y: number): THREE.Mesh {
  const colour = STATUS_COLOR[status]
  return new THREE.Mesh(
    new THREE.SphereGeometry(0.085, 16, 12),
    new THREE.MeshStandardMaterial({
      color: colour,
      emissive: colour,
      emissiveIntensity: 2.4,
      roughness: 0.3,
    }),
  ).translateY(y)
}

function pumpMesh(asset: LabAsset): THREE.Group {
  const group = new THREE.Group()
  const base = box(asset.width * 0.92, 0.16, asset.depth * 0.82, 0x1e293b, 0.8)
  base.position.y = 0.08
  group.add(base)

  const body = cylinder(0.36, 0.36, 0.86, 0x64748b)
  body.rotation.z = Math.PI / 2
  body.position.set(-0.16, 0.56, 0)
  group.add(body)

  const motor = box(0.64, 0.62, 0.64, 0x334155)
  motor.position.set(0.46, 0.52, 0)
  group.add(motor)
  addEdges(motor, 0x64748b)

  const volute = cylinder(0.44, 0.44, 0.3, 0x475569)
  volute.rotation.x = Math.PI / 2
  volute.position.set(-0.2, 0.56, 0.16)
  group.add(volute)

  const pipe = cylinder(0.1, 0.1, 0.9, 0x94a3b8, 16)
  pipe.position.set(-0.78, 0.78, -0.18)
  group.add(pipe)

  const accent = box(asset.width * 0.86, 0.06, 0.06, STATUS_COLOR[asset.status], 0.35)
  accent.position.set(0, 0.2, asset.depth * 0.42)
  group.add(accent)

  const light = statusLight(asset.status, asset.height + 0.12)
  light.position.x = 0.46
  group.add(light)
  return group
}

function motorMesh(asset: LabAsset): THREE.Group {
  const group = new THREE.Group()
  const base = box(asset.width * 0.9, 0.14, asset.depth * 0.8, 0x1e293b, 0.8)
  base.position.y = 0.07
  group.add(base)

  const body = cylinder(0.38, 0.38, 0.9, 0x475569)
  body.rotation.z = Math.PI / 2
  body.position.y = 0.62
  group.add(body)

  for (let i = -2; i <= 2; i += 1) {
    const fin = box(0.05, 0.68, 0.68, 0x334155)
    fin.position.set(i * 0.13, 0.62, 0)
    group.add(fin)
  }

  const terminal = box(0.32, 0.16, 0.28, 0x1e293b)
  terminal.position.set(0, 0.98, 0)
  group.add(terminal)

  const light = statusLight(asset.status, asset.height + 0.12)
  light.position.x = 0.34
  group.add(light)
  return group
}

function valveMesh(asset: LabAsset): THREE.Group {
  const group = new THREE.Group()
  const pipe = cylinder(0.11, 0.11, asset.height, 0x94a3b8, 18)
  pipe.position.y = asset.height / 2
  group.add(pipe)

  const body = box(0.4, 0.42, 0.42, 0x64748b)
  body.position.y = asset.height * 0.58
  group.add(body)
  addEdges(body, 0x94a3b8)

  const wheel = new THREE.Mesh(
    new THREE.TorusGeometry(0.23, 0.035, 10, 28),
    metal(STATUS_COLOR[asset.status], 0.35, 0.6),
  )
  wheel.rotation.x = Math.PI / 2
  wheel.position.y = asset.height * 0.82
  group.add(wheel)

  const stem = cylinder(0.045, 0.045, 0.22, 0x94a3b8, 12)
  stem.position.y = asset.height * 0.72
  group.add(stem)
  return group
}

function tankMesh(asset: LabAsset): THREE.Group {
  const group = new THREE.Group()
  const radius = Math.min(asset.width, asset.depth) * 0.45
  const bodyHeight = asset.height * 0.74
  const body = cylinder(radius, radius, bodyHeight, 0x64748b, 32)
  body.position.y = bodyHeight / 2 + 0.16
  group.add(body)

  const dome = new THREE.Mesh(
    new THREE.SphereGeometry(radius, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2),
    metal(0x94a3b8),
  )
  dome.scale.y = 0.45
  dome.position.y = bodyHeight + 0.16
  group.add(dome)

  for (const [x, z] of [
    [-0.62, -0.62],
    [0.62, -0.62],
    [-0.62, 0.62],
    [0.62, 0.62],
  ]) {
    const leg = box(0.14, 0.24, 0.14, 0x334155)
    leg.position.set(x, 0.12, z)
    group.add(leg)
  }

  const band = new THREE.Mesh(
    new THREE.TorusGeometry(radius + 0.01, 0.035, 8, 40),
    metal(STATUS_COLOR[asset.status], 0.35, 0.6),
  )
  band.rotation.x = Math.PI / 2
  band.position.y = bodyHeight * 0.66
  group.add(band)

  const light = statusLight(asset.status, asset.height + 0.08)
  group.add(light)
  return group
}

function boilerMesh(asset: LabAsset): THREE.Group {
  const group = new THREE.Group()
  const body = box(asset.width, asset.height * 0.82, asset.depth, 0x334155, 0.7)
  body.position.y = asset.height * 0.41
  group.add(body)
  addEdges(body, 0x64748b)

  const door = cylinder(0.52, 0.52, 0.16, 0x475569, 32)
  door.rotation.x = Math.PI / 2
  door.position.set(0, asset.height * 0.42, asset.depth / 2 + 0.08)
  group.add(door)

  const doorRing = new THREE.Mesh(
    new THREE.TorusGeometry(0.56, 0.04, 10, 32),
    metal(STATUS_COLOR[asset.status], 0.35, 0.6),
  )
  doorRing.position.set(0, asset.height * 0.42, asset.depth / 2 + 0.17)
  group.add(doorRing)

  const stack = cylinder(0.2, 0.2, 0.9, 0x475569, 20)
  stack.position.set(asset.width * 0.28, asset.height * 0.86, -asset.depth * 0.18)
  group.add(stack)

  const light = statusLight(asset.status, asset.height + 0.14)
  light.position.x = -asset.width * 0.28
  group.add(light)
  return group
}

function buildAsset(asset: LabAsset): THREE.Group {
  switch (asset.kind) {
    case 'pump':
      return pumpMesh(asset)
    case 'motor':
      return motorMesh(asset)
    case 'valve':
      return valveMesh(asset)
    case 'tank':
      return tankMesh(asset)
    case 'boiler':
      return boilerMesh(asset)
  }
}

function dampAngle(current: number, target: number, factor: number): number {
  let delta = (target - current + Math.PI) % (Math.PI * 2)
  if (delta < 0) {
    delta += Math.PI * 2
  }
  delta -= Math.PI
  return current + delta * Math.min(1, factor)
}

function makeLabel(asset: LabAsset): CSS2DObject {
  const element = document.createElement('div')
  element.className = `scene-label ${asset.status}`

  const dot = document.createElement('span')
  dot.className = `scene-label-dot ${asset.status}`
  dot.style.backgroundColor = STATUS_HEX[asset.status]

  const tag = document.createElement('span')
  tag.className = 'scene-label-tag'
  tag.textContent = asset.id

  const name = document.createElement('span')
  name.className = 'scene-label-name'
  name.textContent = asset.name

  element.append(dot, tag, name)
  const label = new CSS2DObject(element)
  label.position.set(asset.x, asset.height + 0.45, asset.z)
  return label
}

export class LabWorld {
  private readonly host: HTMLDivElement
  private readonly assets: LabAsset[]
  private readonly callbacks: Callbacks
  private readonly renderer: THREE.WebGLRenderer
  private readonly labelRenderer: CSS2DRenderer
  private readonly scene: THREE.Scene
  private readonly camera: THREE.PerspectiveCamera
  private readonly controls: OrbitControls
  private readonly clock = new THREE.Clock()
  private readonly grid: NavGrid
  private readonly assetGroups = new Map<string, THREE.Group>()
  private readonly faultRings: THREE.Mesh[] = []
  private readonly robot: THREE.Group
  private readonly robotBody: THREE.Group
  private readonly robotLabel: HTMLDivElement
  private readonly selectionRing: THREE.Mesh
  private readonly targetPin: THREE.Mesh
  private readonly resizeObserver: ResizeObserver
  private readonly raycaster = new THREE.Raycaster()
  private readonly pointer = new THREE.Vector2()
  private frame = 0
  private elapsed = 0
  private path: THREE.Vector3[] = []
  private pathIndex = 0
  private pathLine: THREE.Mesh | null = null
  private mode: LabMode = 'idle'
  private targetId: string | null = null
  private selectedId: string | null = null
  private remaining = 0
  private totalLength = 0
  private speed = 1.3
  private follow = false
  private pointerStart: { x: number; y: number } | null = null
  private lastEmit = 0
  private disposed = false

  constructor(host: HTMLDivElement, assets: LabAsset[], callbacks: Callbacks) {
    this.host = host
    this.assets = assets
    this.callbacks = callbacks
    this.grid = buildNavGrid(assets)

    this.renderer = new THREE.WebGLRenderer({ antialias: true })
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    this.renderer.setSize(host.clientWidth || 1, host.clientHeight || 1)
    this.renderer.shadowMap.enabled = true
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping
    this.renderer.toneMappingExposure = 1.05
    this.renderer.domElement.style.display = 'block'
    this.renderer.domElement.style.width = '100%'
    this.renderer.domElement.style.height = '100%'
    host.appendChild(this.renderer.domElement)

    this.labelRenderer = new CSS2DRenderer()
    this.labelRenderer.setSize(host.clientWidth || 1, host.clientHeight || 1)
    this.labelRenderer.domElement.style.position = 'absolute'
    this.labelRenderer.domElement.style.inset = '0'
    this.labelRenderer.domElement.style.pointerEvents = 'none'
    this.labelRenderer.domElement.style.overflow = 'hidden'
    host.appendChild(this.labelRenderer.domElement)

    this.scene = new THREE.Scene()
    this.scene.background = new THREE.Color(0x0b1220)
    this.scene.fog = new THREE.Fog(0x0b1220, 22, 46)

    const viewAspect = (host.clientWidth || 1) / (host.clientHeight || 1)
    this.camera = new THREE.PerspectiveCamera(viewAspect < 1 ? 58 : 50, viewAspect, 0.1, 120)
    const home = this.homeView()
    this.camera.position.copy(home.position)

    this.controls = new OrbitControls(this.camera, this.renderer.domElement)
    this.controls.target.copy(home.target)
    this.controls.enableDamping = true
    this.controls.dampingFactor = 0.08
    this.controls.minDistance = 3
    this.controls.maxDistance = 36
    this.controls.maxPolarAngle = Math.PI / 2.15
    this.controls.update()

    this.addLights()
    this.addRoom()
    this.addDock()

    for (const asset of assets) {
      const group = buildAsset(asset)
      group.position.set(asset.x, 0, asset.z)
      group.traverse((object) => {
        object.userData.assetId = asset.id
        if (object instanceof THREE.Mesh) {
          object.castShadow = true
          object.receiveShadow = true
        }
      })
      this.assetGroups.set(asset.id, group)
      this.scene.add(group)
      this.scene.add(makeLabel(asset))

      if (asset.status === 'fault') {
        const ring = new THREE.Mesh(
          new THREE.RingGeometry(0.7, 0.82, 48),
          new THREE.MeshBasicMaterial({
            color: STATUS_COLOR.fault,
            transparent: true,
            opacity: 0.6,
            side: THREE.DoubleSide,
            depthWrite: false,
          }),
        )
        ring.rotation.x = -Math.PI / 2
        ring.position.set(asset.x, 0.025, asset.z)
        const baseScale = Math.max(asset.width, asset.depth) * 0.72 + 0.35
        ring.scale.setScalar(baseScale)
        ring.userData.baseScale = baseScale
        this.faultRings.push(ring)
        this.scene.add(ring)
      }
    }

    this.selectionRing = new THREE.Mesh(
      new THREE.RingGeometry(0.55, 0.68, 48),
      new THREE.MeshBasicMaterial({
        color: 0x38bdf8,
        transparent: true,
        opacity: 0.95,
        side: THREE.DoubleSide,
        depthWrite: false,
      }),
    )
    this.selectionRing.rotation.x = -Math.PI / 2
    this.selectionRing.position.y = 0.03
    this.selectionRing.visible = false
    this.scene.add(this.selectionRing)

    this.targetPin = new THREE.Mesh(
      new THREE.ConeGeometry(0.16, 0.34, 4),
      new THREE.MeshStandardMaterial({
        color: 0x38bdf8,
        emissive: 0x0ea5e9,
        emissiveIntensity: 1.4,
        roughness: 0.35,
      }),
    )
    this.targetPin.rotation.x = Math.PI
    this.targetPin.visible = false
    this.scene.add(this.targetPin)

    this.robot = new THREE.Group()
    this.robotBody = new THREE.Group()
    this.robot.add(this.robotBody)
    this.buildRobot()
    this.robot.position.set(DOCK.x, 0, DOCK.z)
    this.robot.rotation.y = Math.PI / 2
    this.scene.add(this.robot)

    const robotElement = document.createElement('div')
    robotElement.className = 'scene-label robot'
    robotElement.textContent = 'ROBOT'
    this.robotLabel = robotElement
    const robotLabel = new CSS2DObject(robotElement)
    robotLabel.position.set(0, 1.72, 0)
    this.robot.add(robotLabel)

    this.renderer.domElement.addEventListener('pointerdown', this.onPointerDown)
    this.renderer.domElement.addEventListener('pointerup', this.onPointerUp)

    this.resizeObserver = new ResizeObserver(() => this.resize())
    this.resizeObserver.observe(host)

    this.loop()
    this.emit(true)
  }

  private addLights(): void {
    this.scene.add(new THREE.HemisphereLight(0xbfdbfe, 0x0b1220, 1.35))

    const key = new THREE.DirectionalLight(0xffffff, 2.3)
    key.position.set(9, 14, 7)
    key.castShadow = true
    key.shadow.mapSize.set(1024, 1024)
    key.shadow.camera.left = -12
    key.shadow.camera.right = 12
    key.shadow.camera.top = 12
    key.shadow.camera.bottom = -12
    key.shadow.camera.near = 1
    key.shadow.camera.far = 40
    this.scene.add(key)

    const rim = new THREE.DirectionalLight(0x38bdf8, 0.55)
    rim.position.set(-8, 6, -6)
    this.scene.add(rim)
  }

  private addRoom(): void {
    const width = ROOM.maxX - ROOM.minX
    const depth = ROOM.maxZ - ROOM.minZ
    const centreX = (ROOM.minX + ROOM.maxX) / 2
    const centreZ = (ROOM.minZ + ROOM.maxZ) / 2

    const floor = new THREE.Mesh(
      new THREE.PlaneGeometry(width, depth),
      new THREE.MeshStandardMaterial({ color: 0x121c2e, roughness: 0.94, metalness: 0.06 }),
    )
    floor.rotation.x = -Math.PI / 2
    floor.position.set(centreX, 0, centreZ)
    floor.receiveShadow = true
    this.scene.add(floor)

    const gridPoints: THREE.Vector3[] = []
    for (let x = ROOM.minX; x <= ROOM.maxX + 0.001; x += 0.5) {
      gridPoints.push(new THREE.Vector3(x, 0.012, ROOM.minZ), new THREE.Vector3(x, 0.012, ROOM.maxZ))
    }
    for (let z = ROOM.minZ; z <= ROOM.maxZ + 0.001; z += 0.5) {
      gridPoints.push(new THREE.Vector3(ROOM.minX, 0.012, z), new THREE.Vector3(ROOM.maxX, 0.012, z))
    }
    const gridGeometry = new THREE.BufferGeometry().setFromPoints(gridPoints)
    this.scene.add(
      new THREE.LineSegments(
        gridGeometry,
        new THREE.LineBasicMaterial({ color: 0x1d3557, transparent: true, opacity: 0.62 }),
      ),
    )

    const wallMaterial = new THREE.MeshStandardMaterial({
      color: 0x18233a,
      transparent: true,
      opacity: 0.5,
      roughness: 0.9,
      side: THREE.DoubleSide,
    })
    const backWall = new THREE.Mesh(new THREE.PlaneGeometry(width, 2.6), wallMaterial)
    backWall.position.set(centreX, 1.3, ROOM.minZ)
    this.scene.add(backWall)

    const sideWall = new THREE.Mesh(new THREE.PlaneGeometry(depth, 2.6), wallMaterial)
    sideWall.rotation.y = Math.PI / 2
    sideWall.position.set(ROOM.minX, 1.3, centreZ)
    this.scene.add(sideWall)

    const curbMaterial = new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.8 })
    const curbHeight = 0.18
    const curbs = [
      { w: width, d: 0.1, x: centreX, z: ROOM.minZ },
      { w: width, d: 0.1, x: centreX, z: ROOM.maxZ },
      { w: 0.1, d: depth, x: ROOM.minX, z: centreZ },
      { w: 0.1, d: depth, x: ROOM.maxX, z: centreZ },
    ]
    for (const curb of curbs) {
      const mesh = new THREE.Mesh(new THREE.BoxGeometry(curb.w, curbHeight, curb.d), curbMaterial)
      mesh.position.set(curb.x, curbHeight / 2, curb.z)
      mesh.receiveShadow = true
      this.scene.add(mesh)
    }
  }

  private addDock(): void {
    const pad = new THREE.Mesh(
      new THREE.BoxGeometry(1.8, 0.04, 1.8),
      new THREE.MeshStandardMaterial({
        color: 0x0e7490,
        emissive: 0x0e7490,
        emissiveIntensity: 0.25,
        roughness: 0.6,
      }),
    )
    pad.position.set(DOCK.x, 0.025, DOCK.z)
    this.scene.add(pad)

    const ring = new THREE.Mesh(
      new THREE.RingGeometry(0.78, 0.86, 40),
      new THREE.MeshBasicMaterial({ color: 0x22d3ee, transparent: true, opacity: 0.7, side: THREE.DoubleSide }),
    )
    ring.rotation.x = -Math.PI / 2
    ring.position.set(DOCK.x, 0.03, DOCK.z)
    this.scene.add(ring)

    const element = document.createElement('div')
    element.className = 'scene-label dock'
    element.textContent = 'DOCK'
    const label = new CSS2DObject(element)
    label.position.set(DOCK.x, 0.18, DOCK.z + 1.25)
    this.scene.add(label)
  }

  private buildRobot(): void {
    const shell = new THREE.MeshStandardMaterial({ color: 0xe2e8f0, roughness: 0.35, metalness: 0.5 })
    const dark = new THREE.MeshStandardMaterial({ color: 0x0f172a, roughness: 0.45, metalness: 0.55 })
    const cyan = new THREE.MeshStandardMaterial({
      color: 0x38bdf8,
      emissive: 0x0ea5e9,
      emissiveIntensity: 1.6,
      roughness: 0.3,
    })

    const body = new THREE.Mesh(new THREE.CapsuleGeometry(0.28, 0.5, 8, 20), shell)
    body.position.y = 0.68
    body.castShadow = true
    this.robotBody.add(body)

    const visor = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.13, 0.06), cyan)
    visor.position.set(0, 0.82, 0.25)
    this.robotBody.add(visor)

    const head = new THREE.Mesh(new THREE.SphereGeometry(0.17, 18, 14), shell)
    head.position.y = 1.08
    head.castShadow = true
    this.robotBody.add(head)

    const antenna = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.012, 0.22, 8), dark)
    antenna.position.y = 1.3
    this.robotBody.add(antenna)

    const beacon = new THREE.Mesh(new THREE.SphereGeometry(0.045, 12, 10), cyan)
    beacon.position.y = 1.42
    this.robotBody.add(beacon)

    for (const side of [-1, 1]) {
      const wheel = new THREE.Mesh(new THREE.CylinderGeometry(0.17, 0.17, 0.12, 20), dark)
      wheel.rotation.z = Math.PI / 2
      wheel.position.set(side * 0.31, 0.18, 0)
      wheel.castShadow = true
      this.robotBody.add(wheel)
    }

    const nose = new THREE.Mesh(new THREE.ConeGeometry(0.09, 0.22, 4), cyan)
    nose.rotation.x = Math.PI / 2
    nose.position.set(0, 0.55, 0.34)
    this.robotBody.add(nose)

    const glow = new THREE.PointLight(0x38bdf8, 4.5, 4.2)
    glow.position.set(0, 1.1, 0)
    this.robotBody.add(glow)
  }

  private loop = (): void => {
    if (this.disposed) {
      return
    }
    const delta = Math.min(this.clock.getDelta(), 0.05)
    this.elapsed += delta
    this.update(delta)
    this.controls.update()
    this.renderer.render(this.scene, this.camera)
    this.labelRenderer.render(this.scene, this.camera)
    this.frame = requestAnimationFrame(this.loop)
  }

  private update(delta: number): void {
    for (const ring of this.faultRings) {
      const pulse = 1 + Math.sin(this.elapsed * 2.8) * 0.07
      const baseScale = typeof ring.userData.baseScale === 'number' ? ring.userData.baseScale : 1
      ring.scale.setScalar(baseScale * pulse)
    }

    if (this.selectedId) {
      const asset = this.asset(this.selectedId)
      if (asset) {
        this.targetPin.position.set(asset.x, asset.height + 0.72 + Math.sin(this.elapsed * 2.4) * 0.07, asset.z)
        this.targetPin.rotation.y = this.elapsed * 1.2
      }
    }

    if (this.mode === 'moving' && this.path.length > 1) {
      let step = this.speed * delta
      while (step > 0 && this.pathIndex < this.path.length - 1) {
        const target = this.path[this.pathIndex + 1]
        const dx = target.x - this.robot.position.x
        const dz = target.z - this.robot.position.z
        const distance = Math.hypot(dx, dz)
        if (distance < 0.0001) {
          this.pathIndex += 1
          continue
        }
        const heading = Math.atan2(dx, dz)
        this.robot.rotation.y = dampAngle(this.robot.rotation.y, heading, delta * 9)

        if (distance <= step) {
          this.robot.position.x = target.x
          this.robot.position.z = target.z
          this.remaining = Math.max(0, this.remaining - distance)
          step -= distance
          this.pathIndex += 1
          if (this.pathIndex >= this.path.length - 1) {
            this.mode = 'arrived'
            this.robotLabel.textContent = `ROBOT @ ${this.targetId ?? 'target'}`
            this.emit(true)
            break
          }
        } else {
          this.robot.position.x += (dx / distance) * step
          this.robot.position.z += (dz / distance) * step
          this.remaining = Math.max(0, this.remaining - step)
          step = 0
        }
      }
      this.robotBody.position.y = Math.sin(this.elapsed * 13) * 0.012
      this.emit(false)
    } else {
      this.robotBody.position.y = 0
    }

    if (this.follow) {
      const desired = new THREE.Vector3(
        this.robot.position.x,
        8.5,
        this.robot.position.z + 5.5,
      )
      this.camera.position.lerp(desired, 1 - Math.exp(-delta * 2.6))
      this.controls.target.lerp(
        new THREE.Vector3(this.robot.position.x, 0.85, this.robot.position.z),
        1 - Math.exp(-delta * 4),
      )
    }
  }

  private asset(id: string): LabAsset | undefined {
    return this.assets.find((item) => item.id === id)
  }

  select(id: string): void {
    const asset = this.asset(id)
    if (!asset) {
      return
    }
    this.selectedId = id
    const scale = Math.max(asset.width, asset.depth) * 0.72 + 0.28
    this.selectionRing.position.set(asset.x, 0.03, asset.z)
    this.selectionRing.scale.setScalar(scale)
    this.selectionRing.visible = true
    this.targetPin.visible = true
    this.targetPin.position.set(asset.x, asset.height + 0.72, asset.z)
    this.emit(true)
  }

  goTo(id: string): void {
    const asset = this.asset(id)
    if (!asset) {
      return
    }
    this.select(id)

    const start: Point2 = { x: this.robot.position.x, z: this.robot.position.z }
    const goal = approachPoint(this.grid, asset, start)
    const points = findPath(this.grid, start, goal)

    if (!points || points.length < 2) {
      this.mode = 'blocked'
      this.targetId = id
      this.path = []
      this.remaining = 0
      this.totalLength = 0
      this.robotLabel.textContent = 'ROBOT · no route'
      this.clearPathLine()
      this.emit(true)
      return
    }

    this.path = points.map((point) => new THREE.Vector3(point.x, 0, point.z))
    this.pathIndex = 0
    this.mode = 'moving'
    this.targetId = id
    this.robotLabel.textContent = `ROBOT → ${id}`
    this.totalLength = pathLength(points)
    this.remaining = this.totalLength
    this.setPathLine(points)
    this.emit(true)
  }

  reset(): void {
    this.path = []
    this.pathIndex = 0
    this.mode = 'idle'
    this.targetId = null
    this.remaining = 0
    this.totalLength = 0
    this.clearPathLine()
    this.robot.position.set(DOCK.x, 0, DOCK.z)
    this.robot.rotation.y = Math.PI / 2
    this.robotBody.position.y = 0
    this.robotLabel.textContent = 'ROBOT'
    this.emit(true)
  }

  overview(): void {
    const home = this.homeView()
    this.camera.position.copy(home.position)
    this.controls.target.copy(home.target)
    this.controls.update()
  }

  private homeView(): { position: THREE.Vector3; target: THREE.Vector3 } {
    const aspect = (this.host.clientWidth || 1) / (this.host.clientHeight || 1)
    if (aspect < 1) {
      return {
        position: new THREE.Vector3(20, 14, 19),
        target: new THREE.Vector3(7, 1.0, 4.5),
      }
    }
    return {
      position: new THREE.Vector3(15, 10, 14.5),
      target: new THREE.Vector3(7, 0.85, 4.5),
    }
  }

  setFollow(value: boolean): void {
    this.follow = value
  }

  private setPathLine(points: Point2[]): void {
    this.clearPathLine()
    if (points.length < 2) {
      return
    }
    const vectors = points.map((point) => new THREE.Vector3(point.x, 0.07, point.z))
    const curve = new THREE.CatmullRomCurve3(vectors, false, 'centripetal')
    const geometry = new THREE.TubeGeometry(curve, Math.max(12, points.length * 10), 0.038, 6, false)
    const material = new THREE.MeshStandardMaterial({
      color: 0x22d3ee,
      emissive: 0x0891b2,
      emissiveIntensity: 1.7,
      roughness: 0.35,
      transparent: true,
      opacity: 0.95,
      depthWrite: false,
    })
    const line = new THREE.Mesh(geometry, material)
    line.renderOrder = 2
    this.scene.add(line)
    this.pathLine = line
  }

  private clearPathLine(): void {
    if (!this.pathLine) {
      return
    }
    this.scene.remove(this.pathLine)
    this.pathLine.geometry.dispose()
    const material = this.pathLine.material
    if (Array.isArray(material)) {
      material.forEach((item) => item.dispose())
    } else {
      material.dispose()
    }
    this.pathLine = null
  }

  private emit(force: boolean): void {
    const now = performance.now()
    if (!force && now - this.lastEmit < 100) {
      return
    }
    this.lastEmit = now
    this.callbacks.onProgress({
      mode: this.mode,
      targetId: this.targetId,
      remaining: this.remaining,
      pathLength: this.totalLength,
      waypoint: this.pathIndex,
      waypoints: Math.max(0, this.path.length - 1),
    })
  }

  private onPointerDown = (event: PointerEvent): void => {
    this.pointerStart = { x: event.clientX, y: event.clientY }
  }

  private onPointerUp = (event: PointerEvent): void => {
    const start = this.pointerStart
    this.pointerStart = null
    if (!start || Math.hypot(event.clientX - start.x, event.clientY - start.y) > 5) {
      return
    }

    const rect = this.renderer.domElement.getBoundingClientRect()
    this.pointer.set(
      ((event.clientX - rect.left) / rect.width) * 2 - 1,
      -((event.clientY - rect.top) / rect.height) * 2 + 1,
    )
    this.raycaster.setFromCamera(this.pointer, this.camera)
    const hits = this.raycaster.intersectObjects([...this.assetGroups.values()], true)
    const hit = hits.find((item) => typeof item.object.userData.assetId === 'string')
    const id = hit?.object.userData.assetId
    if (typeof id === 'string') {
      this.select(id)
      this.callbacks.onSelect(id)
    }
  }

  private resize(): void {
    const width = this.host.clientWidth
    const height = this.host.clientHeight
    if (!width || !height) {
      return
    }
    this.renderer.setSize(width, height)
    this.labelRenderer.setSize(width, height)
    this.camera.aspect = width / height
    this.camera.fov = width / height < 1 ? 58 : 50
    this.camera.updateProjectionMatrix()
  }

  dispose(): void {
    this.disposed = true
    cancelAnimationFrame(this.frame)
    this.resizeObserver.disconnect()
    this.renderer.domElement.removeEventListener('pointerdown', this.onPointerDown)
    this.renderer.domElement.removeEventListener('pointerup', this.onPointerUp)
    this.controls.dispose()
    this.clearPathLine()

    const geometries = new Set<THREE.BufferGeometry>()
    const materials = new Set<THREE.Material>()
    this.scene.traverse((object) => {
      if (
        object instanceof THREE.Mesh ||
        object instanceof THREE.Line ||
        object instanceof THREE.LineSegments ||
        object instanceof THREE.Points
      ) {
        geometries.add(object.geometry)
        const material = object.material
        if (Array.isArray(material)) {
          material.forEach((item) => materials.add(item))
        } else if (material) {
          materials.add(material)
        }
      }
    })
    geometries.forEach((geometry) => geometry.dispose())
    materials.forEach((material) => material.dispose())

    this.renderer.dispose()
    this.renderer.domElement.remove()
    this.labelRenderer.domElement.remove()
  }
}
