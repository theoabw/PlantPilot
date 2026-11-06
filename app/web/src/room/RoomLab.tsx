import { useEffect, useMemo, useState } from 'react'
import { CLASS_COLOURS, fetchRoomObjects } from './api'
import type { RoomObjects } from './api'
import SplatRoom from './SplatRoom'

type Props = {
  onLeave: () => void
}

export default function RoomLab({ onLeave }: Props) {
  const [data, setData] = useState<RoomObjects | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [panelOpen, setPanelOpen] = useState(true)

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
    return () => {
      alive = false
    }
  }, [])

  const selected = useMemo(
    () => data?.objects.find((object) => object.id === selectedId) ?? null,
    [data, selectedId],
  )

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

            <div className="absolute right-3 top-3 z-20 flex items-center gap-2">
              <button
                type="button"
                onClick={() => setPanelOpen((value) => !value)}
                className="rounded-md border border-slate-600 bg-slate-950/80 px-2.5 py-1.5 text-xs font-black uppercase tracking-[0.12em] text-slate-200 backdrop-blur hover:border-slate-400"
              >
                {panelOpen ? 'hide panel' : 'show panel'}
              </button>
              <button
                type="button"
                onClick={onLeave}
                className="rounded-md border border-slate-600 bg-slate-950/80 px-2.5 py-1.5 text-xs font-black uppercase tracking-[0.12em] text-slate-200 backdrop-blur hover:border-slate-400"
              >
                scene lab
              </button>
            </div>

            {panelOpen ? (
              <aside
                aria-label="Capture details"
                className="absolute inset-x-0 bottom-0 top-auto z-30 max-h-[64%] overflow-y-auto rounded-t-2xl border-t border-slate-700 bg-slate-950/95 p-4 shadow-2xl backdrop-blur-md lg:inset-y-0 lg:left-auto lg:right-0 lg:w-[380px] lg:max-h-none lg:rounded-none lg:border-l lg:border-t-0"
              >
                <p className="text-[10px] font-black uppercase tracking-[0.18em] text-slate-500">Supplied scene</p>
                <h2 className="text-xl font-black leading-tight text-white">
                  {selected ? selected.id : 'Boiler room'}
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
