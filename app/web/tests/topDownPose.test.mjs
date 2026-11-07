import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'
import * as THREE from 'three'

const source = await readFile(new URL('../src/room/topDownPose.ts', import.meta.url), 'utf8')
const js = ts.transpile(source, { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 })
  .replace("'three'", JSON.stringify(import.meta.resolve('three')))
const { topDownPose } = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)

test('top-down pose respects room orientation and narrower viewport', () => {
  const objects = [
    { centre: [-2, 0, 0], axes: [[1, 0, 0], [0, 1, 0], [0, 0, 1]], extents: [2, 2, 2] },
    { centre: [2, 0, 0], axes: [[0, 0, 1], [0, 1, 0], [-1, 0, 0]], extents: [2, 2, 2] },
  ]
  const upright = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), Math.PI)
  const wide = topDownPose(objects, upright, 60, 2)
  const narrow = topDownPose(objects, upright, 60, 0.5)
  assert.ok(wide.eye.y > wide.target.y)
  assert.ok(Math.abs(wide.eye.x - wide.target.x) < 1e-9)
  assert.ok(narrow.eye.y > wide.eye.y)
  assert.throws(() => topDownPose([], upright, 60, 1), /object bounds/)
})
