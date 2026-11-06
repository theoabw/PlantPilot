import type { Gate } from '../types'

// A refused frame is a demo step, so it gets a loud red card with the number
// that failed the gate. An accepted frame gets a quiet green strip.
export function GateRefusal({ gate }: { gate: Gate }) {
  return (
    <section className="rounded-xl border-4 border-red-700 bg-red-50 p-4 shadow-sm">
      <header className="flex items-baseline justify-between gap-3">
        <h2 className="text-xl font-bold text-red-900">Frame refused</h2>
        <span className="rounded-full border-2 border-red-700 bg-red-700 px-3 py-0.5 text-base font-bold text-white">
          gate failed
        </span>
      </header>

      <p className="mt-2 text-lg font-bold text-red-900">{gate.message}</p>

      <dl className="mt-3 flex flex-wrap gap-x-8 gap-y-2">
        <div className="flex items-baseline gap-2">
          <dt className="text-base font-semibold text-red-900">characters</dt>
          <dd className="text-2xl font-black text-red-900">
            {gate.character_px.toFixed(1)} px
          </dd>
        </div>
        <div className="flex items-baseline gap-2">
          <dt className="text-base font-semibold text-red-900">blur</dt>
          <dd className="text-2xl font-black text-red-900">{gate.blur.toFixed(1)}</dd>
        </div>
      </dl>

      <p className="mt-3 text-base font-semibold text-red-900">
        Move closer, hold still and scan again.
      </p>
    </section>
  )
}

export function GateAccepted({ gate }: { gate: Gate }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1 rounded-lg border-2 border-emerald-700 bg-emerald-50 px-4 py-2">
      <span className="text-base font-bold text-emerald-900">frame accepted</span>
      <span className="text-base font-semibold text-emerald-900">
        characters {gate.character_px.toFixed(1)} px
      </span>
      <span className="text-base font-semibold text-emerald-900">
        blur {gate.blur.toFixed(1)}
      </span>
    </div>
  )
}
