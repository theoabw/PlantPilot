import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'
import * as THREE from 'three'

const source = await readFile(new URL('../src/room/SplatRoom.tsx', import.meta.url), 'utf8')
const room = ts.createSourceFile('SplatRoom.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
const effects = new Map()
function visit(node) {
  if (ts.isCallExpression(node) && node.expression.getText(room) === 'useEffect') {
    const body = node.arguments[0]
    if (body && ts.isArrowFunction(body)) {
      const text = body.getText(room)
      if (text.includes('duration: 700') && text.includes('focusTarget')) effects.set('focus', text)
      if (text.includes('state.firstPerson = firstPerson')) effects.set('mode', text)
    }
  }
  ts.forEachChild(node, visit)
}
visit(room)
assert.equal(effects.size, 2)

const moduleSource = `
import * as THREE from 'three'
export function harness(firstPerson, follow, focusTween = null) {
  const state = {
    firstPerson: false, manualControl: false, follow, focusTween,
    world: { quaternion: new THREE.Quaternion() },
    camera: { position: new THREE.Vector3(1, 1, 1) },
    controls: { target: new THREE.Vector3(), enabled: true },
    motion: { robot: null, active: false },
    movementKeys: new Set(),
  }
  const stateRef = { current: state }
  const focusTarget = { centre: [4, 2, 1], radius: 1 }
  const manualControl = firstPerson
  const robotProfile = 'amr'
  const renderRef = { current() {} }
  const focusEffect = ${effects.get('focus')}
  const modeEffect = ${effects.get('mode')}
  return { state, focusEffect, modeEffect }
}`
const js = ts.transpile(moduleSource, { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 })
  .replace("'three'", JSON.stringify(import.meta.resolve('three')))
const { harness } = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)

test('selecting equipment in first person does not start a focus tween', () => {
  const { state, focusEffect } = harness(true, false)
  const original = state.camera.position.clone()
  focusEffect()
  assert.equal(state.focusTween, null)
  assert.ok(state.camera.position.equals(original))
})

test('entering first person cancels a focus tween already in progress', () => {
  const { state, modeEffect } = harness(true, false, { duration: 700 })
  modeEffect()
  assert.equal(state.firstPerson, true)
  assert.equal(state.focusTween, null)
})

test('third-person object focus still starts a camera tween', () => {
  const { state, focusEffect } = harness(false, false)
  focusEffect()
  assert.equal(state.focusTween.duration, 700)
  assert.ok(state.focusTween.toTarget.equals(new THREE.Vector3(4, 2, 1)))
})

test('following still suppresses object focus', () => {
  const { state, focusEffect } = harness(false, true)
  focusEffect()
  assert.equal(state.focusTween, null)
})

test('the equipment card disables camera focus in first person', async () => {
  const labSource = await readFile(new URL('../src/room/RoomLab.tsx', import.meta.url), 'utf8')
  assert.match(labSource, /onClick=\{\(\) => setFocusToken\(\(value\) => value \+ 1\)\}\s*disabled=\{firstPerson\}/)
  assert.match(labSource, /Switch to third person to focus the camera/)
})
