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
  // Present when the record comes from the refined assets artifact rather
  // than the raw extraction.
  label?: string
  verified?: boolean
  confidence?: number
  source_object_ids?: string[]
  method?: string
  reviewed?: boolean
  observed_type?: string
  inferred_function?: string
  category?: string
  classification_confidence?: 'high' | 'medium' | 'low'
  evidence?: string
}

export type RoomAnchor = {
  id: string
  asset_id: string
  class: string
  label: string
  reviewed: boolean
  verdict: string
  note: string
  centre: [number, number, number]
  axes: [number, number, number][]
  extents: [number, number, number]
  points: number
  mean_rgb?: number[] | null
  source_object_ids: string[]
  observed_type?: string
  inferred_function?: string
  category?: string
  classification_confidence?: 'high' | 'medium' | 'low'
  evidence?: string
}

export type RoomAnchors = {
  artifact: string
  version: number
  source?: { scene?: string; fixture?: string }
  counts: { anchors: number }
  anchors: RoomAnchor[]
}

export type RoomAsset = {
  id: string
  class: string
  label: string
  confidence: number
  verified: boolean
  centre: [number, number, number]
  axes: [number, number, number][]
  extents: [number, number, number]
  points: number
  rgb?: [number, number, number] | null
  source_object_ids: string[]
  method: string
  reason: string
}

export type RoomAssets = {
  artifact: string
  version: number
  source: { scene: string; capture?: string | null; objects?: string }
  counts: {
    raw_objects: number
    colour_instances: number
    geometry_candidates: number
    suppressed: number
    assets: number
    verified: number
  }
  assets: RoomAsset[]
}

export type RoomRoute = {
  reachable: boolean
  reason?: string
  target_asset_id: string
  target_waypoint: number[]
  start: number[]
  path: number[][]
  path_samples?: { point: number[] }[]
  distance_m: number
  clearance_m: number
  floor_height_m: number
  up_axis: string
  active_blockers?: number[][]
  planned_height_m?: number
  crouch_spans_m?: [number, number][]
  camera_grid?: {
    x0: number
    z0: number
    cell_m: number
    rows: number
    cols: number
    horizontal_axes: number[]
    blocked_packed: string
    camera_band_m?: number[]
    camera_blocked_cells?: number
  }
  grid_stats?: {
    cols?: number
    rows?: number
    resolution_m?: number
    blocked_fraction?: number
    blocked_cells?: number
    structural_blocked_cells?: number
    object_blocked_cells?: number
    obstacles_from?: string
  }
  grid?: {
    x0: number
    z0: number
    cell_m: number
    rows: number
    cols: number
    horizontal_axes: number[]
    blocked_packed: string
  }
}

export type DiagnosisEvidence = {
  evidence_id?: string
  ref: string
  kind: 'telemetry' | 'alarm' | 'data_quality' | 'document'
  label: string
  detail?: string
  value?: unknown
}

export type DiagnosisTrend = {
  available: boolean
  metric: string
  unit: string
  issue_code: string
  why: string
  points: { timestamp: string; value: number }[]
  summary?: {
    first: number
    last: number
    change: number
    change_percent: number
    min: number
    max: number
    slope_per_sample: number
  }
  reason?: string
}

export type DiagnosisCitation = {
  doc_id: string
  title: string
  scope?: string
  section?: string | null
  page?: number | null
  excerpt?: string
  excerpt_words?: number
  synthetic_record?: boolean
}

export type DiagnosisFinding = {
  finding_id: string
  type: string
  statement: string
  evidence_ids: string[]
  confidence: number
  evidence?: DiagnosisEvidence[]
}

export type ReasoningClaim = {
  claim_id: string
  kind: 'observation' | 'inference' | 'action'
  text: string
  refs: string[]
  confidence?: number
}

export type ReasoningDifferential = {
  hypothesis: string
  verdict: 'supported' | 'less likely' | 'cannot separate'
  because: string
  refs: string[]
}

export type Reasoning = {
  generated_by: string
  claims: ReasoningClaim[]
  differential: ReasoningDifferential[]
  guardrail: { claims: number; cited: number; unsupported: number; refs_resolved: number }
}

export type Diagnosis = {
  available: boolean
  reason?: string
  target?: { asset_id: string; tag: string; class: string; area?: string }
  condition?: string
  health_score?: number
  issue?: { code: string; summary: string; urgency: string }
  findings?: DiagnosisFinding[]
  trend?: DiagnosisTrend | null
  next_safe_check?: { action: string; document_id: string; reason: string }
  citations?: DiagnosisCitation[]
  // Written by the reasoning stage when the artifact carries one. Older
  // artifacts stop after citations, and the card renders the same either way.
  reasoning?: Reasoning
  data_quality?: {
    confidence_effect?: string
    severity_counts?: Record<string, number>
    cases?: unknown[]
  }
}

export type RoomCamera = {
  eye: [number, number, number]
  target: [number, number, number]
  up: [number, number, number]
}

export type RoomObjects = {
  artifact: string
  version: number
  source: { scene: string; capture?: string | null; points: number; up_axis: string; units: string }
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
  camera?: RoomCamera | null
  objects: RoomObject[]
}

export type MappedAsset = {
  asset_id: string
  tag: string
  object_id: string | null
  status?: 'proposed' | 'unresolved'
  match_score?: number | null
  reason?: string | null
  class: string
  state: 'healthy' | 'degraded' | 'watch' | 'attention_required'
  issue_code: string
  method: string
  confidence: number | null
  object_class_proposal: string | null
}

export type RoomMapped = {
  artifact: string
  version: number
  counts: { assets: number; mapped: number; unresolved?: number; unmapped_objects: number }
  target_asset_id: string
  target_tag: string
  target_object_id: string | null
  mappings: MappedAsset[]
  unmapped_object_ids: string[]
}

export const SPLAT_URL = '/api/splat'

export type RoomObjectSplat = {
  anchor_id: string
  label: string
  class?: string
  file: string
  gaussians: number
}

export type RoomObjectSplats = {
  artifact: string
  version: number
  capture?: string
  counts?: { objects?: number; gaussians?: number }
  objects: RoomObjectSplat[]
}

export async function fetchRoomObjectSplats(): Promise<RoomObjectSplats> {
  const response = await fetch('/api/scene/object-splats')
  if (!response.ok) {
    throw new Error(
      response.status === 404
        ? 'no per-object splats on the server, run make object-splats'
        : `/api/scene/object-splats answered ${response.status}`,
    )
  }
  return (await response.json()) as RoomObjectSplats
}

export function objectSplatUrl(anchorId: string): string {
  return `/api/object-splat/${anchorId}`
}

export type RoomMesh = {
  anchor_id: string
  label: string
  class?: string
  file: string
  vertices: number
  triangles: number
  owned_gaussians?: number
}

export type RoomMeshes = {
  artifact: string
  version: number
  source?: { scene?: string; anchors?: string }
  counts?: { objects?: number }
  objects: RoomMesh[]
}

export async function fetchRoomMeshes(): Promise<RoomMeshes> {
  const response = await fetch('/api/scene/meshes')
  if (!response.ok) {
    throw new Error(
      response.status === 404
        ? 'no object meshes on the server, run make object-meshes'
        : `/api/scene/meshes answered ${response.status}`,
    )
  }
  return (await response.json()) as RoomMeshes
}

export function meshAssetUrl(anchorId: string): string {
  return `/api/mesh/${anchorId}`
}

export type RoomFilters = {
  artifact: string
  version: number
  source?: { scene?: string; objects?: string; assets?: string }
  filters: { applied: string[] }
  geometry?: Record<string, unknown>
  variants?: Record<string, unknown>
}

export async function fetchRoomFilters(): Promise<RoomFilters> {
  const response = await fetch('/api/scene/filters')
  if (!response.ok) {
    throw new Error(
      response.status === 404
        ? 'no baked filter assets on the server, run make filter-assets'
        : `/api/scene/filters answered ${response.status}`,
    )
  }
  return (await response.json()) as RoomFilters
}

export function filterAssetUrl(name: string): string {
  // edges and semantics sit on a dimmed capture: edges adds thin contours,
  // semantics adds the pastel anchor overlay and object contours
  return name === 'edges' || name === 'semantics' ? '/api/filter/edges_base' : `/api/filter/${name}`
}

export async function fetchRoomAnchors(): Promise<RoomAnchors> {
  const response = await fetch('/api/scene/anchors')
  if (!response.ok) {
    throw new Error(
      response.status === 404
        ? 'no reviewed anchor layer on the server, run make anchors'
        : `/api/scene/anchors answered ${response.status}`,
    )
  }
  return (await response.json()) as RoomAnchors
}

export async function fetchRoomAssets(): Promise<RoomAssets> {
  const response = await fetch('/api/scene/assets')
  if (!response.ok) {
    throw new Error(
      response.status === 404
        ? 'no assets artifact on the server, run make assets'
        : `/api/scene/assets answered ${response.status}`,
    )
  }
  return (await response.json()) as RoomAssets
}

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

export function splatAssetUrl(version?: number): string {
  // The asset URL has to change when the capture changes, otherwise the browser
  // serves a cached splat from the previous scene.
  return version ? `${SPLAT_URL}?v=${version}` : SPLAT_URL
}

/** The navigation route, or null when make route has not run yet. */
export async function fetchReroute(
  blockers: number[][],
  start: [number, number] | null,
  agentRadiusM = 0.2,
  agentHeightM = 0.55,
  options: { target?: [number, number] | null; standingHeightM?: number | null } = {},
): Promise<RoomRoute> {
  const response = await fetch('/api/scene/reroute', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      blockers,
      start,
      agent_radius_m: agentRadiusM,
      agent_height_m: agentHeightM,
      target: options.target ?? null,
      standing_height_m: options.standingHeightM ?? null,
    }),
  })
  if (!response.ok) {
    throw new Error(`/api/scene/reroute answered ${response.status}`)
  }
  return (await response.json()) as RoomRoute
}

export async function fetchRoomRoute(): Promise<RoomRoute | null> {
  const response = await fetch('/api/scene/route')
  if (response.status === 404) {
    return null
  }
  if (!response.ok) {
    throw new Error(`/api/scene/route answered ${response.status}`)
  }
  return (await response.json()) as RoomRoute
}

/** The diagnosis for the target asset, or null when make diagnose has not run. */
export async function fetchDiagnosis(): Promise<Diagnosis | null> {
  const response = await fetch('/api/diagnosis')
  if (!response.ok) {
    return null
  }
  const body = (await response.json()) as Diagnosis
  return body.available ? body : null
}

/** The mapping artifact, or null when make map has not run yet. */
export async function fetchRoomMapped(): Promise<RoomMapped | null> {
  const response = await fetch('/api/scene/mapped')
  if (response.status === 404) {
    return null
  }
  if (!response.ok) {
    throw new Error(`/api/scene/mapped answered ${response.status}`)
  }
  return (await response.json()) as RoomMapped
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

export const STATE_COLOURS: Record<string, string> = {
  healthy: '#22c55e',
  watch: '#f59e0b',
  degraded: '#fb923c',
  attention_required: '#ef4444',
}

export const STATE_LABEL: Record<string, string> = {
  healthy: 'healthy',
  watch: 'watch',
  degraded: 'degraded',
  attention_required: 'attention',
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
