import { useEffect, useMemo, useRef, useState } from 'react'
import { LAB_ASSETS, type AssetStatus, type LabAsset } from './fixtures'
import { LabWorld, type LabProgress } from './LabWorld'

const STATUS_LABEL: Record<AssetStatus, string> = {
  healthy: 'healthy',
  watch: 'watch',
  fault: 'fault',
}

const STATUS_PILL: Record<AssetStatus, string> = {
  healthy: 'border-emerald-700 bg-emerald-100 text-emerald-950',
  watch: 'border-amber-700 bg-amber-100 text-amber-950',
  fault: 'border-red-700 bg-red-100 text-red-950',
}

const STATUS_DOT: Record<AssetStatus, string> = {
  healthy: 'bg-emerald-500',
  watch: 'bg-amber-500',
  fault: 'bg-red-500',
}

const EMPTY_PROGRESS: LabProgress = {
  mode: 'idle',
  targetId: null,
  remaining: 0,
  pathLength: 0,
  waypoint: 0,
  waypoints: 0,
}

function modeTitle(progress: LabProgress): string {
  if (progress.mode === 'moving') {
    return `Moving to ${progress.targetId ?? 'target'}`
  }
  if (progress.mode === 'arrived') {
    return `Arrived at ${progress.targetId ?? 'target'}`
  }
  if (progress.mode === 'blocked') {
    return 'No clear route'
  }
  return 'Robot at dock'
}

function modeDetail(progress: LabProgress): string {
  if (progress.mode === 'moving') {
    return `${progress.remaining.toFixed(1)} m left · ${progress.waypoint}/${progress.waypoints} waypoints`
  }
  if (progress.mode === 'arrived') {
    return `Route complete · ${progress.pathLength.toFixed(1)} m travelled`
  }
  if (progress.mode === 'blocked') {
    return 'The target is boxed in. Pick another asset or reset the robot.'
  }
  return 'Select a machine, then send the robot to inspect it.'
}

function progressPercent(progress: LabProgress): number {
  if (progress.mode === 'arrived') {
    return 100
  }
  if (progress.pathLength <= 0) {
    return 0
  }
  return Math.max(0, Math.min(100, ((progress.pathLength - progress.remaining) / progress.pathLength) * 100))
}

function AssetRow({
  asset,
  selected,
  onSelect,
}: {
  asset: LabAsset
  selected: boolean
  onSelect: (id: string) => void
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(asset.id)}
      className={`flex w-full items-center gap-3 rounded-lg border-2 px-3 py-2 text-left transition-colors ${
        selected
          ? 'border-slate-900 bg-slate-900 text-white'
          : 'border-slate-300 bg-white text-slate-900 hover:border-slate-500 hover:bg-slate-50'
      }`}
    >
      <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${STATUS_DOT[asset.status]}`} />
      <span className="min-w-0 flex-1">
        <span className="flex items-baseline justify-between gap-2">
          <span className="text-base font-black tracking-tight">{asset.id}</span>
          <span className={`text-xs font-bold ${selected ? 'text-slate-300' : 'text-slate-500'}`}>
            {asset.health}
          </span>
        </span>
        <span className={`block truncate text-sm font-semibold ${selected ? 'text-slate-300' : 'text-slate-600'}`}>
          {asset.name} · {asset.issue}
        </span>
      </span>
    </button>
  )
}

export default function SceneLab() {
  const hostRef = useRef<HTMLDivElement | null>(null)
  const worldRef = useRef<LabWorld | null>(null)
  const [selectedId, setSelectedId] = useState<string>('P-005')
  const [progress, setProgress] = useState<LabProgress>(EMPTY_PROGRESS)
  const [follow, setFollow] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const host = hostRef.current
    if (!host) {
      return
    }

    let world: LabWorld
    try {
      world = new LabWorld(host, LAB_ASSETS, {
        onSelect: (id) => setSelectedId(id),
        onProgress: (value) => setProgress(value),
      })
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : String(problem))
      return
    }

    worldRef.current = world
    world.select('P-005')

    return () => {
      world.dispose()
      worldRef.current = null
    }
  }, [])

  useEffect(() => {
    worldRef.current?.select(selectedId)
  }, [selectedId])

  useEffect(() => {
    worldRef.current?.setFollow(follow)
  }, [follow])

  const selected = useMemo(
    () => LAB_ASSETS.find((asset) => asset.id === selectedId) ?? LAB_ASSETS[0],
    [selectedId],
  )

  const send = () => {
    setFollow(true)
    worldRef.current?.goTo(selectedId)
  }

  const runFaultDemo = () => {
    setSelectedId('P-005')
    setFollow(true)
    worldRef.current?.goTo('P-005')
  }

  const reset = () => {
    worldRef.current?.reset()
  }

  const overview = () => {
    setFollow(false)
    worldRef.current?.setFollow(false)
    worldRef.current?.overview()
  }

  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 overflow-hidden p-3 lg:grid-cols-[minmax(0,1fr)_360px]">
      <section className="relative min-h-[420px] overflow-hidden rounded-xl border-2 border-slate-900 bg-slate-950">
        {error ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 px-8 text-center">
            <p className="text-xl font-black text-white">3D view unavailable</p>
            <p className="max-w-xl text-base font-semibold text-slate-300">{error}</p>
            <p className="text-base text-slate-400">The panels still describe the demo flow.</p>
          </div>
        ) : (
          <>
            <div ref={hostRef} className="absolute inset-0" />

            <div className="pointer-events-none absolute left-3 top-3 flex items-center gap-2">
              <span className="rounded-md border border-cyan-400/50 bg-slate-950/80 px-2 py-1 text-xs font-black uppercase tracking-[0.16em] text-cyan-300 backdrop-blur">
                Scene lab
              </span>
              <span className="rounded-md border border-slate-600/70 bg-slate-950/70 px-2 py-1 text-xs font-bold text-slate-300 backdrop-blur">
                provisional layout · click a machine
              </span>
            </div>

            <div className="pointer-events-none absolute bottom-3 left-3 right-3 flex flex-wrap items-end justify-between gap-2">
              <div className="rounded-lg border border-slate-700/80 bg-slate-950/80 px-3 py-2 backdrop-blur">
                <p className="text-xs font-bold uppercase tracking-[0.14em] text-slate-400">Robot</p>
                <p className="text-base font-black text-white">{modeTitle(progress)}</p>
                <p className="text-sm font-semibold text-slate-300">{modeDetail(progress)}</p>
              </div>
              <div className="rounded-lg border border-slate-700/80 bg-slate-950/80 px-3 py-2 text-right backdrop-blur">
                <p className="text-xs font-bold uppercase tracking-[0.14em] text-slate-400">Route</p>
                <p className="text-base font-black text-cyan-300">
                  {progress.pathLength > 0 ? `${progress.pathLength.toFixed(1)} m` : '—'}
                </p>
                <p className="text-sm font-semibold text-slate-300">
                  {progress.pathLength > 0 ? `${progress.waypoints} segments` : 'not planned'}
                </p>
              </div>
            </div>
          </>
        )}
      </section>

      <aside className="min-h-0 space-y-3 overflow-y-auto pr-1">
        <div className="rounded-xl border-2 border-slate-900 bg-white p-3">
          <div className="flex items-start justify-between gap-2">
            <div>
              <p className="text-xs font-black uppercase tracking-[0.16em] text-slate-500">Robot task</p>
              <h2 className="text-xl font-black leading-tight text-slate-900">{modeTitle(progress)}</h2>
            </div>
            <span className="rounded-full border-2 border-slate-900 bg-slate-100 px-2 py-0.5 text-xs font-black uppercase text-slate-700">
              {progress.mode}
            </span>
          </div>
          <p className="mt-1 text-sm font-semibold text-slate-600">{modeDetail(progress)}</p>

          <div className="mt-3 h-2.5 w-full overflow-hidden rounded-full bg-slate-200">
            <div
              className="h-full rounded-full bg-cyan-500 transition-[width] duration-150"
              style={{ width: `${progressPercent(progress)}%` }}
            />
          </div>

          <div className="mt-3 grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={send}
              className="rounded-lg border-2 border-slate-900 bg-slate-900 px-3 py-2 text-base font-black text-white hover:bg-slate-800"
            >
              Send robot
            </button>
            <button
              type="button"
              onClick={runFaultDemo}
              className="rounded-lg border-2 border-red-700 bg-red-50 px-3 py-2 text-base font-black text-red-900 hover:bg-red-100"
            >
              Fault demo
            </button>
          </div>
        </div>

        <div className="rounded-xl border-2 border-slate-900 bg-white p-3">
          <p className="text-xs font-black uppercase tracking-[0.16em] text-slate-500">Selected target</p>
          <div className="mt-1 flex items-center justify-between gap-2">
            <h3 className="text-2xl font-black leading-none text-slate-900">{selected.id}</h3>
            <span className={`rounded-full border-2 px-2 py-0.5 text-xs font-black uppercase ${STATUS_PILL[selected.status]}`}>
              {STATUS_LABEL[selected.status]}
            </span>
          </div>
          <p className="mt-1 text-base font-bold text-slate-700">{selected.name}</p>
          <p className="text-sm font-semibold text-slate-500">
            health {selected.health} · {selected.issue}
          </p>
          <p className="mt-2 rounded-lg border border-slate-300 bg-slate-50 p-2 text-sm font-medium text-slate-700">
            {selected.detail}
          </p>
        </div>

        <div className="rounded-xl border-2 border-slate-900 bg-white p-3">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs font-black uppercase tracking-[0.16em] text-slate-500">View</p>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setFollow((value) => !value)}
                className={`rounded-md border-2 px-2.5 py-1 text-sm font-black ${
                  follow
                    ? 'border-cyan-700 bg-cyan-100 text-cyan-950'
                    : 'border-slate-400 bg-white text-slate-900 hover:bg-slate-50'
                }`}
              >
                {follow ? 'Following' : 'Follow robot'}
              </button>
              <button
                type="button"
                onClick={overview}
                className="rounded-md border-2 border-slate-400 bg-white px-2.5 py-1 text-sm font-black text-slate-900 hover:bg-slate-50"
              >
                Overview
              </button>
            </div>
          </div>
          <button
            type="button"
            onClick={reset}
            className="mt-2 w-full rounded-md border-2 border-slate-400 bg-white px-3 py-1.5 text-sm font-black text-slate-900 hover:bg-slate-50"
          >
            Reset robot to dock
          </button>
        </div>

        <div className="rounded-xl border-2 border-slate-900 bg-white p-3">
          <div className="flex items-center justify-between">
            <p className="text-xs font-black uppercase tracking-[0.16em] text-slate-500">Machines</p>
            <p className="text-xs font-bold text-slate-500">{LAB_ASSETS.length} in the lab</p>
          </div>
          <div className="mt-2 space-y-1.5">
            {LAB_ASSETS.map((asset) => (
              <AssetRow key={asset.id} asset={asset} selected={asset.id === selectedId} onSelect={setSelectedId} />
            ))}
          </div>
        </div>

        <p className="px-1 text-xs font-semibold leading-relaxed text-slate-500">
          This is a hand-built stand-in for the boiler room. The route planner already runs on a 0.25 m grid with
          obstacle inflation, so the interaction survives the switch to the real splat and extracted boxes.
        </p>
      </aside>
    </div>
  )
}
