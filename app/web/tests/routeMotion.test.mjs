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

test('a diagonal cannot slip through the corner between blocked cells', () => {
  const free = (point) => (point.x < 1 && point.z < 1) || (point.x >= 1 && point.z >= 1)
  assert.equal(motion.slideStep({ x: 0.99, z: 0.99 }, { x: 0.02, z: 0.02 }, free, () => false), null)
})

test('a character on a blocked cell can only step in an allowed escape direction', () => {
  const free = () => false
  assert.deepEqual(motion.slideStep({ x: 0, z: 0 }, { x: 0.1, z: 0 }, free, () => true), { x: 0.1, z: 0 })
  assert.equal(motion.slideStep({ x: 0, z: 0 }, { x: 0.1, z: 0 }, free, () => false), null)
})

test('a sight line is blocked by structure between the ends', () => {
  const wall = (point) => Math.abs(point.x - 1) < 0.06
  assert.equal(motion.sightClear({ x: 0, y: 1, z: 0 }, { x: 2, y: 1, z: 0 }, wall), false)
  assert.equal(motion.sightClear({ x: 0, y: 1, z: 0 }, { x: 0.8, y: 1, z: 0 }, wall), true)
})

test('structure right beside the focus does not block the sight line', () => {
  const wallAtFocus = (point) => point.x < 0.2
  assert.equal(motion.sightClear({ x: 0, y: 1, z: 0 }, { x: 2, y: 1, z: 0 }, wallAtFocus), true)
})

test('easing between opposite offsets keeps the camera away from the robot', () => {
  let offset = { x: 0, y: 0.8, z: -2 }
  for (let frame = 0; frame < 600; frame += 1) {
    offset = motion.easeFollowOffset(offset, { x: 0, y: 0.8, z: 2 }, 1 / 60)
    assert.ok(Math.hypot(offset.x, offset.z) > 1.9)
  }
  assert.ok(offset.z > 1)
})

test('a heading turns the short way across the wrap', () => {
  const next = motion.turnHeading(3, -3, 0.5)
  assert.ok(next > 3)
  assert.ok(Math.abs(motion.turnHeading(0, 1, 1) - 1) < 1e-9)
})

test('arc length converts to polyline metres through the vertices', () => {
  const arc = [0, 1.2, 2.5]
  const line = [0, 1, 2]
  assert.ok(Math.abs(motion.remapAlong(0.6, arc, line) - 0.5) < 1e-9)
  assert.ok(Math.abs(motion.remapAlong(1.85, arc, line) - 1.5) < 1e-9)
  assert.equal(motion.remapAlong(9, arc, line), 2)
  assert.equal(motion.remapAlong(-1, arc, line), 0)
})

test('a position maps to the nearest place along the polyline', () => {
  const polyline = [{ x: 0, z: 0 }, { x: 2, z: 0 }, { x: 2, z: 2 }]
  const hit = motion.nearestAlongPolyline({ x: 2.1, z: 1 }, polyline, [0, 2, 4])
  assert.ok(Math.abs(hit.along - 3) < 1e-9)
  assert.ok(Math.abs(hit.off - 0.1) < 1e-9)
  assert.equal(motion.nearestAlongPolyline({ x: 0, z: 0 }, [], []), null)
})

test('the free camera slides along the bounds and can come back in', () => {
  const bounds = { minX: 0, maxX: 10, minZ: 0, maxZ: 10 }
  assert.deepEqual(motion.boundedStep({ x: 9.95, z: 5 }, { x: 0.1, z: 0.1 }, bounds), { x: 0, z: 0.1 })
  assert.deepEqual(motion.boundedStep({ x: 12, z: 5 }, { x: -0.1, z: 0 }, bounds), { x: -0.1, z: 0 })
  assert.deepEqual(motion.boundedStep({ x: 12, z: 5 }, { x: 0.1, z: 0 }, bounds), { x: 0, z: 0 })
})

test('a crouched plan is tried when standing was refused or stopped short', () => {
  assert.equal(motion.shouldTryCrouched({ reachable: false }), true)
  assert.equal(motion.shouldTryCrouched({ reachable: true, target_waypoint_from: 'goal_override_reachable' }), true)
  assert.equal(motion.shouldTryCrouched({ reachable: true, target_waypoint_from: 'goal_override' }), false)
  assert.equal(motion.shouldTryCrouched({ reachable: true }), false)
})

test('crouching wins only for a refusal or a meaningfully closer stop', () => {
  const standing = { reachable: true, goal_snap_m: 2.71 }
  assert.equal(motion.prefersCrouched(standing, { reachable: true, goal_snap_m: 1.22 }), true)
  assert.equal(motion.prefersCrouched(standing, { reachable: true, goal_snap_m: 2.5 }), false)
  assert.equal(motion.prefersCrouched(standing, { reachable: false, goal_snap_m: 0 }), false)
  assert.equal(motion.prefersCrouched({ reachable: false }, { reachable: true }), true)
  assert.equal(motion.prefersCrouched({ reachable: false }, { reachable: false }), false)
  assert.equal(motion.prefersCrouched({ reachable: true }, { reachable: true, goal_snap_m: 0 }), false)
})

test('a refusal only blames an obstacle when the planner names one', () => {
  assert.equal(motion.routeFailureText('no walkable route with this obstruction'), 'No safe path with the current obstacle.')
  assert.equal(motion.routeFailureText('no walkable route from this position'), 'No safe path from this position.')
  assert.equal(motion.routeFailureText(''), 'No safe route for this robot.')
})

test('a newer request to the same destination keeps the pending start and labels', () => {
  const pending = { target: [1, 2], startAfter: true, label: 'Pump', tag: 'P-005', condition: 'Fault', objectId: 'A' }
  const merged = motion.supersedePlan(pending, { target: [1, 2] })
  assert.deepEqual(merged, { ...pending, target: [1, 2] })
})

test('a newer request to another destination replaces the pending one', () => {
  const next = { target: [5, 5], label: 'Motor' }
  assert.equal(motion.supersedePlan({ target: [1, 2], startAfter: true, label: 'Pump' }, next), next)
  assert.equal(motion.supersedePlan(null, next), next)
})

test('the pending labels win over ones filled in from the previous trip', () => {
  const merged = motion.supersedePlan({ target: [1, 2], label: 'Pump', tag: null }, { target: [1, 2], label: 'Old', tag: 'OLD', startAfter: true })
  assert.equal(merged.label, 'Pump')
  assert.equal(merged.tag, null)
  assert.equal(merged.startAfter, true)
})

const destinationA = {
  target: [1, 2], label: 'Pump A', tag: 'P-A', condition: 'Watch', objectId: 'A',
}
const destinationB = {
  target: [3, 4], label: 'Motor B', tag: 'M-B', condition: 'Healthy', objectId: 'B',
}
const destinationC = {
  target: [5, 6], label: 'Valve C', tag: 'V-C', condition: 'Fault', objectId: 'C',
}

function withCommittedDestination(intent) {
  const planning = motion.transitionDestinationPlan({ committed: { target: null }, pending: null }, {
    type: 'begin', intent,
  })
  return motion.transitionDestinationPlan(planning, {
    type: 'commit', intent: planning.pending, waypoint: [9, 9],
  })
}

for (const control of ['Reset', 'Manual control']) {
  test(`${control} during a pending destination restores the committed goal for Start`, () => {
    let state = withCommittedDestination(destinationA)
    state = motion.transitionDestinationPlan(state, { type: 'begin', intent: { ...destinationB, startAfter: true } })
    const cancelled = state.pending
    assert.deepEqual(motion.destinationTarget(state), destinationB.target)
    assert.deepEqual(state.committed, destinationA)

    // Both controls discard the pending plan without publishing its metadata.
    state = motion.transitionDestinationPlan(state, { type: 'cancel' })
    assert.deepEqual(motion.destinationTarget(state), destinationA.target)
    assert.deepEqual(state.committed, destinationA)
    const afterCancel = state
    assert.equal(motion.transitionDestinationPlan(state, {
      type: 'commit', intent: cancelled, waypoint: [3.2, 4.2],
    }), afterCancel)

    state = motion.transitionDestinationPlan(state, {
      type: 'begin', intent: { ...state.committed, target: motion.destinationTarget(state), startAfter: true },
    })
    assert.deepEqual(state.pending, { ...destinationA, startAfter: true })
    state = motion.transitionDestinationPlan(state, { type: 'commit', intent: state.pending, waypoint: [1.2, 2.2] })
    // The coordinates, labels, condition and arrival-facing object all stay on A.
    assert.deepEqual(state.committed, destinationA)
    assert.equal(state.pending, null)
  })
}

test('overlapping requests that fail restore the last committed destination, not an uncommitted one', () => {
  let state = withCommittedDestination(destinationA)
  state = motion.transitionDestinationPlan(state, { type: 'begin', intent: { ...destinationB, startAfter: true } })
  const superseded = state.pending
  state = motion.transitionDestinationPlan(state, { type: 'begin', intent: { ...destinationC, startAfter: true } })
  const failed = state.pending
  assert.deepEqual(motion.destinationTarget(state), destinationC.target)
  assert.equal(motion.transitionDestinationPlan(state, {
    type: 'commit', intent: superseded, waypoint: destinationB.target,
  }), state)

  // A final request failure takes the same discard transition as cancellation.
  state = motion.transitionDestinationPlan(state, { type: 'cancel' })
  assert.deepEqual(state.committed, destinationA)
  assert.deepEqual(motion.destinationTarget(state), destinationA.target)
  assert.equal(state.pending, null)
  assert.equal(motion.transitionDestinationPlan(state, {
    type: 'commit', intent: failed, waypoint: destinationC.target,
  }), state)
  state = motion.transitionDestinationPlan(state, {
    type: 'begin', intent: { target: motion.destinationTarget(state), startAfter: true },
  })
  state = motion.transitionDestinationPlan(state, { type: 'commit', intent: state.pending, waypoint: [1.1, 2.1] })
  assert.deepEqual(state.committed, destinationA)
})

test('a replacement replan inherits the pending destination and commits its metadata together', () => {
  let state = withCommittedDestination(destinationA)
  state = motion.transitionDestinationPlan(state, { type: 'begin', intent: { ...destinationB, startAfter: true } })
  state = motion.transitionDestinationPlan(state, {
    type: 'begin', intent: { ...destinationA, target: motion.destinationTarget(state) },
  })
  assert.deepEqual(state.pending, { ...destinationB, startAfter: true })
  assert.deepEqual(state.committed, destinationA)
  state = motion.transitionDestinationPlan(state, { type: 'commit', intent: state.pending, waypoint: [3.2, 4.2] })
  assert.deepEqual(state.committed, destinationB)
  assert.deepEqual(motion.destinationTarget(state), destinationB.target)
  assert.equal(state.pending, null)
})

test('committing metadata preserves omitted fields but honors explicit nulls', () => {
  let state = withCommittedDestination(destinationA)
  state = motion.transitionDestinationPlan(state, {
    type: 'begin', intent: { target: destinationA.target, tag: null, condition: null, objectId: null },
  })
  state = motion.transitionDestinationPlan(state, { type: 'commit', intent: state.pending, waypoint: null })
  assert.deepEqual(state.committed, {
    target: destinationA.target, label: destinationA.label, tag: null, condition: null, objectId: null,
  })
})

test('a reachable route with nowhere to go says the robot is there, not that it failed', () => {
  assert.equal(motion.routeStatusText({ reachable: true, reason: null }), 'The robot is already at this stop.')
  assert.equal(
    motion.routeStatusText({ reachable: false, reason: 'no walkable route from this position' }),
    'No safe path from this position.',
  )
  assert.equal(motion.routeStatusText(null), 'No safe route for this robot.')
})
