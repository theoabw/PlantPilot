import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'
import * as THREE from 'three'
import { SplatEditRgbaBlendMode, SplatEdits } from '@sparkjsdev/spark'

const source = await readFile(new URL('../src/room/selectionSplatEdit.ts', import.meta.url), 'utf8')
const js = ts.transpile(source, { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 })
  .replace("'@sparkjsdev/spark'", JSON.stringify(import.meta.resolve('@sparkjsdev/spark')))
  .replace("'three'", JSON.stringify(import.meta.resolve('three')))
const { selectionSplatEdit } = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)

test('highlight adds light inside the selected oriented box', () => {
  const object = {
    centre: [1, 2, 3],
    axes: [[0, 1, 0], [-1, 0, 0], [0, 0, 1]],
    extents: [2, 4, 6],
  }
  const edit = selectionSplatEdit(object)
  assert.equal(edit.rgbaBlendMode, SplatEditRgbaBlendMode.ADD_RGBA)
  assert.equal(edit.children.length, 1)

  const box = edit.children[0]
  assert.ok(box.isSplatEditSdf)
  // ADD_RGBA adds this to every splat's alpha, so anything but 0 solidifies fog.
  assert.equal(box.opacity, 0)
  assert.deepEqual([box.position.x, box.position.y, box.position.z], [1, 2, 3])
  // The box is a unit cube scaled by half extents, so its local size is 2 m by
  // 4 m by 6 m in the object's own axes.
  assert.deepEqual([box.scale.x, box.scale.y, box.scale.z], [1, 2, 3])
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
