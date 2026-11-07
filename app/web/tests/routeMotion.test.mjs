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

test('a new route starts from the robot, not from the planned first point', () => {
  const robot = { x: 0, y: 0, z: 0, id: 'robot' }
  const path = [{ x: 0.3, y: 0, z: 0.4 }, { x: 3, y: 0, z: 0 }]
  const joined = motion.joinRouteToRobot(path, robot)
  assert.equal(joined.points[0], robot)
  assert.equal(joined.points.length, 3)
  assert.ok(Math.abs(joined.offsetM - 0.5) < 1e-9)
})

test('a robot almost on the first point replaces it instead of adding a stub', () => {
  const robot = { x: 0, y: 0, z: 0 }
  const joined = motion.joinRouteToRobot([{ x: 0.01, y: 0, z: 0 }, { x: 3, y: 0, z: 0 }], robot)
  assert.equal(joined.points.length, 2)
  assert.equal(joined.points[0], robot)
  assert.equal(joined.offsetM, 0)
})

test('a robot far from the route does not get a line through the room', () => {
  const path = [{ x: 5, y: 0, z: 0 }, { x: 6, y: 0, z: 0 }]
  assert.equal(motion.joinRouteToRobot(path, { x: 0, y: 0, z: 0 }).points, path)
})

test('a path with no direction keeps the current heading', () => {
  assert.equal(motion.headingFromTangent(0, 0, 1.25), 1.25)
  assert.ok(Math.abs(motion.headingFromTangent(1, 0, 0) - Math.PI / 2) < 1e-9)
})

test('a blocked diagonal step slides along the wall', () => {
  const free = (point) => point.x < 1
  const onGrid = () => true
  const next = motion.slideStep({ x: 0.95, z: 0 }, { x: 0.1, z: 0.1 }, free, onGrid)
  assert.deepEqual(next, { x: 0.95, z: 0.1 })
})

test('head-on into a wall does not move', () => {
  const free = (point) => point.x < 1
  assert.equal(motion.slideStep({ x: 0.95, z: 0 }, { x: 0.1, z: 0 }, free, () => true), null)
})

test('a character on a blocked cell can walk out, but not off the grid', () => {
  const free = () => false
  assert.deepEqual(motion.slideStep({ x: 0, z: 0 }, { x: 0.1, z: 0 }, free, () => true), { x: 0.1, z: 0 })
  assert.equal(motion.slideStep({ x: 0, z: 0 }, { x: 0.1, z: 0 }, free, () => false), null)
})
