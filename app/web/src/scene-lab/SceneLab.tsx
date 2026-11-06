import { useEffect, useMemo, useRef, useState } from 'react'
import { LAB_ASSETS } from './fixtures'
import { LabWorld, type LabProgress } from './LabWorld'
import { modeDetail, modeTitle } from './status'
import ScenePanel from '../components/ScenePanel'
import ViewToolbar from '../components/ViewToolbar'

const EMPTY_PROGRESS: LabProgress = {
  mode: 'idle',
  targetId: null,
  remaining: 0,
  pathLength: 0,
  waypoint: 0,
  waypoints: 0,
}

export default function SceneLab({ onNavigate }: { onNavigate: (view: 'plant' | 'plate') => void }) {
  const hostRef = useRef<HTMLDivElement | null>(null)
  const worldRef = useRef<LabWorld | null>(null)
  const [selectedId, setSelectedId] = useState<string>('P-005')
  const [progress, setProgress] = useState<LabProgress>(EMPTY_PROGRESS)
  const [follow, setFollow] = useState(false)
  const [panelOpen, setPanelOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const host = hostRef.current
    if (!host) {
      return
    }

    let world: LabWorld
    try {
      world = new LabWorld(host, LAB_ASSETS, {
        onSelect: (id) => {
          setSelectedId(id)
          setPanelOpen(true)
        },
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

  useEffect(() => {
    if (!panelOpen) {
      return
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setPanelOpen(false)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [panelOpen])

  const selected = useMemo(
    () => LAB_ASSETS.find((asset) => asset.id === selectedId) ?? LAB_ASSETS[0],
    [selectedId],
  )

  const faultCount = useMemo(
    () => LAB_ASSETS.filter((asset) => asset.status === 'fault').length,
    [],
  )

  const send = () => {
    setPanelOpen(false)
    setFollow(true)
    worldRef.current?.goTo(selectedId)
  }

  const runFaultDemo = () => {
    setSelectedId('P-005')
    setPanelOpen(false)
    setFollow(true)
    worldRef.current?.goTo('P-005')
  }

  const overview = () => {
    setFollow(false)
    worldRef.current?.setFollow(false)
    worldRef.current?.overview()
  }

  return (
    <div className="relative h-screen w-full overflow-hidden bg-slate-950">
      <section className="relative h-full w-full overflow-hidden">
        {error ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 px-8 text-center">
            <p className="text-xl font-black text-white">3D view unavailable</p>
            <p className="max-w-xl text-base font-semibold text-slate-300">{error}</p>
            <p className="text-base text-slate-400">The mission panel still describes the demo flow.</p>
          </div>
        ) : (
          <>
            <div ref={hostRef} className="absolute inset-0" />

            <div className="pointer-events-none absolute left-3 top-3 z-10 flex flex-wrap items-center gap-2 pr-28">
              <span className="rounded-md border border-cyan-400/50 bg-slate-950/80 px-2 py-1 text-xs font-black uppercase tracking-[0.16em] text-cyan-300 backdrop-blur">
                Scene lab
              </span>
              <span className="rounded-md border border-slate-600/70 bg-slate-950/70 px-2 py-1 text-xs font-bold text-slate-300 backdrop-blur">
                click a machine to inspect
              </span>
            </div>

            <ViewToolbar
              follow={follow}
              panelOpen={panelOpen}
              faultCount={faultCount}
              onOverview={overview}
              onFollow={() => setFollow((value) => !value)}
              onReset={() => worldRef.current?.reset()}
              onTogglePanel={() => setPanelOpen((value) => !value)}
            />

            <div className="pointer-events-none absolute bottom-3 left-3 z-10 max-w-[62%] rounded-lg border border-slate-700/80 bg-slate-950/80 px-3 py-2 backdrop-blur">
              <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">Robot</p>
              <p className="text-base font-black text-white">{modeTitle(progress)}</p>
              <p className="text-sm font-semibold text-slate-300">{modeDetail(progress)}</p>
            </div>

            <div className="pointer-events-none absolute bottom-3 right-3 z-10 rounded-lg border border-slate-700/80 bg-slate-950/80 px-3 py-2 text-right backdrop-blur">
              <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">Route</p>
              <p className="text-base font-black text-cyan-300">
                {progress.pathLength > 0 ? `${progress.pathLength.toFixed(1)} m` : '-'}
              </p>
              <p className="text-sm font-semibold text-slate-300">
                {progress.pathLength > 0 ? `${progress.waypoints} segments` : 'not planned'}
              </p>
            </div>

            {panelOpen ? (
              <ScenePanel
                assets={LAB_ASSETS}
                selected={selected}
                progress={progress}
                onSelect={setSelectedId}
                onClose={() => setPanelOpen(false)}
                onSend={send}
                onFaultDemo={runFaultDemo}
                onNavigate={onNavigate}
              />
            ) : null}
          </>
        )}
      </section>
    </div>
  )
}
