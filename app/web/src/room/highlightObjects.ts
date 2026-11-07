import type { RoomObject } from './api'

/** Match the displayed nearby IDs to boxes, preserving a separate selection. */
export function highlightObjects(
  objects: RoomObject[],
  frameObjects: RoomObject[],
  selectedId: string | null,
  nearbyIds: string[],
  showNearby: boolean,
): RoomObject[] {
  const result: RoomObject[] = []
  const seen = new Set<string>()
  if (selectedId) {
    const selected = frameObjects.find((object) => object.id === selectedId)
      ?? objects.find((object) => object.id === selectedId)
    if (selected) {
      result.push(selected)
      seen.add(selected.id)
    }
  }
  if (showNearby) {
    const nearby = new Set(nearbyIds)
    for (const object of objects) {
      if (nearby.has(object.id) && !seen.has(object.id)) {
        result.push(object)
        seen.add(object.id)
      }
    }
  }
  return result
}
