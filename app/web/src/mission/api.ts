// Types and fetchers for the mission view. The backend contract lives in
// app/server/src/plantpilot/main.py.

export type Asset = {
  id: string
  kind: string
  pos: [number, number, number]
  size: [number, number, number]
  shape?: string
  waypoint: [number, number]
  tag: string
  interval: string
  last_service: string
  criticality: string
  type?: string
  dn?: string
  pn?: string
}

export type Plant = {
  name: string
  note: string
  source: string
  area: { x0: number; x1: number; z0: number; z1: number; height: number }
  door: { x0: number; x1: number; z: number }
  start: [number, number]
  assets: Asset[]
  aisles: { id: string; points: [number, number][]; width: number }[]
  blockers: { id: string; label: string; pos: [number, number, number]; size: [number, number, number] }[]
}

export type RouteResult = {
  reachable: boolean
  path: [number, number][]
  distance_m?: number
  clearance_m?: number
  reason?: string
  cells?: number
}

export type Cloud = { positions: Float32Array; colors: Uint8Array; count: number }

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init)
  if (!response.ok) {
    throw new Error(`${url} answered ${response.status}`)
  }
  return (await response.json()) as T
}

export const fetchPlant = () => json<Plant>('/api/plant')

export async function fetchCloud(): Promise<Cloud> {
  const meta = await json<{ available: boolean; count: number }>('/api/cloud/meta')
  if (!meta.available || meta.count === 0) {
    throw new Error('no cloud generated, run make plant')
  }
  const response = await fetch('/api/cloud')
  if (!response.ok) {
    throw new Error(`/api/cloud answered ${response.status}`)
  }
  const buffer = await response.arrayBuffer()
  const count = meta.count
  const positions = new Float32Array(buffer, 0, count * 3)
  const colors = new Uint8Array(buffer, count * 12, count * 3)
  return { positions, colors, count }
}

export function fetchRoute(to: string, blockers: number[][] = []): Promise<RouteResult> {
  return json<RouteResult>('/api/route', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ to, blockers }),
  })
}

export type Inspection = { asset: Asset; dueInDays: number }

// A work order is derived, not invented: last service plus the service interval.
export function inspections(assets: Asset[]): Inspection[] {
  const now = new Date('2026-11-06T00:00:00Z').getTime()
  return assets
    .map((asset) => {
      const years = asset.interval.includes('4') ? 4 : 1
      const last = new Date(`${asset.last_service}T00:00:00Z`).getTime()
      const due = last + years * 365 * 24 * 3600 * 1000
      return { asset, dueInDays: Math.round((due - now) / (24 * 3600 * 1000)) }
    })
    .sort((a, b) => a.dueInDays - b.dueInDays)
}


export type Explain = {
  asset: Asset | null
  reason?: string
  request?: { interval: string; last_service: string; due: string; due_in_days: number; symptom: string }
  sections: { id: string; title: string; page: number; quote: string; anchor: string }[]
  action: { part: string; action: string; interval: string; source: string } | null
}

export type Diagnosis = {
  available: boolean
  reason?: string
  artifact?: string
  target?: { asset_id: string; tag: string; class: string; area: string }
  condition?: string
  health_score?: number
  issue?: { code: string; summary: string; urgency: string }
  findings?: { finding_id: string; statement: string; confidence: number }[]
  data_quality?: { cases: number; confidence_penalty: number }
  citations?: { doc_id: string; title: string; content: string }[]
  next_safe_check?: { action: string; document_id: string; reason: string }
}

export function fetchExplain(assetId: string): Promise<Explain> {
  return json<Explain>('/api/explain', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ asset_id: assetId }),
  })
}

export const fetchDiagnosis = () => json<Diagnosis>('/api/diagnosis')
