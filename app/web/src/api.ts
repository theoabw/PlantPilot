import type { GraphResponse, Health, ScanResponse } from './types'

// In development Vite proxies /api to the FastAPI backend on 127.0.0.1:8000.
// In production FastAPI serves the same build, so a relative path works there.
const API_BASE = '/api'

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = ''
    try {
      detail = await response.text()
    } catch {
      detail = ''
    }
    const suffix = detail ? `: ${detail.slice(0, 300)}` : ''
    throw new Error(`${response.status} ${response.statusText}${suffix}`)
  }
  return (await response.json()) as T
}

export async function fetchHealth(): Promise<Health> {
  const response = await fetch(`${API_BASE}/health`, {
    headers: { Accept: 'application/json' },
  })
  return readJson<Health>(response)
}

export async function scanFrame(frame: Blob): Promise<ScanResponse> {
  const form = new FormData()
  form.append('frame', frame, 'frame.jpg')
  const response = await fetch(`${API_BASE}/scan`, {
    method: 'POST',
    body: form,
    headers: { Accept: 'application/json' },
  })
  return readJson<ScanResponse>(response)
}

export async function fetchGraph(tag: string): Promise<GraphResponse> {
  const response = await fetch(`${API_BASE}/assets/${encodeURIComponent(tag)}`, {
    headers: { Accept: 'application/json' },
  })
  return readJson<GraphResponse>(response)
}

export function errorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message
  }
  return String(error)
}
