import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'

const source = await readFile(new URL('../src/room/followOrbit.ts', import.meta.url), 'utf8')
const js = ts.transpile(source, { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 })
const { followCameraGoal, FollowOrbitInput } = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)

test('a stationary robot retains the user orbit instead of snapping to an avoidance position', () => {
  const desired = { x: 2, y: 1, z: 0 }
  const fallback = { x: 0.18, y: 2, z: 0.18 }
  const avoidObstacles = () => fallback
  assert.equal(followCameraGoal(desired, true, false, avoidObstacles), desired)
  assert.equal(followCameraGoal(desired, true, true, avoidObstacles), fallback)
  assert.equal(followCameraGoal(desired, false, false, avoidObstacles), fallback)
  assert.equal(followCameraGoal(desired, false, true, avoidObstacles), fallback)
})

test('follow movement reported by controls is not mistaken for user orbit', () => {
  const orbit = new FollowOrbitInput()
  orbit.start()
  orbit.end()
  let captured = 0
  const changed = orbit.update(() => {
    if (orbit.isInputChange()) captured += 1
  }, () => false)
  assert.equal(changed, false)
  assert.equal(captured, 0)
  assert.equal(orbit.isInputChange(), false)
})

test('drag and damping update the chosen angle without a time limit', () => {
  const orbit = new FollowOrbitInput()
  orbit.start()
  assert.equal(orbit.update(() => {}, () => true), true)
  orbit.end()
  for (let frame = 0; frame < 100; frame += 1) {
    assert.equal(orbit.update(() => {}, () => true), true)
  }
  assert.equal(orbit.update(() => {}, () => false), false)
  assert.equal(orbit.update(() => {}, () => true), false)
})

test('wheel input is captured immediately and reset clears pending input', () => {
  const orbit = new FollowOrbitInput()
  orbit.start()
  assert.equal(orbit.isInputChange(), true)
  orbit.end()
  orbit.reset()
  assert.equal(orbit.isInputChange(), false)
  assert.equal(orbit.update(() => {}, () => true), false)
})

test('real orbit controls keep a dragged angle when the follow target moves', () => {
  const listeners = new Map()
  const element = {
    style: {},
    clientHeight: 600,
    addEventListener(type, handler) { listeners.set(type, handler) },
    removeEventListener(type) { listeners.delete(type) },
    setPointerCapture() {},
    releasePointerCapture() {},
    getRootNode() { return this },
  }
  const camera = new THREE.PerspectiveCamera()
  camera.position.set(0, 1, -3)
  const controls = new OrbitControls(camera, element)
  controls.enableDamping = true
  controls.dampingFactor = 0.15
  const orbit = new FollowOrbitInput()
  let selected = null
  const capture = () => { selected = camera.position.clone().sub(controls.target) }
  controls.addEventListener('start', () => orbit.start())
  controls.addEventListener('end', () => orbit.end())
  controls.addEventListener('change', () => { if (orbit.isInputChange()) capture() })
  const frame = () => {
    const position = camera.position.clone()
    const target = controls.target.clone()
    if (orbit.update(() => controls.update(), () =>
      camera.position.distanceToSquared(position) > 1e-12 ||
      controls.target.distanceToSquared(target) > 1e-12)) capture()
  }
  const pointer = { pointerId: 1, pointerType: 'mouse', button: 0, clientX: 100, clientY: 100 }
  listeners.get('pointerdown')(pointer)
  listeners.get('pointermove')({ ...pointer, clientX: 250 })
  listeners.get('pointerup')(pointer)
  for (let frameNumber = 0; frameNumber < 100; frameNumber += 1) frame()
  assert.ok(selected && Math.abs(selected.x) > 1, 'drag selects a side view')
  const chosen = selected.clone()
  const step = new THREE.Vector3(0.5, 0, 0.25)
  camera.position.add(step)
  controls.target.add(step)
  frame()
  assert.ok(selected.distanceTo(chosen) < 1e-9, 'following movement does not overwrite the chosen angle')
  assert.ok(camera.position.clone().sub(controls.target).distanceTo(chosen) < 1e-4)
  controls.dispose()
})
