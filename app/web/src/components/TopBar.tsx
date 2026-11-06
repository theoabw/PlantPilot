import type { Health } from '../types'

type TopBarProps = {
  health: Health | null
}

// The offline badge is a product fact, not a live status: the demo runs on the
// technician laptop with no network. The counts appear once /api/health answers.
export default function TopBar({ health }: TopBarProps) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 border-b-4 border-slate-900 bg-white px-5 py-3">
      <div className="flex items-baseline gap-3">
        <span className="text-3xl font-black tracking-tight text-slate-900">PlantPilot</span>
        <span className="text-base font-semibold text-slate-700">
          inspection missions in a scanned plant
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-4">
        <span className="inline-flex items-center gap-2 rounded-full border-2 border-slate-900 bg-slate-100 px-4 py-1 text-base font-bold text-slate-900">
          <span aria-hidden="true" className="h-3 w-3 rounded-full bg-slate-900" />
          offline
        </span>

        {health ? (
          <div className="flex items-baseline gap-3">
            <span className="flex items-baseline gap-2">
              <span className="text-2xl font-black text-slate-900">
                {health.corpus_sections}
              </span>
              <span className="text-base font-semibold text-slate-700">sections</span>
            </span>
            <span className="flex items-baseline gap-2">
              <span className="text-2xl font-black text-slate-900">{health.assets}</span>
              <span className="text-base font-semibold text-slate-700">assets</span>
            </span>
            <span className="text-base font-semibold text-slate-700">v{health.version}</span>
          </div>
        ) : null}
      </div>
    </header>
  )
}
