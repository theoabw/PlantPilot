import { useEffect, useState } from 'react'
import { errorMessage, fetchGraph, fetchHealth, scanFrame } from './api'
import type { GraphResponse, Health, ScanResponse, ScanState } from './types'
import { SAMPLE_GRAPH, SAMPLE_SCAN } from './sample'
import ActionCard from './components/ActionCard'
import AssetCard from './components/AssetCard'
import CameraPane from './components/CameraPane'
import DocumentCard from './components/DocumentCard'
import GraphCard from './components/GraphCard'
import TopBar from './components/TopBar'
import { GateAccepted, GateRefusal } from './components/GateBanner'

function closestTypes(response: ScanResponse | null): string[] {
  if (!response) {
    return []
  }
  const fromRoot = response.closest_types ?? []
  const fromPlate = response.plate?.closest_types ?? []
  return fromRoot.length > 0 ? fromRoot : fromPlate
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [result, setResult] = useState<ScanResponse | null>(null)
  const [graph, setGraph] = useState<GraphResponse | null>(null)
  const [graphLoading, setGraphLoading] = useState(false)
  const [graphError, setGraphError] = useState<string | null>(null)
  const [scanning, setScanning] = useState(false)
  const [scanError, setScanError] = useState<string | null>(null)
  const [isSample, setIsSample] = useState(false)

  // Health is a nicety: retry quietly while the backend is still starting up.
  useEffect(() => {
    let cancelled = false
    let retry: number | undefined

    function load() {
      fetchHealth()
        .then((value) => {
          if (!cancelled) {
            setHealth(value)
          }
        })
        .catch(() => {
          if (!cancelled) {
            retry = window.setTimeout(load, 5000)
          }
        })
    }

    load()

    return () => {
      cancelled = true
      if (retry !== undefined) {
        window.clearTimeout(retry)
      }
    }
  }, [])

  const assetTag = result?.asset?.tag ?? null

  useEffect(() => {
    if (!assetTag || isSample) {
      return
    }

    let cancelled = false
    setGraphLoading(true)
    setGraphError(null)
    setGraph(null)

    fetchGraph(assetTag)
      .then((value) => {
        if (!cancelled) {
          setGraph(value)
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setGraphError(`Line neighbours did not load: ${errorMessage(error)}`)
        }
      })
      .finally(() => {
        if (!cancelled) {
          setGraphLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [assetTag, isSample])

  async function runScan(frame: Blob) {
    setScanning(true)
    setScanError(null)
    setIsSample(false)
    setResult(null)
    setGraph(null)
    setGraphError(null)
    setGraphLoading(false)

    try {
      const response = await scanFrame(frame)
      setResult(response)
    } catch (error) {
      setScanError(`Scan failed: ${errorMessage(error)}`)
    } finally {
      setScanning(false)
    }
  }

  function loadSample() {
    setScanning(false)
    setScanError(null)
    setIsSample(true)
    setResult(SAMPLE_SCAN)
    setGraph(SAMPLE_GRAPH)
    setGraphError(null)
    setGraphLoading(false)
  }

  const state: ScanState = scanError ? 'error' : result ? 'done' : 'idle'

  return (
    <div className="flex h-screen flex-col bg-slate-100 text-slate-900">
      <TopBar health={health} />

      <main className="grid min-h-0 flex-1 grid-cols-1 gap-4 p-4 lg:grid-cols-2">
        <div className="min-h-0">
          <CameraPane
            busy={scanning}
            onFrame={(frame) => void runScan(frame)}
            onLoadSample={loadSample}
          />
        </div>

        <div className="min-h-0 space-y-4 overflow-y-auto pr-1">
          {isSample ? (
            <div className="rounded-xl border-2 border-amber-600 bg-amber-50 px-4 py-2 text-base font-bold text-amber-900">
              sample data, nothing was scanned and no backend call was made
            </div>
          ) : null}

          {scanning ? (
            <div className="flex items-center gap-3 rounded-xl border-2 border-blue-800 bg-blue-50 px-4 py-3 text-lg font-bold text-blue-900">
              <span
                aria-hidden="true"
                className="h-6 w-6 shrink-0 animate-spin rounded-full border-[3px] border-blue-800 border-t-transparent"
              />
              scanning the frame...
            </div>
          ) : null}

          {scanError ? (
            <div className="rounded-xl border-4 border-red-700 bg-red-50 px-4 py-3">
              <p className="text-xl font-bold text-red-900">Scan failed</p>
              <p className="mt-1 text-base font-semibold text-red-900">{scanError}</p>
              <p className="mt-1 text-base font-semibold text-red-900">
                Check the backend on 127.0.0.1:8000, then scan again.
              </p>
            </div>
          ) : null}

          {result && !result.gate.ok ? <GateRefusal gate={result.gate} /> : null}
          {result && result.gate.ok ? <GateAccepted gate={result.gate} /> : null}

          <AssetCard
            plate={result?.plate ?? null}
            asset={result?.asset ?? null}
            closestTypes={closestTypes(result)}
            state={state}
          />

          <DocumentCard section={result?.sections[0] ?? null} state={state} />

          <ActionCard action={result?.action ?? null} state={state} />

          <GraphCard
            graph={graph}
            loading={graphLoading}
            error={graphError}
            assetTag={assetTag}
            state={state}
          />
        </div>
      </main>
    </div>
  )
}
