import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'
import * as THREE from 'three'

const source = await readFile(new URL('../src/room/routeCurve.ts', import.meta.url), 'utf8')
const js = ts.transpile(source, { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 })
  .replace("'three'", JSON.stringify(import.meta.resolve('three')))
const { routeCurve } = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)

test('the robot follows the planned segments without cutting the corner', () => {
  const curve = routeCurve([new THREE.Vector3(0, 0, 0), new THREE.Vector3(1, 0, 0), new THREE.Vector3(1, 0, 1)])
  for (let i = 0; i <= 100; i += 1) {
    const p = curve.getPoint(i / 100)
    assert.ok(Math.abs(p.z) < 1e-9 || Math.abs(p.x - 1) < 1e-9)
  }
  assert.equal(curve.getLength(), 2)
})

test('a stationary route stays at its endpoint', () => {
  const point = new THREE.Vector3(1, 0, 2)
  assert.deepEqual(routeCurve([point, point.clone()]).getPoint(0.5).toArray(), point.toArray())
})
