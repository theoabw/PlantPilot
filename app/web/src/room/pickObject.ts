import * as THREE from 'three'

/** A press that moved further than this was a camera drag, not a click. */
export const CLICK_MAX_DRAG_PX = 6

/** A longer side than this on a structural box means it wraps the room. */
const ROOM_SIZED_SIDE_M = 2.2
const ROOM_CLASSES = new Set(['surface', 'structure'])

/** Whether a box is one thing to point at, or the shell around everything else. */
export function isPickable(
  object: { class: string; extents: [number, number, number] },
  mapped: boolean,
): boolean {
  return mapped || !ROOM_CLASSES.has(object.class) || Math.max(...object.extents) <= ROOM_SIZED_SIDE_M
}

/**
 * The box a ray means, from its hits nearest first. That is the nearest box,
 * unless a smaller one starts inside it: from outside a machine's frame, a part
 * framed inside it could otherwise never be picked. A box further along that
 * does not start inside the current one stays behind it and is not considered.
 */
export function nestedPick<T extends THREE.Intersection>(hits: T[]): T | null {
  let best: T | null = null
  let bestVolume = Infinity
  const local = new THREE.Vector3()
  for (const hit of hits) {
    const scale = hit.object.scale
    const volume = Math.abs(scale.x * scale.y * scale.z)
    if (best === null) {
      best = hit
      bestVolume = volume
      continue
    }
    best.object.worldToLocal(local.copy(hit.point))
    const inside = Math.max(Math.abs(local.x), Math.abs(local.y), Math.abs(local.z)) <= 0.5 + 1e-6
    if (inside && volume < bestVolume) {
      best = hit
      bestVolume = volume
    }
  }
  return best
}

/** How far in front of a box a surface has to be before it hides the box. */
const SURFACE_TOLERANCE_M = 0.25
/** One stray splat on the ray is a floater, not a wall. */
const SURFACE_MIN_SPLATS = 2

/** Whether the splats a ray crossed put a real surface in front of `distance`. */
export function hiddenBySplats(distance: number, splatDistances: number[]): boolean {
  let inFront = 0
  for (const splat of splatDistances) {
    if (splat < distance - SURFACE_TOLERANCE_M) {
      inFront += 1
    }
  }
  return inFront >= SURFACE_MIN_SPLATS
}
