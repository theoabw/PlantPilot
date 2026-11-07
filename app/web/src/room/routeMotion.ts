/**
 * Pure geometry for moving the robot and the follow camera along a route.
 *
 * Kept free of three.js and React so the rules can be tested in plain Node:
 * every function takes plain numbers or `{ x, y, z }` shaped objects.
 */

export type Point3 = { x: number; y: number; z: number }

/** The camera may not cover more than this per second while it tracks. */
export const CAMERA_MAX_SPEED_M_S = 7.2

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
  rate = 0.8,
  maxTurnRadPerS = 0.7,
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
