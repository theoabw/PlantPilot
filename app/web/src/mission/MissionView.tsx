import { useCallback, useEffect, useMemo, useState } from 'react'
import { fetchCloud, fetchExplain, fetchPlant, fetchRoute, inspections } from './api'
import type { Cloud, Explain, Plant, RouteResult } from './api'
import PlantScene from './PlantScene'

const AISLE_CLOSED = [[0.0, 4.8, 4.6, 7.2]]
const AREA_SEALED = [[0.0, 1.5, 16.0, 2.2]]
type Access = 'clear' | 'aisle' | 'sealed'

const ACCESS_LABEL: Record<Access, string> = {
  clear: 'Clear',
  aisle: 'Aisle blocked',
  sealed: 'Area sealed',
}

function dateLabel(iso: string): string {
  const date = new Date(`${iso}T00:00:00Z`)
  return date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' })
}

export default function MissionView() {
  const [plant, setPlant] = useState<Plant | null>(null)
  const [cloud, setCloud] = useState<Cloud | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [route, setRoute] = useState<RouteResult | null>(null)
  const [access, setAccess] = useState<Access>('clear')
  const [evidence, setEvidence] = useState<Explain | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    Promise.all([fetchPlant(), fetchCloud()])
      .then(([nextPlant, nextCloud]) => {
        if (!alive) {
          return
        }
        setPlant(nextPlant)
        setCloud(nextCloud)
        const fromUrl = new URLSearchParams(window.location.search).get('asset')
        setSelected(fromUrl && nextPlant.assets.some((asset) => asset.id === fromUrl) ? fromUrl : null)
      })
      .catch((problem: Error) => alive && setError(problem.message))
    return () => {
      alive = false
    }
  }, [])

  const load = useCallback((id: string | null, mode: Access) => {
    if (!id) {
      return
    }
    const blockers = mode === 'aisle' ? AISLE_CLOSED : mode === 'sealed' ? AREA_SEALED : []
    fetchRoute(id, blockers).then(setRoute).catch((problem: Error) => setError(problem.message))
  }, [])

  useEffect(() => {
    load(selected, access)
  }, [selected, access, load])

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
  const attention = useMemo(() => new Set(orders.filter((order) => order.dueInDays < 0).map((order) => order.asset.id)), [orders])
  const current = plant?.assets.find((asset) => asset.id === selected) ?? null
  const nextOrder = orders[0]

  return (
    <div className="mission">
      <section className="field">
        {error ? (
          <div className="field-error">
            <p style={{ fontSize: 19, fontWeight: 700 }}>The plant model did not load</p>
            <p style={{ fontSize: 15, color: '#c9d5dd' }}>{error}</p>
          </div>
        ) : (
          <PlantScene
            cloud={cloud}
            assets={plant?.assets ?? []}
            attention={attention}
            selectedId={selected}
            route={route}
            blocked={access !== 'clear'}
            onSelect={setSelected}
          />
        )}
        <div className="field-label">
          {plant?.name ?? 'plant'} ·{' '}
          {plant?.source?.includes('synthetic') ? 'reference dataset' : (plant?.source ?? 'reference dataset')}
        </div>
        {current ? (
        <div className="field-bar">
          <div className="gauge">
            <b className="tnum">{route?.reachable ? `${route.distance_m} m` : 'no route'}</b>
            <i>{current ? `to the ${current.id} inspection point` : 'to the inspection point'}</i>
          </div>
          <div className="gauge">
            <b className="tnum">{route?.reachable ? `${route.clearance_m} m` : '—'}</b>
            <i>clearance</i>
          </div>
        </div>
        ) : null}
      </section>

      <aside className="sheet">
        <div className="block sheet-head">
          <p className="sheet-title">{plant?.name ?? 'plant'}</p>
          <p className="meta">
            {orders.length} machines · {orders.filter((order) => order.dueInDays < 0).length} overdue
          </p>
        </div>
        {nextOrder ? (
          <div className="block">
            <p className="label">Next inspection</p>
            <p>
              <span className="tag-id">{nextOrder.asset.id}</span>
              <span className="kind">{nextOrder.asset.kind}</span>
            </p>
            <p className={`due${nextOrder.dueInDays < 0 ? '' : ' ok'}`}>
              {Math.abs(nextOrder.dueInDays)}
              <span> {nextOrder.dueInDays < 0 ? 'days overdue' : 'days remaining'}</span>
            </p>
            <p className="meta">
              {nextOrder.asset.interval} interval, last serviced {dateLabel(nextOrder.asset.last_service)}
            </p>
            <button type="button" className="primary" onClick={() => setSelected(nextOrder.asset.id)}>
              Plan this visit
            </button>
          </div>
        ) : null}

        <div className="block">
          <p className="label">Route</p>
          {current ? (
            <p className="route-figures">
              <b className="tnum">{route?.reachable ? `${route.distance_m} m` : 'none'}</b>
              <span>
                {route?.reachable
                  ? `${route.clearance_m} m clearance`
                  : 'set a machine on the plant model'}
              </span>
            </p>
          ) : (
            <p className="lede">Set a machine on the model to plan the walk.</p>
          )}
          <div className="seg" role="group" aria-label="Access">
            {(['clear', 'aisle', 'sealed'] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                aria-pressed={access === mode}
                onClick={() => setAccess(mode)}
              >
                {ACCESS_LABEL[mode]}
              </button>
            ))}
          </div>
          {route && !route.reachable ? <p className="reason">No route: {route.reason}</p> : null}
        </div>

        <div className="block">
          <p className="label">Reason for visit</p>
          {current ? (
            <>
              <p className="lede">{evidence?.request?.symptom ?? `${current.kind} inspection`}</p>
              {evidence?.sections?.length ? (
                <div className="citation">
                  <b>{evidence.sections[0].title}</b>
                  <p className="page">
                    Manual section {evidence.sections[0].id}, page {evidence.sections[0].page}
                  </p>
                  <p>{evidence.sections[0].quote}</p>
                </div>
              ) : (
                <p className="lede">No manual passage attached to this work order.</p>
              )}
              {evidence?.action ? (
                <p className="action-row">
                  <b>{evidence.action.part}</b>: {evidence.action.action}, {evidence.action.interval} (
                  {evidence.action.source})
                </p>
              ) : null}
            </>
          ) : (
            <p className="lede">Select a machine to read its work order.</p>
          )}
        </div>

        <div className="block">
          <p className="label">Equipment</p>
          <div className="rows">
            {orders.map(({ asset }) => {
              const order = orders.find((entry) => entry.asset.id === asset.id)
              const overdue = order ? order.dueInDays < 0 : false
              return (
                <button
                  key={asset.id}
                  type="button"
                  className="row"
                  aria-current={asset.id === selected}
                  onClick={() => setSelected(asset.id)}
                >
                  <span className="row-id">{asset.id}</span>
                  <span className="row-kind">{asset.kind}</span>
                  <span className={`row-due${overdue ? '' : ' ok'}`}>
                    {order ? (overdue ? `overdue ${Math.abs(order.dueInDays)} d` : `due in ${order.dueInDays} d`) : ''}
                  </span>
                </button>
              )
            })}
          </div>
        </div>

        <div className="block">
          <p className="meta">PlantPilot {plant ? 'v0.1.0' : ''}</p>
        </div>
      </aside>
    </div>
  )
}
