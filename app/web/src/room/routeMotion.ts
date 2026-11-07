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
