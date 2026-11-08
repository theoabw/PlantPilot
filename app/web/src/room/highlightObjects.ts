import type { MappedAsset, RoomObject } from './api'

export function syntheticMappedObjects(objects: RoomObject[], mappings: MappedAsset[]): RoomObject[] {
  const mappedIds = new Set(mappings.flatMap((mapping) => mapping.object_id ? [mapping.object_id] : []))
  return objects.filter((object) => mappedIds.has(object.id))
}

export function proximityCandidates(
  objects: RoomObject[],
  syntheticObjects: RoomObject[],
  showSynthetic: boolean,
): RoomObject[] {
  if (!showSynthetic) {
    return objects
  }
  const ids = new Set(objects.map((object) => object.id))
  return [...objects, ...syntheticObjects.filter((object) => !ids.has(object.id))]
}

export function nearbyHighlightIds(
  reviewedIds: string[],
  nearbyIds: string[],
  syntheticObjects: RoomObject[],
): string[] {
  const syntheticIds = new Set(syntheticObjects.map((object) => object.id))
  return [...reviewedIds, ...nearbyIds.filter((id) => syntheticIds.has(id))]
}

export function syntheticFrameOpacity(id: string, nearby: Set<string>, moving: boolean): number {
  return moving && nearby.has(id) ? 1 : 0.55
}

/** Match nearby IDs to enabled boxes, preserving a separate selection. */
export function highlightObjects(
  objects: RoomObject[],
  frameObjects: RoomObject[],
  selectedId: string | null,
  nearbyIds: string[],
  showNearby: boolean,
  syntheticObjects: RoomObject[] = [],
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
    for (const object of [...objects, ...syntheticObjects]) {
      if (nearby.has(object.id) && !seen.has(object.id)) {
        result.push(object)
        seen.add(object.id)
      }
    }
  }
  return result
}
