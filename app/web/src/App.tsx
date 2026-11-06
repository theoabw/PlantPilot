import { useEffect, useState } from 'react'
import { errorMessage, fetchGraph, scanFrame } from './api'
import type { GraphResponse, ScanResponse, ScanState } from './types'
import { SAMPLE_GRAPH, SAMPLE_SCAN } from './sample'
import ActionCard from './components/ActionCard'
import AssetCard from './components/AssetCard'
import CameraPane from './components/CameraPane'
import DocumentCard from './components/DocumentCard'
import GraphCard from './components/GraphCard'
import MissionView from './mission/MissionView'
import SceneLab from './scene-lab/SceneLab'
import { GateAccepted, GateRefusal } from './components/GateBanner'

function closestTypes(response: ScanResponse | null): string[] {
  if (!response) {
    return []
  }
  const fromRoot = response.closest_types ?? []
  const fromPlate = response.plate?.closest_types ?? []
  return fromRoot.length > 0 ? fromRoot : fromPlate
}

function WorkspaceBar({ title, onBack }: { title: string; onBack: () => void }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-slate-300 bg-white px-3 py-2">
      <button
        type="button"
        onClick={onBack}
        className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-2.5 py-1 text-sm font-bold text-slate-800 hover:border-slate-500 hover:bg-slate-50"
      >
        <svg aria-hidden="true" viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="m15 18-6-6 6-6" />
        </svg>
        Scene lab
      </button>
      <span className="text-xs font-black uppercase tracking-[0.16em] text-slate-500">{title}</span>
      <span className="rounded-full border border-slate-300 bg-slate-100 px-2 py-0.5 text-[10px] font-black uppercase tracking-wide text-slate-500">
        offline
      </span>
    </div>
  )
}

export default function App() {
  const [result, setResult] = useState<ScanResponse | null>(null)
  const [graph, setGraph] = useState<GraphResponse | null>(null)
  const [graphLoading, setGraphLoading] = useState(false)
  const [graphError, setGraphError] = useState<string | null>(null)
  const [scanning, setScanning] = useState(false)
  const [scanError, setScanError] = useState<string | null>(null)
  const [isSample, setIsSample] = useState(false)
  const [view, setView] = useState<'scene' | 'plant' | 'plate'>('scene')

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

  if (view === 'scene') {
    return <SceneLab onNavigate={(next) => setView(next)} />
  }

  if (view === 'plant') {
    return (
      <div className="flex h-screen flex-col bg-slate-100 text-slate-900">
        <WorkspaceBar title="Plant mission" onBack={() => setView('scene')} />
        <MissionView />
      </div>
    )
  }

  return (
    <div className="flex h-screen flex-col bg-slate-100 text-slate-900">
      <WorkspaceBar title="Plate scan" onBack={() => setView('scene')} />

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
