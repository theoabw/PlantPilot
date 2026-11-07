import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'
import * as THREE from 'three'

const source = await readFile(new URL('../src/room/pickObject.ts', import.meta.url), 'utf8')
const js = ts.transpile(source, { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 })
  .replace("'three'", JSON.stringify(import.meta.resolve('three')))
const { isPickable, nestedPick, hiddenBySplats, visiblePick } = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)

const box = (centre, size) => {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshBasicMaterial())
  mesh.position.set(...centre)
  mesh.scale.set(...size)
  mesh.updateMatrixWorld()
  return mesh
}
const pick = (...meshes) => {
  const ray = new THREE.Raycaster(new THREE.Vector3(0, 0, -10), new THREE.Vector3(0, 0, 1))
  return nestedPick(ray.intersectObjects(meshes, false))?.object ?? null
}

test('a small box inside a larger one wins over the shell around it', () => {
  const outer = box([0, 0, 0], [4, 4, 4])
  const inner = box([0, 0, 0], [1, 1, 1])
  assert.equal(pick(outer, inner), inner)
})

test('a small box behind another box stays behind it', () => {
  const near = box([0, 0, -3], [2, 2, 2])
  const far = box([0, 0, 3], [1, 1, 1])
  assert.equal(pick(near, far), near)
})

test('nothing hit means nothing picked', () => {
  assert.equal(nestedPick([]), null)
})

test('only the shell around the room is left out of picking', () => {
  assert.equal(isPickable({ class: 'surface', extents: [6, 3, 0.2] }, false), false)
  assert.equal(isPickable({ class: 'structure', extents: [3, 1, 1] }, false), false)
  assert.equal(isPickable({ class: 'structure', extents: [1, 1, 1] }, false), true)
  assert.equal(isPickable({ class: 'pump', extents: [6, 3, 1] }, false), true)
  assert.equal(isPickable({ class: 'surface', extents: [6, 3, 0.2] }, true), true)
})

test('a surface hides a box, a floater and a box own face do not', () => {
  assert.equal(hiddenBySplats(5, [1, 1.2, 5.1]), true)
  assert.equal(hiddenBySplats(5, [1, 5.1, 5.2]), false)
  assert.equal(hiddenBySplats(5, [4.9, 4.95, 5.1]), false)
  assert.equal(hiddenBySplats(5, []), false)
})

test('a machine\'s own surface does not hide a part framed inside it', () => {
  const outer = box([0, 0, 0], [4, 4, 4])
  const inner = box([0, 0, 0], [1, 1, 1])
  const ray = new THREE.Raycaster(new THREE.Vector3(0, 0, -10), new THREE.Vector3(0, 0, 1))
  const hits = ray.intersectObjects([outer, inner], false)
  // Splats on the outer face, in front of the inner box by more than the tolerance.
  assert.equal(visiblePick(hits, () => [8.05, 8.1])?.object, inner)
})

test('a surface in front of the first box still hides the click', () => {
  const outer = box([0, 0, 0], [4, 4, 4])
  const ray = new THREE.Raycaster(new THREE.Vector3(0, 0, -10), new THREE.Vector3(0, 0, 1))
  const hits = ray.intersectObjects([outer], false)
  assert.equal(visiblePick(hits, () => [3, 3.1]), null)
})

test('a ray with no hits does not pay for the splat query', () => {
  assert.equal(visiblePick([], () => { throw new Error('queried') }), null)
})
