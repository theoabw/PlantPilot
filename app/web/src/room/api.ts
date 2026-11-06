// Types and fetchers for the room view. The artifacts are written by make scene,
// make objects and make splat-asset; their contract is docs/scene-artifacts.md.

export type RoomObject = {
  id: string
  centre: [number, number, number]
  axes: [number, number, number][]
  extents: [number, number, number]
  points: number
  class: string
  class_confidence: number
  class_reason: string
  height_above_floor: number
  volume_m3: number
  planarity: number
}

export type RoomObjects = {
  artifact: string
  version: number
  source: { points: number; up_axis: string; units: string }
  floor: { detected: boolean; height: number | null; normal: number[] | null }
  counts: {
    objects: number
    largest_object_share: number
    median_points_per_object: number
    points_in_objects_fraction: number
    objects_by_class: Record<string, number>
  }
  scale_check: { performed: boolean; units_are_metres: boolean; reason: string }
  timing_s: number
  objects: RoomObject[]
}

export const SPLAT_URL = '/api/splat'

export async function fetchRoomObjects(): Promise<RoomObjects> {
  const response = await fetch('/api/scene/objects')
  if (!response.ok) {
    throw new Error(
      response.status === 404
        ? 'no objects artifact on the server, run make objects'
        : `/api/scene/objects answered ${response.status}`,
    )
  }
  return (await response.json()) as RoomObjects
}

export function splatAssetUrl(): string {
  return SPLAT_URL
}

/** The scene's up axis as a unit vector, from "+y" or "-y" style metadata. */
export function upVector(axis: string | undefined): [number, number, number] {
  const value = (axis ?? '+y').trim().toLowerCase()
  const sign = value.startsWith('-') ? -1 : 1
  const name = value.replace(/^[+-]/, '')
  const vectors: Record<string, [number, number, number]> = {
    x: [1, 0, 0],
    y: [0, 1, 0],
    z: [0, 0, 1],
  }
  const vector = vectors[name] ?? vectors.y
  return [vector[0] * sign, vector[1] * sign, vector[2] * sign]
}

export const CLASS_COLOURS: Record<string, string> = {
  pump: '#ff6060',
  motor: '#ffa040',
  valve: '#ffe060',
  pipe: '#60c8ff',
  duct: '#60ffc8',
  door: '#c878ff',
  drum: '#ff78dc',
  pallet: '#b4ff60',
  cabinet: '#8caaff',
  panel: '#ffbe8c',
  ladder: '#96ffc8',
  beam: '#96c8dc',
  tray: '#c8c878',
  machine: '#f0f0f0',
  structure: '#aaaaaa',
  surface: '#778899',
  unknown: '#969696',
}
