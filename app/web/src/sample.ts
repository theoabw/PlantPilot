import type { GraphResponse, ScanResponse } from './types'

// Hardcoded sample used by the dev only "load sample" button. It walks the five
// states without a camera or a backend, and is always labelled as sample data.
export const SAMPLE_SCAN: ScanResponse = {
  gate: {
    ok: true,
    character_px: 24.0,
    blur: 130.5,
    message: 'ok',
  },
  plate: {
    fields: {
      type: 'MAP-150-4',
      dn: 'DN 150',
      pn: 'PN 40',
      body: 'A216 WCB',
      serial: 'SN 24-118377',
    },
    confidence: {
      type: 0.98,
      dn: 0.96,
      pn: 0.94,
      body: 0.91,
      serial: 0.88,
    },
    family: 'NelesAce',
  },
  asset: {
    tag: 'K-102',
    line: 'Line 2 board machine',
    criticality: 'high',
    last_service: '2025-11-14',
  },
  sections: [
    {
      id: '3.4',
      title: 'Cavitation and hydrodynamic noise abatement',
      page: 55,
      quote:
        'Trim the plug one size down when the measured noise exceeds the curve.\n' +
        'Keep the vena contracta clear of the seat face to avoid cavitation damage.',
      anchor: '#page=55',
    },
  ],
  action: {
    part: 'Limit switches',
    action: 'Check function',
    interval: '1 year',
    source: 'VMR003',
  },
}

export const SAMPLE_GRAPH: GraphResponse = {
  asset: {
    tag: 'K-102',
    line: 'Line 2 board machine',
    criticality: 'high',
    last_service: '2025-11-14',
  },
  neighbours: [
    { tag: 'K-101', label: 'Line 2', overdue: true },
    { tag: 'K-103', label: 'Line 2', overdue: false },
    { tag: 'K-118', label: 'Line 2', overdue: false },
    { tag: 'K-104', label: 'Line 2', overdue: true },
    { tag: 'K-097', label: 'Line 1', overdue: false },
  ],
  shared_spares: ['Limit switch kit LS-2', 'Plug trim set DN 150'],
}
