import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'
import * as THREE from 'three'
import { SplatEdits } from '@sparkjsdev/spark'

const source = await readFile(new URL('../src/room/heightSplatFilter.ts', import.meta.url), 'utf8')
const js = ts.transpile(source, { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 })
  .replace("'@sparkjsdev/spark'", JSON.stringify(import.meta.resolve('@sparkjsdev/spark')))
  .replace("'three'", JSON.stringify(import.meta.resolve('three')))
const { heightSplatFilter } = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)

test('height cut hides above-floor splats for positive and negative up axes', () => {
  for (const up of [[0, 1, 0], [0, -1, 0], [1, 0, 0], [0, 0, -1]]) {
    const upVector = new THREE.Vector3(...up)
    const edit = heightSplatFilter(up, -1.2, 1.5)
    assert.equal(edit.invert, true)
    assert.equal(edit.ordering, Number.MAX_SAFE_INTEGER)
    const world = new THREE.Group()
    world.quaternion.setFromUnitVectors(upVector, new THREE.Vector3(0, 1, 0))
    world.add(edit)
    world.updateMatrixWorld(true)
    const packed = new SplatEdits({ maxEdits: 1, maxSdfs: 1 })
    packed.update([{ edit, sdfs: edit.children }])
    assert.equal(packed.sdfFloatData[19], 0)
    const data = packed.sdfFloatData
    const offset = new THREE.Vector3().fromArray(data, 0)
    const rotation = new THREE.Quaternion().fromArray(data, 4)
    const scale = new THREE.Vector3().fromArray(data, 8)
    const distance = (height) => upVector.clone().multiplyScalar(-1.2 + height)
      .applyMatrix4(world.matrixWorld).multiply(scale).applyQuaternion(rotation).add(offset).z
    assert.ok(distance(1.4) < 0)
    assert.ok(distance(1.6) > 0)
  }
})
