// A hand-built stand-in for the real boiler room. The point of this view is to
// tune the interaction before the splat and the extracted objects arrive: a few
// boxy assets, a robot, and a click-to-send target. Coordinates are metres with
// Y up, matching the supplied scene.

export type AssetStatus = 'healthy' | 'watch' | 'fault'
export type AssetKind = 'pump' | 'motor' | 'valve' | 'tank' | 'boiler'

export type LabAsset = {
  id: string
  name: string
  kind: AssetKind
  x: number
  z: number
  width: number
  depth: number
  height: number
  status: AssetStatus
  health: number
  issue: string
  detail: string
}

export const ROOM = {
  minX: 0,
  maxX: 14,
  minZ: 0,
  maxZ: 9,
  height: 4.2,
}

export const DOCK = { x: 1.4, z: 4.5 }

export const LAB_ASSETS: LabAsset[] = [
  {
    id: 'P-005',
    name: 'Process pump',
    kind: 'pump',
    x: 10.4,
    z: 2.3,
    width: 1.8,
    depth: 1.2,
    height: 1.35,
    status: 'fault',
    health: 44,
    issue: 'FOULING',
    detail: 'Efficiency loss / fouling-like signature. Inspect hydraulic path.',
  },
  {
    id: 'P-002',
    name: 'Feed pump',
    kind: 'pump',
    x: 3.6,
    z: 1.5,
    width: 1.8,
    depth: 1.2,
    height: 1.35,
    status: 'watch',
    health: 45,
    issue: 'CAVITATION_RISK',
    detail: 'Hydraulic instability. Inspect process conditions.',
  },
  {
    id: 'M-006',
    name: 'Drive motor',
    kind: 'motor',
    x: 6.1,
    z: 7.4,
    width: 1.5,
    depth: 1.1,
    height: 1.15,
    status: 'watch',
    health: 45,
    issue: 'OVERHEATING',
    detail: 'Sustained temperature elevation. Inspect cooling and load.',
  },
  {
    id: 'CV-003',
    name: 'Control valve',
    kind: 'valve',
    x: 2.2,
    z: 7.3,
    width: 0.8,
    depth: 0.8,
    height: 1.7,
    status: 'watch',
    health: 52,
    issue: 'POSITION_DEVIATION',
    detail: 'Position tracking deviation. Verify control and mechanics.',
  },
  {
    id: 'T-101',
    name: 'Buffer tank',
    kind: 'tank',
    x: 11.9,
    z: 7.1,
    width: 2.2,
    depth: 2.2,
    height: 2.7,
    status: 'healthy',
    health: 96,
    issue: 'NORMAL',
    detail: 'No significant deviation.',
  },
  {
    id: 'B-01',
    name: 'Boiler unit',
    kind: 'boiler',
    x: 6.8,
    z: 4.6,
    width: 2.8,
    depth: 2.0,
    height: 3.0,
    status: 'healthy',
    health: 96,
    issue: 'NORMAL',
    detail: 'No significant deviation.',
  },
]
