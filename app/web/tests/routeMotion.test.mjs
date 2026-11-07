import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'

const source = await readFile(new URL('../src/room/routeMotion.ts', import.meta.url), 'utf8')
const js = ts.transpile(source, { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 })
const motion = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)

test('a capped step still advances by the limit toward the goal', () => {
  const next = motion.cappedStep({ x: 0, y: 0, z: 0 }, { x: 3, y: 0, z: 4 }, 0.5)
  assert.ok(Math.abs(next.x - 0.3) < 1e-9)
  assert.ok(Math.abs(next.z - 0.4) < 1e-9)
  assert.equal(next.y, 0)
})

test('a step under the limit lands on the goal', () => {
  assert.deepEqual(motion.cappedStep({ x: 0, y: 0, z: 0 }, { x: 0.1, y: 0.2, z: 0 }, 1), { x: 0.1, y: 0.2, z: 0 })
})

test('a repeated capped step closes a gap instead of freezing', () => {
  let at = { x: 0, y: 0, z: 0 }
  for (let frame = 0; frame < 100; frame += 1) {
    at = motion.cappedStep(at, { x: 5, y: 0, z: 0 }, 0.12)
  }
  assert.equal(at.x, 5)
})

test('a snapped waypoint never replaces the requested destination', () => {
  assert.deepEqual(motion.nextDestination([1, 2], [1.4, 2.6]), [1, 2])
  assert.deepEqual(motion.nextDestination(null, [1.4, 2.6]), [1.4, 2.6])
  assert.equal(motion.nextDestination(null, null), null)
})
