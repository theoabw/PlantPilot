import { useState } from 'react'
import type { LabAsset } from '../scene-lab/fixtures'
import type { LabProgress } from '../scene-lab/LabWorld'
import {
  STATUS_LABEL,
  STATUS_PILL,
  modeDetail,
  modeTitle,
  progressPercent,
} from '../scene-lab/status'
import SceneAssetRow from './SceneAssetRow'

type ScenePanelProps = {
  assets: LabAsset[]
  selected: LabAsset
  progress: LabProgress
  onSelect: (id: string) => void
  onClose: () => void
  onSend: () => void
  onFaultDemo: () => void
}

type Tab = 'mission' | 'machines'

export default function ScenePanel({
  assets,
  selected,
  progress,
  onSelect,
  onClose,
  onSend,
  onFaultDemo,
}: ScenePanelProps) {
  const [tab, setTab] = useState<Tab>('mission')

  return (
    <aside
      id="scene-detail-panel"
      aria-label="Mission details"
      className="scene-panel absolute inset-x-0 bottom-0 top-auto z-30 max-h-[72%] overflow-y-auto rounded-t-2xl border-t border-slate-700 bg-slate-950/95 p-4 shadow-2xl backdrop-blur-md lg:inset-y-0 lg:left-auto lg:right-0 lg:w-[390px] lg:max-h-none lg:rounded-none lg:border-l lg:border-t-0"
    >
      <div className="mx-auto mb-2 h-1 w-10 rounded-full bg-slate-600 lg:hidden" />

      <header className="flex items-start justify-between gap-3 border-b border-slate-800 pb-3">
        <div>
          <p className="text-[10px] font-black uppercase tracking-[0.18em] text-slate-500">Scene details</p>
          <h2 className="text-xl font-black leading-tight text-white">Mission panel</h2>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close mission panel"
          className="rounded-md border border-slate-700 bg-slate-900 p-1.5 text-slate-300 hover:border-slate-500 hover:text-white"
        >
          <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="m6 6 12 12M18 6 6 18" />
          </svg>
        </button>
      </header>

      <div className="mt-3 grid grid-cols-2 gap-1 rounded-lg border border-slate-800 bg-slate-900/70 p-1">
        {(
          [
            ['mission', 'Mission'],
            ['machines', `Machines (${assets.length})`],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            type="button"
            onClick={() => setTab(value)}
            className={`rounded-md px-3 py-1.5 text-sm font-black transition-colors ${
              tab === value ? 'bg-cyan-500 text-slate-950' : 'text-slate-400 hover:text-white'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'mission' ? (
        <div className="mt-3 space-y-3">
          <section className="rounded-xl border border-slate-700 bg-slate-900/70 p-3">
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="text-[10px] font-black uppercase tracking-[0.16em] text-slate-500">Robot task</p>
                <h3 className="text-lg font-black leading-tight text-white">{modeTitle(progress)}</h3>
              </div>
              <span className="rounded-full border border-slate-600 bg-slate-950 px-2 py-0.5 text-[10px] font-black uppercase text-slate-300">
                {progress.mode}
              </span>
            </div>
            <p className="mt-1 text-sm font-semibold text-slate-400">{modeDetail(progress)}</p>

            <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-slate-700">
              <div
                className="h-full rounded-full bg-cyan-400 transition-[width] duration-150"
                style={{ width: `${progressPercent(progress)}%` }}
              />
            </div>

            <div className="mt-3 grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={onSend}
                className="rounded-lg bg-cyan-500 px-3 py-2 text-sm font-black text-slate-950 hover:bg-cyan-400"
              >
                Send robot
              </button>
              <button
                type="button"
                onClick={onFaultDemo}
                className="rounded-lg border border-red-500/60 bg-red-500/10 px-3 py-2 text-sm font-black text-red-200 hover:bg-red-500/20"
              >
                Fault demo
              </button>
            </div>
          </section>

          <section className="rounded-xl border border-slate-700 bg-slate-900/70 p-3">
            <div className="flex items-center justify-between gap-2">
              <p className="text-[10px] font-black uppercase tracking-[0.16em] text-slate-500">Selected target</p>
              <span className={`rounded-full border px-2 py-0.5 text-[10px] font-black uppercase ${STATUS_PILL[selected.status]}`}>
                {STATUS_LABEL[selected.status]}
              </span>
            </div>
            <div className="mt-1 flex items-baseline justify-between gap-2">
              <h3 className="text-2xl font-black leading-none text-white">{selected.id}</h3>
              <span className="text-xs font-bold text-slate-400">health {selected.health}</span>
            </div>
            <p className="mt-1 text-base font-bold text-slate-200">{selected.name}</p>
            <p className="text-xs font-bold uppercase tracking-wide text-slate-500">{selected.issue}</p>
            <p className="mt-2 rounded-lg border border-slate-700 bg-slate-950/70 p-2 text-sm font-medium text-slate-300">
              {selected.detail}
            </p>
          </section>
        </div>
      ) : (
        <div className="mt-3 space-y-2">
          <p className="text-xs font-semibold text-slate-500">Pick a machine to inspect. The robot waits for a send command.</p>
          <div className="space-y-1.5">
            {assets.map((asset) => (
              <SceneAssetRow
                key={asset.id}
                asset={asset}
                selected={asset.id === selected.id}
                onSelect={onSelect}
              />
            ))}
          </div>
          <button
            type="button"
            onClick={onSend}
            className="mt-1 w-full rounded-lg bg-cyan-500 px-3 py-2 text-sm font-black text-slate-950 hover:bg-cyan-400"
          >
            Send robot to {selected.id}
          </button>
        </div>
      )}

      <p className="mt-4 border-t border-slate-800 pt-3 text-[11px] font-semibold leading-relaxed text-slate-500">
        Click a machine in the scene to open this panel. Sending the robot closes it and turns on the follow
        camera so the route stays visible.
      </p>
    </aside>
  )
}
