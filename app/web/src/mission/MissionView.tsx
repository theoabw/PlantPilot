import { useCallback, useEffect, useMemo, useState } from 'react'
import { fetchCloud, fetchExplain, fetchPlant, fetchRoute, inspections } from './api'
import type { Cloud, Explain, Plant, RouteResult } from './api'
import PlantScene from './PlantScene'

const WEST_AISLE_CLOSED = [[0.0, 4.8, 4.6, 7.2]]
const HALL_SEALED = [[0.0, 1.5, 16.0, 2.2]]

export default function MissionView() {
  const [plant, setPlant] = useState<Plant | null>(null)
  const [cloud, setCloud] = useState<Cloud | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [route, setRoute] = useState<RouteResult | null>(null)
  const [blocked, setBlocked] = useState<'none' | 'aisle' | 'sealed'>('none')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [routeMs, setRouteMs] = useState<number | null>(null)
  const [evidence, setEvidence] = useState<Explain | null>(null)

  useEffect(() => {
    let alive = true
    Promise.all([fetchPlant(), fetchCloud()])
      .then(([nextPlant, nextCloud]) => {
        if (!alive) {
          return
        }
        setPlant(nextPlant)
        setCloud(nextCloud)
        // The demo opens on the whole hall, then a click picks a machine. A URL
        // parameter pre-selects one, which is how the screenshots and the video are taken.
        const fromUrl = new URLSearchParams(window.location.search).get('asset')
        setSelected(fromUrl && nextPlant.assets.some((asset) => asset.id === fromUrl) ? fromUrl : null)
      })
      .catch((problem: Error) => alive && setError(problem.message))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [])

  const load = useCallback(
    (id: string | null, mode: 'none' | 'aisle' | 'sealed') => {
      if (!id) {
        return
      }
      const blockers = mode === 'aisle' ? WEST_AISLE_CLOSED : mode === 'sealed' ? HALL_SEALED : []
      const started = performance.now()
      fetchRoute(id, blockers)
        .then((next) => {
          setRoute(next)
          setRouteMs(Math.round(performance.now() - started))
        })
        .catch((problem: Error) => setError(problem.message))
    },
    [],
  )

  useEffect(() => {
    load(selected, blocked)
  }, [selected, blocked, load])

  useEffect(() => {
    if (!selected) {
      setEvidence(null)
      return
    }
    let alive = true
    fetchExplain(selected)
      .then((next) => alive && setEvidence(next))
      .catch(() => alive && setEvidence(null))
    return () => {
      alive = false
    }
  }, [selected])

  const orders = useMemo(() => (plant ? inspections(plant.assets) : []), [plant])
  const current = plant?.assets.find((asset) => asset.id === selected) ?? null
  const nextOrder = orders[0]

  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 p-4 lg:grid-cols-3">
      <div className="min-h-[420px] lg:col-span-2">
        {error ? (
          <div className="rounded-xl border-2 border-red-800 bg-red-50 p-4 text-lg font-bold text-red-900">{error}</div>
        ) : (
          <PlantScene
            cloud={cloud}
            assets={plant?.assets ?? []}
            selectedId={selected}
            route={route}
            blocked={blocked !== 'none'}
            onSelect={setSelected}
          />
        )}
      </div>

      <aside className="min-h-0 space-y-3 overflow-y-auto pr-1">
        <div className="rounded-xl border-2 border-slate-900 bg-white p-3">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-xl font-black text-slate-900">{plant?.name ?? 'loading the plant'}</h2>
            <span className="rounded-full border-2 border-slate-900 bg-slate-100 px-2 py-0.5 text-sm font-bold text-slate-900">
              {plant?.source ?? '...'}
            </span>
          </div>
          <p className="mt-1 text-base font-semibold text-slate-700">
            {cloud ? `${cloud.count.toLocaleString()} points` : loading ? 'loading the cloud' : 'no cloud'}
            {routeMs !== null ? ` · route answered in ${routeMs} ms` : ''}
          </p>
        </div>

        <div className="rounded-xl border-2 border-slate-900 bg-white p-3">
          <p className="text-sm font-bold uppercase tracking-wide text-slate-600">Next inspection</p>
          {nextOrder ? (
            <button
              type="button"
              onClick={() => setSelected(nextOrder.asset.id)}
              className="mt-1 w-full rounded-lg border-2 border-slate-900 bg-amber-50 px-3 py-2 text-left hover:bg-amber-100"
            >
              <span className="block text-lg font-black text-slate-900">{nextOrder.asset.id}</span>
              <span className="block text-base font-semibold text-slate-700">
                {nextOrder.asset.kind}, {nextOrder.dueInDays < 0 ? `${Math.abs(nextOrder.dueInDays)} days overdue` : `due in ${nextOrder.dueInDays} days`}
              </span>
              <span className="block text-sm font-semibold text-slate-600">
                {nextOrder.asset.interval} interval, last service {nextOrder.asset.last_service}
              </span>
            </button>
          ) : null}
        </div>

        {current ? (
          <div className="rounded-xl border-2 border-slate-900 bg-white p-3">
            <p className="text-sm font-bold uppercase tracking-wide text-slate-600">Selected</p>
            <p className="text-lg font-black text-slate-900">
              {current.id} <span className="font-semibold text-slate-700">{current.kind}</span>
            </p>
            <p className="text-base font-semibold text-slate-700">
              {current.type ?? 'type unknown'} · {current.dn} · {current.pn}
            </p>
            <p className="mt-1 text-base text-slate-700">
              {route?.reachable
                ? `${route.distance_m} m to the inspection point, ${route.clearance_m} m clearance`
                : route?.reason ?? 'computing'}
            </p>
          </div>
        ) : null}

        <div className="rounded-xl border-2 border-slate-900 bg-white p-3">
          <p className="text-sm font-bold uppercase tracking-wide text-slate-600">Why this visit</p>
          {evidence?.request ? (
            <p className="mt-1 text-base font-semibold text-slate-700">
              {evidence.request.symptom}, {evidence.request.due_in_days < 0
                ? `${Math.abs(evidence.request.due_in_days)} days overdue`
                : `due in ${evidence.request.due_in_days} days`}
              , {evidence.request.interval} interval
            </p>
          ) : null}
          {!selected ? (
            <p className="mt-1 text-base font-semibold text-slate-700">
              Select a machine to see the reason and its citation.
            </p>
          ) : null}
          {evidence?.sections?.length ? (
            <div className="mt-2 rounded-lg border-2 border-slate-300 bg-slate-50 p-2">
              <p className="text-base font-bold text-slate-900">{evidence.sections[0].title}</p>
              <p className="text-sm font-bold text-slate-600">
                section {evidence.sections[0].id}, page {evidence.sections[0].page}
              </p>
              <p className="mt-1 text-base text-slate-700">{evidence.sections[0].quote}</p>
            </div>
          ) : selected ? (
            <p className="mt-1 text-base font-semibold text-amber-800">
              no cited section for this machine, run make corpus
            </p>
          ) : null}
          {evidence?.action ? (
            <p className="mt-2 text-base text-slate-700">
              {evidence.action.part}: {evidence.action.action}, {evidence.action.interval} ({evidence.action.source})
            </p>
          ) : null}
        </div>

        <div className="rounded-xl border-2 border-slate-900 bg-white p-3">
          <p className="text-sm font-bold uppercase tracking-wide text-slate-600">Judge pick</p>
          <div className="mt-1 flex flex-wrap gap-2">
            {['P-204', 'V-203', 'T-501'].map((id) => (
              <button
                key={id}
                type="button"
                onClick={() => setSelected(id)}
                className="rounded-md border-2 border-slate-900 bg-white px-3 py-1.5 text-base font-bold text-slate-900 hover:bg-slate-100"
              >
                {id}
              </button>
            ))}
          </div>
        </div>

        <div className="rounded-xl border-2 border-slate-900 bg-white p-3">
          <p className="text-sm font-bold uppercase tracking-wide text-slate-600">Obstruction</p>
          <div className="mt-1 flex flex-wrap gap-2">
            {(['none', 'aisle', 'sealed'] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => setBlocked(mode)}
                className={`rounded-md border-2 px-3 py-1.5 text-base font-bold ${
                  blocked === mode
                    ? 'border-slate-900 bg-slate-900 text-white'
                    : 'border-slate-400 bg-white text-slate-900 hover:bg-slate-100'
                }`}
              >
                {mode === 'none' ? 'clear' : mode === 'aisle' ? 'west aisle closed' : 'hall sealed'}
              </button>
            ))}
          </div>
        </div>

        <div className="rounded-xl border-2 border-slate-900 bg-white p-3">
          <p className="text-sm font-bold uppercase tracking-wide text-slate-600">Equipment</p>
          <ul className="mt-1 space-y-1">
            {plant?.assets.map((asset) => (
              <li key={asset.id}>
                <button
                  type="button"
                  onClick={() => setSelected(asset.id)}
                  className={`flex w-full items-center justify-between rounded-md px-2 py-1 text-left text-base font-semibold ${
                    asset.id === selected ? 'bg-slate-900 text-white' : 'hover:bg-slate-100'
                  }`}
                >
                  <span>{asset.id}</span>
                  <span className={asset.id === selected ? 'text-slate-200' : 'text-slate-600'}>{asset.kind}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </aside>
    </div>
  )
}
