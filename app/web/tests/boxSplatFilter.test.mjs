import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'
import * as THREE from 'three'
import { SplatEditRgbaBlendMode, SplatEdits } from '@sparkjsdev/spark'

const source = await readFile(new URL('../src/room/boxSplatFilter.ts', import.meta.url), 'utf8')
const js = ts.transpile(source, { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 })
  .replace("'@sparkjsdev/spark'", JSON.stringify(import.meta.resolve('@sparkjsdev/spark')))
  .replace("'three'", JSON.stringify(import.meta.resolve('three')))
const { boxSplatFilter } = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)

test('filter encodes the union of oriented boxes in scene coordinates', () => {
  const boxes = [
    { centre: [1, 2, 3], axes: [[1, 0, 0], [0, 1, 0], [0, 0, 1]], extents: [2, 4, 6] },
    { centre: [-1, 0, 2], axes: [[0, 1, 0], [-1, 0, 0], [0, 0, 1]], extents: [4, 2, 2] },
  ]
  const edit = boxSplatFilter(boxes)
  assert.equal(edit.invert, true)
  assert.equal(edit.rgbaBlendMode, SplatEditRgbaBlendMode.MULTIPLY)
  assert.equal(edit.children.length, 2)

  const world = new THREE.Group()
  world.rotation.x = Math.PI
  world.add(edit)
  world.updateMatrixWorld(true)
  const packed = new SplatEdits({ maxEdits: 1, maxSdfs: 2 })
  packed.update([{ edit, sdfs: edit.children }])
  assert.equal(packed.numSdfs, 2)
  assert.equal(packed.editData[0] & 0x100, 0x100)

  const inside = (point, index) => {
    const data = packed.sdfFloatData
    const base = index * 32
    const offset = new THREE.Vector3().fromArray(data, base)
    const rotation = new THREE.Quaternion().fromArray(data, base + 4)
    const scale = new THREE.Vector3().fromArray(data, base + 8)
    const size = new THREE.Vector3().fromArray(data, base + 12)
    const local = point.clone().multiply(scale).applyQuaternion(rotation).add(offset)
    return Math.abs(local.x) < size.x && Math.abs(local.y) < size.y && Math.abs(local.z) < size.z
  }
  const isKept = (point) => boxes.some((_, index) => inside(point.clone().applyMatrix4(world.matrixWorld), index))
  assert.equal(isKept(new THREE.Vector3(1, 2, 3)), true)
  assert.equal(isKept(new THREE.Vector3(-1, 1.8, 2)), true)
  assert.equal(isKept(new THREE.Vector3(0, 1.8, 2)), false)
  assert.equal(isKept(new THREE.Vector3(20, 20, 20)), false)
  assert.equal(packed.sdfFloatData[19], 0)
  assert.equal(packed.sdfFloatData[51], 0)
})
