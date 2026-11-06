import { useEffect, useMemo, useState } from 'react'
import {
  CLASS_COLOURS,
  STATE_COLOURS,
  STATE_LABEL,
  fetchRoomMapped,
  fetchRoomObjects,
  fetchRoomRoute,
  splatAssetUrl,
} from './api'
import type { MappedAsset, RoomMapped, RoomObjects, RoomRoute } from './api'
import SplatRoom, { type TripState } from './SplatRoom'
import ViewToolbar from '../components/ViewToolbar'

type Props = {
  onLeave: () => void
}

export default function RoomLab({ onLeave }: Props) {
  const [data, setData] = useState<RoomObjects | null>(null)
  const [mapped, setMapped] = useState<RoomMapped | null>(null)
  const [route, setRoute] = useState<RoomRoute | null>(null)
  const [trip, setTrip] = useState<TripState>({ mode: 'idle', travelled: 0, total: 0 })
  const [follow, setFollow] = useState(false)
  const [tripToken, setTripToken] = useState(0)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [panelOpen, setPanelOpen] = useState(true)
  const [resetToken, setResetToken] = useState(0)

  useEffect(() => {
    let alive = true
    fetchRoomObjects()
      .then((value) => {
        if (alive) {
          setData(value)
        }
      })
      .catch((problem: Error) => alive && setError(problem.message))
      .finally(() => alive && setLoading(false))
    // The mapping artifact is optional: without make map the room still shows
    // the extracted objects, just without the builder assets.
    fetchRoomMapped()
      .then((value) => alive && setMapped(value))
      .catch(() => undefined)
    fetchRoomRoute()
      .then((value) => alive && setRoute(value))
      .catch(() => undefined)
    return () => {
      alive = false
    }
  }, [])

  const selected = useMemo(
    () => data?.objects.find((object) => object.id === selectedId) ?? null,
    [data, selectedId],
  )

  const mappedByObject = useMemo(() => {
    const byObject = new Map<string, MappedAsset>()
    for (const mapping of mapped?.mappings ?? []) {
      byObject.set(mapping.object_id, mapping)
    }
    return byObject
  }, [mapped])

  const mappedIds = useMemo(() => [...mappedByObject.keys()], [mappedByObject])

  const attention = useMemo(
    () => (mapped?.mappings ?? []).filter((mapping) => mapping.state !== 'healthy'),
    [mapped],
  )

  const faults = useMemo(
    () => (mapped?.mappings ?? []).filter((mapping) => mapping.state === 'attention_required'),
    [mapped],
  )

  const selectedMapping = selectedId ? mappedByObject.get(selectedId) ?? null : null

  const routeReady = Boolean(route?.reachable && (route.path?.length ?? 0) > 1)

  const sendRobot = () => {
    if (!routeReady) {
      return
    }
    setFollow(true)
    setPanelOpen(false)
    setTripToken((value) => value + 1)
  }

  // The artifact names the capture it came from, so a second capture does not
  // keep calling itself the boiler room.
  const roomName = (() => {
    const capture = data?.source.capture ?? ''
    if (capture) {
      return capture.replace(/\.ply$/i, '').replace(/^\(\d+\)\s*/, '').trim()
    }
    const scene = data?.source.scene ?? ''
    const folder = scene.split('/').filter(Boolean).slice(-2, -1)[0] ?? 'scene'
    return folder === 'scene' ? 'Supplied scene' : `${folder.charAt(0).toUpperCase()}${folder.slice(1)} room`
  })()

  const classes = useMemo(() => {
    const counts = data?.counts.objects_by_class ?? {}
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
  }, [data])

  return (
    <div className="relative h-screen w-full overflow-hidden bg-slate-950">
      <section className="relative h-full w-full overflow-hidden">
        {error ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 px-8 text-center">
            <p className="text-xl font-black text-white">The real capture is not loaded</p>
            <p className="max-w-xl text-base font-semibold text-slate-300">{error}</p>
            <code className="rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm font-bold text-cyan-300">
              make scene && make objects && make splat-asset
            </code>
            <button
              type="button"
              onClick={onLeave}
              className="mt-2 rounded-lg border border-slate-600 px-3 py-2 text-sm font-black text-slate-200 hover:border-slate-400"
            >
              Back to the scene lab
            </button>
          </div>
        ) : (
          <>
            <div className="absolute inset-0">
              {data ? (
                <SplatRoom
                  objects={data.objects}
                  upAxis={data.source.up_axis}
                  floorHeight={data.floor.height}
                  resetToken={resetToken}
                  mappedIds={mappedIds}
                  targetId={mapped?.target_object_id ?? null}
                  cameraPose={data.camera ?? null}
                  maxSplats={data.source.points + 20_000}
                  splatUrl={splatAssetUrl(data.source.points)}
                  route={route}
                  tripToken={tripToken}
                  follow={follow}
                  focus={follow || trip.mode === 'moving'}
                  onTrip={setTrip}
                  selectedId={selectedId}
                  onSelect={(id) => {
                    setSelectedId(id)
                    setPanelOpen(true)
                  }}
                />
              ) : (
                <div className="flex h-full items-center justify-center text-lg font-bold text-slate-300">
                  {loading ? 'reading the extracted objects' : 'no scene'}
                </div>
              )}
            </div>

            <div className="pointer-events-none absolute left-3 top-3 z-10 flex flex-wrap items-center gap-2 pr-28">
              <span className="rounded-md border border-cyan-400/50 bg-slate-950/80 px-2 py-1 text-xs font-black uppercase tracking-[0.16em] text-cyan-300 backdrop-blur">
                Real capture
              </span>
              <span className="rounded-md border border-slate-600/70 bg-slate-950/70 px-2 py-1 text-xs font-bold text-slate-300 backdrop-blur">
                {data ? `${data.source.points.toLocaleString()} gaussians · ${data.counts.objects} framed objects` : 'loading'}
              </span>
              <span className="rounded-md border border-slate-600/70 bg-slate-950/70 px-2 py-1 text-xs font-bold text-slate-300 backdrop-blur">
                click a box to inspect
              </span>
            </div>

            <ViewToolbar
              follow={follow}
              followEnabled={routeReady}
              panelOpen={panelOpen}
              faultCount={faults.length}
              onOverview={() => setResetToken((value) => value + 1)}
              onFollow={() => setFollow((value) => !value)}
              onReset={() => setResetToken((value) => value + 1)}
              onTogglePanel={() => setPanelOpen((value) => !value)}
            />

            <button
              type="button"
              onClick={onLeave}
              className="absolute left-3 top-14 z-20 rounded-md border border-slate-600 bg-slate-950/80 px-2.5 py-1.5 text-xs font-black uppercase tracking-[0.12em] text-slate-200 backdrop-blur hover:border-slate-400"
            >
              scene lab
            </button>

            <div className="pointer-events-none absolute bottom-3 left-3 z-10 max-w-[62%] rounded-lg border border-slate-700/80 bg-slate-950/80 px-3 py-2 backdrop-blur">
              <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">Robot</p>
              <p className="text-base font-black text-white">
                {trip.mode === 'moving'
                  ? 'moving'
                  : trip.mode === 'arrived'
                    ? 'arrived'
                    : routeReady
                      ? 'ready'
                      : 'no route'}
              </p>
              <p className="text-sm font-semibold text-slate-300">
                {trip.mode === 'moving'
                  ? `to ${route?.target_asset_id ?? 'target'}, ${Math.max(0, trip.total - trip.travelled).toFixed(1)} m to go`
                  : trip.mode === 'arrived'
                    ? `at ${route?.target_asset_id ?? 'target'}`
                    : routeReady
                      ? `${(route?.distance_m ?? 0).toFixed(1)} m planned`
                      : (route?.reason ?? 'run make route')}
              </p>
            </div>

            <div className="pointer-events-none absolute bottom-3 right-3 z-10 rounded-lg border border-slate-700/80 bg-slate-950/80 px-3 py-2 text-right backdrop-blur">
              <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">Route</p>
              <p className="text-base font-black text-cyan-300">
                {routeReady ? `${(route?.distance_m ?? 0).toFixed(1)} m` : '-'}
              </p>
              <p className="text-sm font-semibold text-slate-300">
                {routeReady ? `${Math.max(0, (route?.path?.length ?? 1) - 1)} legs, ${(route?.clearance_m ?? 0).toFixed(2)} m clear` : 'not planned'}
              </p>
            </div>

            {panelOpen ? (
              <aside
                aria-label="Capture details"
                className="absolute inset-x-0 bottom-0 top-auto z-30 max-h-[64%] overflow-y-auto rounded-t-2xl border-t border-slate-700 bg-slate-950/95 p-4 shadow-2xl backdrop-blur-md lg:inset-y-0 lg:left-auto lg:right-0 lg:w-[390px] lg:max-h-none lg:rounded-none lg:border-l lg:border-t-0"
              >
                <p className="text-[10px] font-black uppercase tracking-[0.18em] text-slate-500">Supplied scene</p>
                <h2 className="text-xl font-black leading-tight text-white">
                  {selected ? selected.id : roomName}
                </h2>

                <section className="mt-3 rounded-xl border border-slate-700 bg-slate-900/70 p-3">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-black uppercase tracking-[0.16em] text-slate-500">Capture</span>
                    <span className="rounded-full border border-slate-600 bg-slate-950 px-2 py-0.5 text-[10px] font-black uppercase tracking-wide text-emerald-300">
                      offline
                    </span>
                  </div>
                  <dl className="mt-2 grid grid-cols-2 gap-2 text-sm">
                    <div>
                      <dt className="text-[10px] font-black uppercase tracking-[0.12em] text-slate-500">Gaussians</dt>
                      <dd className="font-black text-white">{data?.source.points.toLocaleString() ?? '-'}</dd>
                    </div>
                    <div>
                      <dt className="text-[10px] font-black uppercase tracking-[0.12em] text-slate-500">Objects</dt>
                      <dd className="font-black text-white">{data?.counts.objects ?? '-'}</dd>
                    </div>
                    <div>
                      <dt className="text-[10px] font-black uppercase tracking-[0.12em] text-slate-500">Up axis</dt>
                      <dd className="font-black text-white">{data?.source.up_axis ?? '-'}</dd>
                    </div>
                    <div>
                      <dt className="text-[10px] font-black uppercase tracking-[0.12em] text-slate-500">Largest share</dt>
                      <dd className="font-black text-white">
                        {data ? `${(data.counts.largest_object_share * 100).toFixed(1)} %` : '-'}
                      </dd>
                    </div>
                  </dl>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {classes.map(([name, count]) => (
                      <span
                        key={name}
                        className="rounded-md border px-1.5 py-0.5 text-[10px] font-black uppercase tracking-wide"
                        style={{
                          borderColor: CLASS_COLOURS[name] ?? CLASS_COLOURS.unknown,
                          color: CLASS_COLOURS[name] ?? CLASS_COLOURS.unknown,
                        }}
                      >
                        {name} {count}
                      </span>
                    ))}
                  </div>
                </section>

                {mapped ? (
                  <section className="mt-3 rounded-xl border border-slate-700 bg-slate-900/70 p-3">
                    <div className="flex items-center justify-between">
                      <p className="text-[10px] font-black uppercase tracking-[0.16em] text-slate-500">Builder assets</p>
                      <span className="text-[10px] font-black uppercase tracking-wide text-slate-400">
                        {mapped.counts.mapped}/{mapped.counts.assets} mapped
                      </span>
                    </div>
                    <p className="mt-1 text-sm font-semibold text-slate-300">
                      {attention.length} of {mapped.counts.mapped} need attention
                      {faults.length > 0 ? `, ${faults.length} attention required` : ''}
                    </p>
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedId(mapped.target_object_id)
                        setPanelOpen(true)
                      }}
                      className="mt-2 flex w-full items-center justify-between rounded-lg border border-red-500/60 bg-red-500/10 px-2.5 py-1.5 text-left hover:border-red-400"
                    >
                      <span className="text-sm font-black text-white">
                        {mapped.target_tag} <span className="font-semibold text-red-300">FOULING</span>
                      </span>
                      <span className="text-[10px] font-black uppercase tracking-wide text-red-300">
                        {mapped.target_object_id}
                      </span>
                    </button>
                    <button
                      type="button"
                      onClick={sendRobot}
                      disabled={!routeReady}
                      className={`mt-2 w-full rounded-lg px-3 py-2 text-sm font-black ${
                        routeReady
                          ? 'bg-cyan-500 text-slate-950 hover:bg-cyan-400'
                          : 'cursor-not-allowed border border-slate-700 bg-slate-900 text-slate-500'
                      }`}
                    >
                      {routeReady ? `Send robot to ${mapped.target_tag}` : 'Route not planned yet'}
                    </button>
                    <div className="mt-2 max-h-36 space-y-0.5 overflow-y-auto pr-1">
                      {mapped.mappings
                        .filter((mapping) => mapping.state !== 'healthy')
                        .map((mapping) => (
                          <button
                            key={mapping.object_id}
                            type="button"
                            onClick={() => setSelectedId(mapping.object_id)}
                            className="flex w-full items-center justify-between rounded px-1.5 py-1 text-left hover:bg-slate-800/70"
                          >
                            <span className="text-xs font-black text-slate-200">{mapping.tag}</span>
                            <span
                              className="text-[10px] font-bold uppercase tracking-wide"
                              style={{ color: STATE_COLOURS[mapping.state] }}
                            >
                              {STATE_LABEL[mapping.state]} {mapping.issue_code.toLowerCase()}
                            </span>
                          </button>
                        ))}
                    </div>
                  </section>
                ) : null}

                {selected ? (
                  <section className="mt-3 rounded-xl border border-slate-700 bg-slate-900/70 p-3">
                    <p className="text-[10px] font-black uppercase tracking-[0.16em] text-slate-500">Framed object</p>
                    <p className="mt-1 text-lg font-black text-white">
                      {selected.id}{' '}
                      <span className="font-bold" style={{ color: CLASS_COLOURS[selected.class] ?? CLASS_COLOURS.unknown }}>
                        {selected.class}
                      </span>
                    </p>
                    <p className="text-xs font-semibold text-slate-400">{selected.class_reason}</p>
                    {selectedMapping ? (
                      <div className="mt-2 rounded-md border border-slate-700 bg-slate-950/60 px-2 py-1.5">
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-black text-white">{selectedMapping.tag}</span>
                          <span
                            className="text-[10px] font-black uppercase tracking-wide"
                            style={{ color: STATE_COLOURS[selectedMapping.state] }}
                          >
                            {STATE_LABEL[selectedMapping.state]}
                          </span>
                        </div>
                        <p className="text-[11px] font-semibold text-slate-400">
                          {selectedMapping.class} · {selectedMapping.issue_code.toLowerCase()} · confidence{' '}
                          {Math.round(selectedMapping.confidence * 100)} % via {selectedMapping.method}
                        </p>
                      </div>
                    ) : null}
                    <dl className="mt-2 grid grid-cols-2 gap-2 text-sm">
                      <div>
                        <dt className="text-[10px] font-black uppercase tracking-[0.12em] text-slate-500">Points</dt>
                        <dd className="font-black text-white">{selected.points.toLocaleString()}</dd>
                      </div>
                      <div>
                        <dt className="text-[10px] font-black uppercase tracking-[0.12em] text-slate-500">Confidence</dt>
                        <dd className="font-black text-white">{Math.round(selected.class_confidence * 100)} %</dd>
                      </div>
                      <div>
                        <dt className="text-[10px] font-black uppercase tracking-[0.12em] text-slate-500">Size</dt>
                        <dd className="font-black text-white">
                          {selected.extents.map((value) => value.toFixed(2)).join(' x ')}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-[10px] font-black uppercase tracking-[0.12em] text-slate-500">Above floor</dt>
                        <dd className="font-black text-white">{selected.height_above_floor.toFixed(2)}</dd>
                      </div>
                    </dl>
                  </section>
                ) : (
                  <p className="mt-3 rounded-xl border border-slate-700 bg-slate-900/70 p-3 text-sm font-semibold text-slate-400">
                    Click a box in the room. Every frame carries a geometric class proposal and a confidence, and
                    the interface shows both rather than claiming an identification.
                  </p>
                )}

                <p className="mt-3 border-t border-slate-800 pt-3 text-[11px] font-semibold leading-relaxed text-slate-500">
                  The room is the supplied gaussian splat, rendered from the same artifact the API serves. The boxes
                  are the extracted objects; distances are in scene units, and the scale check has not confirmed
                  metres.
                </p>
              </aside>
            ) : null}
          </>
        )}
      </section>
    </div>
  )
}
