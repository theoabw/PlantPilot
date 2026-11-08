import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'

const source = await readFile(new URL('../src/room/SplatRoom.tsx', import.meta.url), 'utf8')
const room = ts.createSourceFile('SplatRoom.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
const handlers = new Map()
function visit(node) {
  if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name)
    && ['onPointerDown', 'onPointerMove', 'onPointerUp', 'onPointerCancel'].includes(node.name.text)) {
    handlers.set(node.name.text, node.getText(room))
  }
  ts.forEachChild(node, visit)
}
visit(room)
assert.equal(handlers.size, 4)

const pickSource = await readFile(new URL('../src/room/pickObject.ts', import.meta.url), 'utf8')
const pickJs = ts.transpile(pickSource, { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 })
  .replace("'three'", JSON.stringify(import.meta.resolve('three')))
const pickUrl = `data:text/javascript;base64,${Buffer.from(pickJs).toString('base64')}`
const harnessSource = `
import * as THREE from 'three'
import { draggedSincePress, nestedPick, visiblePick } from './pickObject'
export function harness(firstPerson) {
  const selected = []
  const capture = []
  const live = { manualControl: true, firstPerson, pointerLookActive: false, manualYaw: 0, manualPitch: 0, boxGroup: { visible: true }, boxes: [] }
  const stateRef = { current: live }
  const renderer = { domElement: {
    setPointerCapture: (id) => capture.push(id),
    getBoundingClientRect: () => ({ left: 0, top: 0, width: 200, height: 100 }),
  } }
  const pointer = { x: 0, y: 0 }
  const camera = {}
  const hit = { distance: 1, object: { userData: { objectId: 'equipment' }, scale: { x: 1, y: 1, z: 1 } } }
  const raycaster = { setFromCamera() {}, intersectObjects: () => [hit] }
  const pickGroup = { children: [] }
  const obstacleModeRef = { current: false }
  const objectModeRef = { current: false }
  const selectRef = { current: (id) => selected.push(id) }
  const splatRayDistances = () => []
  const requestRender = () => {}
  const clearHover = () => {}
  let hoveredBox = null
  let pressed = null
  const ${handlers.get('onPointerMove')};
  const ${handlers.get('onPointerDown')};
  const ${handlers.get('onPointerCancel')};
  const ${handlers.get('onPointerUp')};
  return { live, selected, capture, onPointerDown, onPointerMove, onPointerCancel, onPointerUp }
}`
const js = ts.transpile(harnessSource, { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 })
  .replace("'three'", JSON.stringify(import.meta.resolve('three')))
  .replace("'./pickObject'", JSON.stringify(pickUrl))
const { harness } = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)
const event = (x, y, pointerId = 1) => ({ clientX: x, clientY: y, pointerId, preventDefault() {} })

test('a first-person click selects equipment at the pointer position', () => {
  const controls = harness(true)
  controls.onPointerDown(event(40, 30))
  controls.onPointerUp(event(40, 30))
  assert.deepEqual(controls.capture, [1])
  assert.deepEqual(controls.selected, ['equipment'])
})

test('first-person drag looks around without selecting, even after returning', () => {
  const controls = harness(true)
  controls.onPointerDown(event(40, 30))
  controls.live.boxGroup.visible = false
  controls.onPointerMove(event(70, 30))
  controls.onPointerMove(event(40, 30))
  controls.live.boxGroup.visible = true
  controls.onPointerUp(event(40, 30))
  assert.deepEqual(controls.selected, [])
})

test('cancelled clicks do not select, and third-person clicks still do', () => {
  const controls = harness(false)
  controls.onPointerDown(event(40, 30))
  controls.onPointerCancel()
  controls.onPointerUp(event(40, 30))
  assert.deepEqual(controls.selected, [])
  controls.onPointerDown(event(40, 30))
  controls.onPointerUp(event(40, 30))
  assert.deepEqual(controls.selected, ['equipment'])
})
