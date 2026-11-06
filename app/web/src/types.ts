// Types for the Fieldplate API contract. The contract is fixed by the backend,
// so these mirror it exactly; nothing here may drift from the responses.

export type Gate = {
  ok: boolean
  character_px: number
  blur: number
  message: string
}

export type PlateFields = {
  type?: string
  dn?: string
  pn?: string
  body?: string
  serial?: string
}

export type Plate = {
  fields: PlateFields
  // Per field confidence, for example { "type": 0.98 }.
  confidence: Record<string, number>
  family?: string | null
  // Only sent when no asset matched; the three closest known types.
  closest_types?: string[]
}

export type Asset = {
  tag: string
  line?: string
  criticality?: string
  last_service?: string
}

export type Section = {
  id: string
  title: string
  page: number
  quote: string
  anchor: string
}

export type ServiceAction = {
  part: string
  action: string
  interval: string
  source: string
}

export type ScanResponse = {
  gate: Gate
  plate: Plate | null
  asset: Asset | null
  sections: Section[]
  action: ServiceAction | null
  closest_types?: string[]
}

export type Neighbour = {
  tag: string
  label?: string
  overdue?: boolean
}

export type GraphResponse = {
  asset: Asset
  neighbours: Neighbour[]
  shared_spares?: string[]
}

// Where the right hand column is: nothing scanned yet, the last scan failed,
// or there is a response to render.
export type ScanState = 'idle' | 'error' | 'done'

export type Health = {
  ok: boolean
  corpus_sections: number
  assets: number
  version: string
}
