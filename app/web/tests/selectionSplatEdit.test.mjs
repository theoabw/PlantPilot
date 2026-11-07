import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'
import * as THREE from 'three'
import { SplatEditRgbaBlendMode, SplatEdits } from '@sparkjsdev/spark'

const source = await readFile(new URL('../src/room/selectionSplatEdit.ts', import.meta.url), 'utf8')
const boxSource = await readFile(new URL('../src/room/boxGeometry.ts', import.meta.url), 'utf8')
const boxJs = ts.transpile(boxSource, { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 })
  .replace("'three'", JSON.stringify(import.meta.resolve('three')))
const boxUrl = `data:text/javascript;base64,${Buffer.from(boxJs).toString('base64')}`
const js = ts.transpile(source, { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 })
  .replace("'@sparkjsdev/spark'", JSON.stringify(import.meta.resolve('@sparkjsdev/spark')))
  .replace("'three'", JSON.stringify(import.meta.resolve('three')))
  .replace("'./boxGeometry'", JSON.stringify(boxUrl))
const { selectionSplatEdit } = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)

test('highlight adds light inside the selected oriented box', () => {
  const object = {
    centre: [1, 2, 3],
    axes: [[0, 1, 0], [-1, 0, 0], [0, 0, 1]],
    extents: [2, 4, 6],
  }
  const edit = selectionSplatEdit([object])
  assert.equal(edit.rgbaBlendMode, SplatEditRgbaBlendMode.ADD_RGBA)
  assert.equal(edit.children.length, 1)

  const box = edit.children[0]
  assert.ok(box.isSplatEditSdf)
  // ADD_RGBA adds this to every splat's alpha, so anything but 0 solidifies fog.
  assert.equal(box.opacity, 0)
  assert.deepEqual([box.position.x, box.position.y, box.position.z], [1, 2, 3])
  assert.deepEqual([box.scale.x, box.scale.y, box.scale.z], [1.03, 2.03, 3.03])
  const axes = new THREE.Matrix4().makeBasis(
    new THREE.Vector3(0, 1, 0),
    new THREE.Vector3(-1, 0, 0),
    new THREE.Vector3(0, 0, 1),
  )
  const expected = new THREE.Quaternion().setFromRotationMatrix(axes)
  assert.ok(box.quaternion.angleTo(expected) < 1e-6)

  const packed = new SplatEdits({ maxEdits: 1, maxSdfs: 1 })
  packed.update([{ edit, sdfs: edit.children }])
  assert.equal(packed.numSdfs, 1)
  assert.equal(packed.numEdits, 1)
})

test('left-handed reviewed axes still cover the intended oriented box', () => {
  const object = {
    centre: [1, 2, 3],
    axes: [[0, 1, 0], [1, 0, 0], [0, 0, 1]],
    extents: [2, 4, 6],
  }
  const box = selectionSplatEdit([object]).children[0]
  for (let i = 0; i < 3; i += 1) {
    const actual = new THREE.Vector3(i === 0 ? 1 : 0, i === 1 ? 1 : 0, i === 2 ? 1 : 0)
      .applyQuaternion(box.quaternion)
    const expected = new THREE.Vector3(...object.axes[i])
    assert.ok(Math.abs(actual.dot(expected)) > 0.999999)
  }
})

test('all reviewed Equipment Room anchors keep their measured box axes', async () => {
  const fixture = JSON.parse(await readFile(new URL('../../../fixtures/scene/anchors_equipment.json', import.meta.url), 'utf8'))
  for (const object of fixture.anchors) {
    const box = selectionSplatEdit([object]).children[0]
    for (let i = 0; i < 3; i += 1) {
      const actual = new THREE.Vector3(i === 0 ? 1 : 0, i === 1 ? 1 : 0, i === 2 ? 1 : 0)
        .applyQuaternion(box.quaternion)
      const expected = new THREE.Vector3(...object.axes[i]).normalize()
      assert.ok(Math.abs(actual.dot(expected)) > 0.9999, `${object.label}, axis ${i}`)
    }
  }
})

test('one edit highlights every nearby box as a union without changing alpha', () => {
  const objects = [
    { centre: [1, 2, 3], axes: [[1, 0, 0], [0, 1, 0], [0, 0, 1]], extents: [1, 2, 3] },
    { centre: [4, 5, 6], axes: [[1, 0, 0], [0, 1, 0], [0, 0, 1]], extents: [3, 2, 1] },
  ]
  const edit = selectionSplatEdit(objects)
  assert.equal(edit.children.length, 2)
  assert.deepEqual(edit.children.map((box) => box.position.toArray()), objects.map((object) => object.centre))
  assert.ok(edit.children.every((box) => box.opacity === 0))
  const packed = new SplatEdits({ maxEdits: 1, maxSdfs: 2 })
  packed.update([{ edit, sdfs: edit.children }])
  assert.equal(packed.numEdits, 1)
  assert.equal(packed.numSdfs, 2)
})
