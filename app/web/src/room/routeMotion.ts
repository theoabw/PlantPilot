/**
 * Pure geometry for moving the robot and the follow camera along a route.
 *
 * Kept free of three.js and React so the rules can be tested in plain Node:
 * every function takes plain numbers or `{ x, y, z }` shaped objects.
 */

export type Point3 = { x: number; y: number; z: number }

/** The camera may not cover more than this per second while it tracks. */
export const CAMERA_MAX_SPEED_M_S = 1.6
/** The opening move onto the robot, or pulling the camera out of structure. */
export const CAMERA_FAST_SPEED_M_S = 4

/**
 * Move `from` toward `goal`, covering at most `maxStep` metres.
 *
 * The direction is taken before anything moves: a step that is over the limit
 * still has to advance by the limit, because a camera that stands still while
 * the robot walks away only ever sees a larger step on the next frame.
 */
export function cappedStep(from: Point3, goal: Point3, maxStep: number): Point3 {
  const dx = goal.x - from.x
  const dy = goal.y - from.y
  const dz = goal.z - from.z
  const length = Math.hypot(dx, dy, dz)
  if (length <= maxStep || length < 1e-9) {
    return { x: goal.x, y: goal.y, z: goal.z }
  }
  const scale = maxStep / length
  return { x: from.x + dx * scale, y: from.y + dy * scale, z: from.z + dz * scale }
}

/**
 * The point the next replan should aim for.
 *
 * A destination is what the user asked for: the object's centre, not the cell
 * the planner snapped it to for one robot. A snapped waypoint fed back into the
 * next plan moves the goal a little on every replan, and a wide robot's waypoint
 * stays far from the object after switching back to a narrow one. The waypoint
 * is only used when no destination was ever given, as with the shipped route.
 */
export function nextDestination(
  requested: [number, number] | null,
  waypoint: [number, number] | null,
): [number, number] | null {
  return requested ?? waypoint
}

/** A live robot further than this from a new route's start is not on it. */
export const ROUTE_JOIN_LIMIT_M = 1.5
/** Closer than this, the robot's position simply replaces the first point. */
const ROUTE_JOIN_MERGE_M = 0.05

/**
 * Join a new route to where the robot actually stands.
 *
 * The planner snaps its start to a free cell, and the robot may have stopped a
 * little after the request was sent, so the first path point is rarely under
 * the robot. Starting the curve from the robot means nothing jumps when a trip
 * begins. A robot too far away to be on this route keeps the route as planned.
 */
export function joinRouteToRobot<T extends Point3>(
  points: T[],
  robot: T | null,
): { points: T[]; offsetM: number } {
  if (!robot || points.length === 0) {
    return { points, offsetM: 0 }
  }
  const gap = Math.hypot(robot.x - points[0].x, robot.z - points[0].z)
  if (gap > ROUTE_JOIN_LIMIT_M) {
    return { points, offsetM: 0 }
  }
  if (gap < ROUTE_JOIN_MERGE_M) {
    return { points: [robot, ...points.slice(1)], offsetM: 0 }
  }
  return { points: [robot, ...points], offsetM: gap }
}

/** Heading of a tangent, or the current heading when there is no direction. */
export function headingFromTangent(x: number, z: number, current: number): number {
  return Math.hypot(x, z) < 1e-4 ? current : Math.atan2(x, z)
}

export type Point2 = { x: number; z: number }

/**
 * One manual walking step, sliding along whatever blocks it.
 *
 * Tries the whole step, then each axis alone, so walking into a wall at an angle
 * follows the wall. A character standing on a blocked cell can always step, or
 * nothing could ever get it out: changing to a wider robot blocks most of the
 * floor under the old position. Only the grid's edge still stops that step.
 */
export function slideStep(
  at: Point2,
  step: Point2,
  isFree: (point: Point2) => boolean,
  isOnGrid: (point: Point2) => boolean,
): Point2 | null {
  const whole = { x: at.x + step.x, z: at.z + step.z }
  if (!isFree(at)) {
    return isOnGrid(whole) ? whole : null
  }
  const candidates = [whole, { x: at.x + step.x, z: at.z }, { x: at.x, z: at.z + step.z }]
  for (const candidate of candidates) {
    if ((candidate.x !== at.x || candidate.z !== at.z) && isFree(candidate)) {
      return candidate
    }
  }
  return null
}

/** The camera does not count structure this close to what it looks at. */
const SIGHT_SKIP_FOCUS_M = 0.3
const SIGHT_SKIP_CAMERA_M = 0.15
const SIGHT_SAMPLE_M = 0.05

/**
 * Whether the line from the focus to a camera position crosses no structure.
 *
 * The ends are skipped: a robot beside a wall still has a usable view, and the
 * camera's own clearance has a separate test.
 */
export function sightClear(from: Point3, to: Point3, isBlocked: (point: Point3) => boolean): boolean {
  const length = Math.hypot(to.x - from.x, to.y - from.y, to.z - from.z)
  const samples = Math.max(3, Math.ceil(length / SIGHT_SAMPLE_M))
  for (let index = 1; index < samples; index += 1) {
    const ratio = index / samples
    const along = ratio * length
    if (along < SIGHT_SKIP_FOCUS_M || length - along < SIGHT_SKIP_CAMERA_M) {
      continue
    }
    const point = {
      x: from.x + (to.x - from.x) * ratio,
      y: from.y + (to.y - from.y) * ratio,
      z: from.z + (to.z - from.z) * ratio,
    }
    if (isBlocked(point)) {
      return false
    }
  }
  return true
}

/**
 * Ease a follow camera's offset toward a goal offset.
 *
 * The horizontal direction turns at a limited rate rather than blending, because
 * a straight blend between opposite offsets passes through the robot when it
 * reverses direction: the distance is eased on its own and never collapses.
 */
export function easeFollowOffset(
  offset: Point3,
  goal: Point3,
  dt: number,
  rate = 0.4,
  maxTurnRadPerS = 0.25,
): Point3 {
  const blend = 1 - Math.exp(-rate * dt)
  const angle = Math.atan2(offset.x, offset.z)
  let delta = Math.atan2(goal.x, goal.z) - angle
  while (delta > Math.PI) delta -= Math.PI * 2
  while (delta < -Math.PI) delta += Math.PI * 2
  const turn = Math.sign(delta) * Math.min(Math.abs(delta) * blend, maxTurnRadPerS * dt)
  const distance = Math.hypot(offset.x, offset.z)
  const reach = distance + (Math.hypot(goal.x, goal.z) - distance) * blend
  return {
    x: Math.sin(angle + turn) * reach,
    y: offset.y + (goal.y - offset.y) * blend,
    z: Math.cos(angle + turn) * reach,
  }
}

/** Turn a heading toward a target by a blend, the short way round. */
export function turnHeading(current: number, target: number, blend: number): number {
  let delta = target - current
  while (delta > Math.PI) delta -= Math.PI * 2
  while (delta < -Math.PI) delta += Math.PI * 2
  return current + delta * blend
}

/**
 * Map a distance along one cumulative table to the matching distance in another.
 *
 * The robot's progress is arc length along the spline, and the planner's crouch
 * spans are metres along its polyline. The two agree at the route's vertices and
 * drift between them, so the conversion goes through the vertices.
 */
export function remapAlong(value: number, from: number[], to: number[]): number {
  if (from.length === 0 || from.length !== to.length) {
    return value
  }
  if (value <= from[0]) {
    return to[0]
  }
  for (let index = 1; index < from.length; index += 1) {
    if (value <= from[index]) {
      const span = from[index] - from[index - 1]
      const ratio = span > 1e-9 ? (value - from[index - 1]) / span : 1
      return to[index - 1] + (to[index] - to[index - 1]) * ratio
    }
  }
  return to[to.length - 1]
}

/** The distance along a polyline nearest to a point, and how far off it is. */
export function nearestAlongPolyline(
  point: Point2,
  polyline: Point2[],
  cumulative: number[],
): { along: number; off: number } | null {
  if (polyline.length === 0 || polyline.length !== cumulative.length) {
    return null
  }
  let best = { along: cumulative[0], off: Math.hypot(point.x - polyline[0].x, point.z - polyline[0].z) }
  for (let index = 1; index < polyline.length; index += 1) {
    const a = polyline[index - 1]
    const b = polyline[index]
    const dx = b.x - a.x
    const dz = b.z - a.z
    const lengthSq = dx * dx + dz * dz
    const t = lengthSq > 1e-12 ? Math.max(0, Math.min(1, ((point.x - a.x) * dx + (point.z - a.z) * dz) / lengthSq)) : 0
    const off = Math.hypot(point.x - (a.x + dx * t), point.z - (a.z + dz * t))
    if (off < best.off) {
      best = { along: cumulative[index - 1] + (cumulative[index] - cumulative[index - 1]) * t, off }
    }
  }
  return best
}

export type Bounds2 = { minX: number; maxX: number; minZ: number; maxZ: number }

/**
 * A free-camera step that cannot carry it further out of the bounds.
 *
 * Each axis is judged alone, so it slides along the edge, and a camera already
 * outside, as in the room overview, can still move back in instead of snapping.
 */
export function boundedStep(at: Point2, step: Point2, bounds: Bounds2): Point2 {
  const axis = (value: number, delta: number, min: number, max: number): number => {
    const next = value + delta
    if ((next > max && delta > 0) || (next < min && delta < 0)) {
      return 0
    }
    return delta
  }
  return {
    x: axis(at.x, step.x, bounds.minX, bounds.maxX),
    z: axis(at.z, step.z, bounds.minZ, bounds.maxZ),
  }
}

/** A crouched stop has to be this much closer to be worth walking folded. */
export const CROUCH_STOP_GAIN_M = 0.3

type PlannedStop = {
  reachable: boolean
  target_waypoint_from?: string
  goal_snap_m?: number | null
}

/**
 * Whether a standing plan leaves a crouched one worth asking for: it was refused,
 * or it only reached ground short of the destination, which a lower body may
 * get closer to.
 */
export function shouldTryCrouched(standing: PlannedStop): boolean {
  return !standing.reachable || standing.target_waypoint_from === 'goal_override_reachable'
}

/**
 * Whether the crouched plan replaces the standing one. A refusal loses to
 * anything reachable; between two stops, crouching has to bring the robot
 * meaningfully closer, because it means walking folded for part of the route.
 */
export function prefersCrouched(standing: PlannedStop, crouched: PlannedStop): boolean {
  if (!crouched.reachable) {
    return false
  }
  if (!standing.reachable) {
    return true
  }
  const standingSnap = standing.goal_snap_m
  const crouchedSnap = crouched.goal_snap_m
  if (standingSnap === null || standingSnap === undefined || crouchedSnap === null || crouchedSnap === undefined) {
    return false
  }
  return standingSnap - crouchedSnap > CROUCH_STOP_GAIN_M
}

/**
 * What to tell the user about a route the planner refused.
 *
 * The planner only names an obstruction when one was placed, so an obstacle is
 * not blamed for a position that has no route to begin with.
 */
export function routeFailureText(reason: string): string {
  if (reason.includes('inspection point is blocked')) {
    return 'This robot cannot reach the pump: the inspection point is too tight.'
  }
  if (reason.includes('does not fit at its current position')) {
    return 'This robot does not fit at its current position.'
  }
  if (reason.includes('with this obstruction')) {
    return 'No safe path with the current obstacle.'
  }
  if (reason.includes('no walkable route')) {
    return 'No safe path from this position.'
  }
  return 'No safe route for this robot.'
}

/**
 * What to say when a route has nothing to drive. A reachable route with a single
 * point means the robot already stands at the stop, which is not a failure.
 */
export function routeStatusText(route: { reachable?: boolean; reason?: string | null } | null): string {
  if (route?.reachable) {
    return 'The robot is already at this stop.'
  }
  return routeFailureText(route?.reason ?? '')
}

/** What a plan request is for, beyond the route itself. */
export type PlanIntent = {
  target: [number, number] | null
  startAfter?: boolean
  label?: string
  tag?: string | null
  condition?: string | null
  objectId?: string | null
}

/** Destination metadata is committed only when the latest plan finishes. */
export type DestinationPlanState = {
  committed: PlanIntent
  pending: PlanIntent | null
}

type DestinationPlanAction =
  | { type: 'begin'; intent: PlanIntent }
  | { type: 'commit'; intent: PlanIntent; waypoint: [number, number] | null }
  | { type: 'cancel' }

/** Replans inherit the pending goal, but cancellation falls back to the committed one. */
export function destinationTarget(state: DestinationPlanState): [number, number] | null {
  return state.pending?.target ?? state.committed.target
}

/** Keep a pending request separate from the destination of the route still in use. */
export function transitionDestinationPlan(
  state: DestinationPlanState,
  action: DestinationPlanAction,
): DestinationPlanState {
  if (action.type === 'begin') {
    return { ...state, pending: supersedePlan(state.pending, action.intent) }
  }
  if (action.type === 'cancel') {
    return { ...state, pending: null }
  }
  // A cancelled or superseded response cannot publish its destination metadata.
  if (state.pending !== action.intent) {
    return state
  }
  const intent = action.intent
  return {
    committed: {
      target: nextDestination(intent.target, action.waypoint),
      label: intent.label || state.committed.label,
      tag: intent.tag !== undefined ? intent.tag : state.committed.tag,
      condition: intent.condition !== undefined ? intent.condition : state.committed.condition,
      objectId: intent.objectId !== undefined ? intent.objectId : state.committed.objectId,
    },
    pending: null,
  }
}

const SAME_DESTINATION_M = 0.001

/**
 * The intent of a request that replaces one still waiting for its answer.
 *
 * Only the latest answer is used, so a Start followed by an obstacle replan to
 * the same destination must carry the Start along, or the robot never leaves.
 * What was pending describes that destination and wins over what the newer
 * request filled in from the state of the previous trip. A different destination
 * is a new decision and owes the old request nothing.
 */
export function supersedePlan(pending: PlanIntent | null, next: PlanIntent): PlanIntent {
  if (!pending) {
    return next
  }
  const same =
    pending.target && next.target
      ? Math.hypot(pending.target[0] - next.target[0], pending.target[1] - next.target[1]) < SAME_DESTINATION_M
      : pending.target === next.target
  if (!same) {
    return next
  }
  return {
    target: next.target,
    startAfter: Boolean(pending.startAfter || next.startAfter),
    label: pending.label ?? next.label,
    tag: pending.tag !== undefined ? pending.tag : next.tag,
    condition: pending.condition !== undefined ? pending.condition : next.condition,
    objectId: pending.objectId !== undefined ? pending.objectId : next.objectId,
  }
}
