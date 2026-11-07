import { useEffect, useMemo, useRef, useState } from 'react'
import {
  CLASS_COLOURS,
  STATE_COLOURS,
  STATE_LABEL,
  fetchReroute,
  fetchRoomAnchors,
  fetchRoomFilters,
  fetchRoomMeshes,
  fetchRoomObjectSplats,
  fetchRoomAssets,
  fetchRoomMapped,
  fetchDiagnosis,
  fetchRoomObjects,
  fetchRoomRoute,
  filterAssetUrl,
  splatAssetUrl,
} from './api'
import type { Diagnosis, MappedAsset, RoomAnchor, RoomAnchors, RoomAsset, RoomAssets, RoomFilters, RoomMapped, RoomMesh, RoomMeshes, RoomObjectSplats, RoomObjects, RoomObject, RoomRoute } from './api'
import SplatRoom, { type TripState } from './SplatRoom'
import ViewToolbar from '../components/ViewToolbar'

type Props = {
  onLeave: () => void
}

export default function RoomLab({ onLeave }: Props) {
  const [data, setData] = useState<RoomObjects | null>(null)
  const [anchors, setAnchors] = useState<RoomAnchors | null>(null)
  const [filters, setFilters] = useState<RoomFilters | null>(null)
  const [meshes, setMeshes] = useState<RoomMeshes | null>(null)
  const [objectSplats, setObjectSplats] = useState<RoomObjectSplats | null>(null)
  const [explode, setExplode] = useState(0)
  const [obstacleMode, setObstacleMode] = useState(false)
  const [obstacles, setObstacles] = useState<[number, number][]>([])
  const [rerouteNote, setRerouteNote] = useState<string | null>(null)
  const [showOccupancy, setShowOccupancy] = useState(false)
  const [originalRoute, setOriginalRoute] = useState<RoomRoute | null>(null)
  const robotPositionRef = useRef<[number, number] | null>(null)
  const [filterName, setFilterName] = useState(() => new URLSearchParams(window.location.search).get('filter') ?? 'photo')
  const [assets, setAssets] = useState<RoomAssets | null>(null)
  const [showRaw, setShowRaw] = useState(false)
  const [minConfidence, setMinConfidence] = useState(0.5)
  const [mapped, setMapped] = useState<RoomMapped | null>(null)
  const [route, setRoute] = useState<RoomRoute | null>(null)
  const [trip, setTrip] = useState<TripState>({ mode: 'idle', travelled: 0, total: 0 })
  const [nearby, setNearby] = useState<string[]>([])
  const [diagnosis, setDiagnosis] = useState<Diagnosis | null>(null)
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
      .then((value) => {
        if (alive) {
          setRoute(value)
          setOriginalRoute(value)
        }
      })
      .catch(() => undefined)
    // The reviewed anchors are the demo layer; the automatic proposal layer is
    // the fallback, and the raw extraction is the last resort.
    fetchRoomAnchors()
      .then((value) => alive && setAnchors(value))
      .catch(() => undefined)
    fetchRoomFilters()
      .then((value) => alive && setFilters(value))
      .catch(() => undefined)
    fetchRoomMeshes()
      .then((value) => alive && setMeshes(value))
      .catch(() => undefined)
    fetchRoomObjectSplats()
      .then((value) => alive && setObjectSplats(value))
      .catch(() => undefined)
    fetchRoomAssets()
      .then((value) => alive && setAssets(value))
      .catch(() => undefined)
    return () => {
      alive = false
    }
  }, [])

  const mappedByObject = useMemo(() => {
    const byObject = new Map<string, MappedAsset>()
    for (const mapping of mapped?.mappings ?? []) {
      if (mapping.object_id) {
        byObject.set(mapping.object_id, mapping)
      }
    }
    return byObject
  }, [mapped])

  const mappedIds = useMemo(() => [...mappedByObject.keys()], [mappedByObject])

  const anchorsPresent = (anchors?.anchors.length ?? 0) > 0
  const visibleAssets = useMemo<RoomObject[]>(() => {
    if (anchorsPresent) {
      return (anchors?.anchors ?? []).map((anchor: RoomAnchor): RoomObject => ({
        id: anchor.id,
        centre: anchor.centre,
        axes: anchor.axes,
        extents: anchor.extents,
        points: anchor.points,
        class: anchor.class,
        class_confidence: 1,
        class_reason: anchor.note,
        height_above_floor: 0,
        volume_m3: anchor.extents[0] * anchor.extents[1] * anchor.extents[2],
        planarity: 0,
        label: anchor.label,
        verified: true,
        confidence: 1,
        source_object_ids: anchor.source_object_ids,
        method: 'reviewed_anchor',
        reviewed: true,
      }))
    }
    const list = assets?.assets ?? []
    return list
      .filter((asset) => asset.verified && asset.confidence >= minConfidence)
      .map((asset: RoomAsset): RoomObject => ({
        id: asset.id,
        centre: asset.centre,
        axes: asset.axes,
        extents: asset.extents,
        points: asset.points,
        class: asset.class,
        class_confidence: asset.confidence,
        class_reason: asset.reason,
        height_above_floor: 0,
        volume_m3: asset.extents[0] * asset.extents[1] * asset.extents[2],
        planarity: 0,
        label: asset.label,
        verified: asset.verified,
        confidence: asset.confidence,
        source_object_ids: asset.source_object_ids,
        method: asset.method,
      }))
  }, [anchors, anchorsPresent, assets, minConfidence])

  const assetsActive = (anchors !== null || assets !== null) && visibleAssets.length > 0 && !showRaw
  const displayObjects = assetsActive ? visibleAssets : (data?.objects ?? [])

  const mappedByAsset = useMemo(() => {
    const byAsset = new Map<string, MappedAsset>()
    for (const record of visibleAssets) {
      for (const source of record.source_object_ids ?? []) {
        const mapping = mappedByObject.get(source)
        if (mapping) {
          byAsset.set(record.id, mapping)
          break
        }
      }
    }
    return byAsset
  }, [visibleAssets, mappedByObject])

  const displayMappedIds = assetsActive
    ? visibleAssets.filter((asset) => mappedByAsset.has(asset.id)).map((asset) => asset.id)
    : mappedIds
  const displayTargetId = assetsActive
    ? visibleAssets.find((asset) => (asset.source_object_ids ?? []).includes(mapped?.target_object_id ?? ''))?.id ?? null
    : (mapped?.target_object_id ?? null)

  const viewerObjects = useMemo(
    () => (objectSplats?.objects ?? []).map((entry) => ({
      id: entry.anchor_id,
      label: entry.label,
      url: `/api/object-splat/${entry.anchor_id}`,
      kind: 'splat' as const,
    })),
    [objectSplats],
  )
  const objectAssets = viewerObjects.length > 0 ? viewerObjects : (meshes?.objects ?? []).map((entry: RoomMesh) => ({
    id: entry.anchor_id,
    label: entry.label,
    url: `/api/mesh/${entry.anchor_id}`,
    kind: 'mesh' as const,
  }))
  const hasObjectAssets = objectAssets.length > 0

  const targetPoint = useMemo<[number, number, number] | null>(() => {
    const targetObject = mapped?.target_object_id
    if (!targetObject || displayTargetId) {
      return null
    }
    const object = data?.objects.find((candidate) => candidate.id === targetObject)
    return object ? object.centre : null
  }, [mapped, displayTargetId, data])

  const assetBySource = useMemo(() => {
    const bySource = new Map<string, RoomObject>()
    for (const asset of visibleAssets) {
      for (const source of asset.source_object_ids ?? []) {
        bySource.set(source, asset)
      }
    }
    return bySource
  }, [visibleAssets])

  const selectObjectId = (rawId: string) => {
    const asset = assetsActive ? assetBySource.get(rawId) : undefined
    setSelectedId(asset ? asset.id : rawId)
    setPanelOpen(true)
  }

  const attention = useMemo(
    () => (mapped?.mappings ?? []).filter((mapping) => mapping.state !== 'healthy'),
    [mapped],
  )

  const faults = useMemo(
    () => (mapped?.mappings ?? []).filter((mapping) => mapping.state === 'attention_required'),
    [mapped],
  )

  const selected = useMemo(() => {
    const found = displayObjects.find((object) => object.id === selectedId)
    return found ?? data?.objects.find((object) => object.id === selectedId) ?? null
  }, [displayObjects, data, selectedId])

  const selectedMapping = useMemo(() => {
    if (!selectedId) {
      return null
    }
    const direct = mappedByObject.get(selectedId)
    if (direct) {
      return direct
    }
    const asset = assets?.assets.find((candidate) => candidate.id === selectedId)
    if (!asset) {
      return null
    }
    for (const source of asset.source_object_ids) {
      const mapping = mappedByObject.get(source)
      if (mapping) {
        return mapping
      }
    }
    return null
  }, [selectedId, mappedByObject, assets])

  const routeReady = Boolean(route?.reachable && (route.path?.length ?? 0) > 1)

  useEffect(() => {
    if (trip.mode !== 'arrived' || diagnosis) {
      return
    }
    let alive = true
    fetchDiagnosis()
      .then((value) => {
        if (alive && value) {
          setDiagnosis(value)
          setPanelOpen(true)
        }
      })
      .catch(() => undefined)
    return () => {
      alive = false
    }
  }, [trip.mode, diagnosis])

  const nearbyAssets = useMemo(() => {
    const seen = new Set<string>()
    const result: MappedAsset[] = []
    const push = (mapping: MappedAsset | undefined) => {
      if (mapping && !seen.has(mapping.tag)) {
        seen.add(mapping.tag)
        result.push(mapping)
      }
    }
    for (const id of nearby) {
      if (assetsActive) {
        const asset = visibleAssets.find((candidate) => candidate.id === id)
        for (const source of asset?.source_object_ids ?? []) {
          push(mappedByObject.get(source))
        }
      } else {
        push(mappedByObject.get(id))
      }
    }
    return result
  }, [nearby, assetsActive, visibleAssets, mappedByObject])

  const placeObstacle = (point: [number, number]) => {
    const blocker: number[] = [
      Math.round((point[0] - 0.18) * 100) / 100,
      Math.round((point[1] - 0.18) * 100) / 100,
      Math.round((point[0] + 0.18) * 100) / 100,
      Math.round((point[1] + 0.18) * 100) / 100,
    ]
    const next = [...obstacles, point]
    setObstacles(next)
    setOriginalRoute((previous) => previous ?? route)
    const start = robotPositionRef.current
    fetchReroute([...obstacles.map((item) => [item[0] - 0.18, item[1] - 0.18, item[0] + 0.18, item[1] + 0.18]), blocker], start)
      .then((result) => {
        setRoute(result)
        if (!result.reachable) {
          setRerouteNote('Blocked: no alternative path from here')
          return
        }
        setRerouteNote(
          `Rerouted live: ${(result.distance_m ?? 0).toFixed(1)} m, ${(result.clearance_m ?? 0).toFixed(2)} m clear`,
        )
        if (trip.mode === 'moving') {
          setTripToken((value) => value + 1)
        }
      })
      .catch(() => setRerouteNote('Reroute failed'))
  }

  const clearObstacles = () => {
    setObstacles([])
    setObstacleMode(false)
    setRerouteNote(null)
    const restore = originalRoute ?? route
    if (restore) {
      setRoute(restore)
    }
  }

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
                  objects={displayObjects}
                  frameObjects={data.objects}
                  selectedLabel={
                    selected
                      ? `${selected.id} · ${selected.label ?? selected.class}${
                          selected.verified === undefined
                            ? ''
                            : ` · ${Math.round((selected.confidence ?? selected.class_confidence) * 100)}%`
                        }`
                      : ''
                  }
                  frameKey={`${data.source.scene}:${data.source.points}`}
                  subtle={assetsActive}
                  upAxis={data.source.up_axis}
                  floorHeight={data.floor.height}
                  resetToken={resetToken}
                  mappedIds={displayMappedIds}
                  targetId={displayTargetId}
                  targetPoint={targetPoint}
                  cameraPose={data.camera ?? null}
                  maxSplats={data.source.points + 20_000}
                  splatUrl={splatAssetUrl(data.source.points)}
                  filterUrl={filterName === 'photo' || filterName === 'objects' ? null : filterAssetUrl(filterName)}
                  contourUrl={filterName === 'edges' || filterName === 'semantics' ? '/api/filter/contours' : null}
                  objectOverlayUrl={filterName === 'semantics' ? '/api/filter/anchors_overlay' : null}
                  showLabels={filterName !== 'photo'}
                  framesVisible={filterName === 'photo'}
                  objectMode={filterName === 'objects'}
                  hideSplat={filterName === 'objects'}
                  explode={explode}
                  objectAssets={objectAssets}
                  obstacleMode={obstacleMode}
                  obstacles={obstacles}
                  robotPositionRef={robotPositionRef}
                  onPlaceObstacle={placeObstacle}
                  showOccupancy={showOccupancy}
                  route={route}
                  tripToken={tripToken}
                  follow={follow}
                  focus={follow || trip.mode === 'moving'}
                  onNearby={setNearby}
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
                {data
                  ? `${data.source.points.toLocaleString()} gaussians · ${
                      assetsActive
                        ? anchorsPresent
                          ? `${visibleAssets.length} reviewed of ${data.counts.objects} objects`
                          : `${visibleAssets.length} validated of ${data.counts.objects} objects`
                        : `${data.counts.objects} raw objects`
                    }`
                  : 'loading'}
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

            {filters && filters.filters.applied.length > 0 ? (
              <div className="absolute left-3 top-[6.2rem] z-20 flex flex-wrap gap-1 rounded-lg border border-slate-700/80 bg-slate-950/80 p-1 backdrop-blur">
                {['photo', ...(hasObjectAssets ? ['objects'] : []), ...filters.filters.applied].map((name) => (
                  <button
                    key={name}
                    type="button"
                    onClick={() => setFilterName(name)}
                    className={`rounded px-1.5 py-1 text-[10px] font-black uppercase tracking-wide ${
                      filterName === name
                        ? 'bg-cyan-500/20 text-cyan-200 ring-1 ring-cyan-400'
                        : 'text-slate-300 hover:bg-slate-800/80'
                    }`}
                  >
                    {name}
                  </button>
                ))}
              </div>
            ) : null}


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
              {nearbyAssets.length > 0 ? (
                <div className="mt-2 border-t border-slate-700/70 pt-2">
                  <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">
                    Nearby assets
                  </p>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {nearbyAssets.slice(0, 6).map((mapping) => (
                      <span
                        key={mapping.tag}
                        className="rounded border px-1.5 py-0.5 text-[10px] font-black uppercase tracking-wide"
                        style={{ borderColor: STATE_COLOURS[mapping.state], color: STATE_COLOURS[mapping.state] }}
                      >
                        {mapping.tag}
                      </span>
                    ))}
                  </div>
                </div>
              ) : null}
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
                className="absolute inset-x-0 bottom-0 top-auto z-30 flex max-h-[64%] flex-col overflow-y-auto rounded-t-2xl border-t border-slate-700 bg-slate-950/95 p-4 shadow-2xl backdrop-blur-md lg:inset-y-0 lg:left-auto lg:right-0 lg:w-[390px] lg:max-h-none lg:rounded-none lg:border-l lg:border-t-0"
              >
                <p className="text-[10px] font-black uppercase tracking-[0.18em] text-slate-500">Supplied scene</p>
                <h2 className="text-xl font-black leading-tight text-white">
                  {selected ? selected.id : roomName}
                </h2>

                <section className="order-1 mt-3 rounded-xl border border-red-500/50 bg-red-500/5 p-3">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-black uppercase tracking-[0.16em] text-red-300">Mission</span>
                    <span className="text-[10px] font-black uppercase tracking-wide text-slate-400">
                      {routeReady ? `${(route?.distance_m ?? 0).toFixed(1)} m route` : 'no route'}
                    </span>
                  </div>
                  <p className="mt-1 text-sm font-semibold text-slate-300">
                    Drive to the faulty device, highlight the equipment it passes and inspect what the pack says.
                  </p>
                  <button
                    type="button"
                    onClick={() => {
                      if (mapped?.target_object_id) {
                        selectObjectId(mapped.target_object_id)
                      }
                    }}
                    className="mt-2 flex w-full items-center justify-between rounded-lg border border-red-500/60 bg-red-500/10 px-2.5 py-1.5 text-left hover:border-red-400"
                  >
                    <span className="text-sm font-black text-white">
                      {mapped?.target_tag ?? 'P-005'}{' '}
                      <span className="font-semibold text-red-300">FOULING</span>
                    </span>
                    <span className="text-[10px] font-black uppercase tracking-wide text-red-300">
                      {displayTargetId ?? mapped?.target_object_id ?? 'target'}
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
                    {routeReady ? `Send robot to ${mapped?.target_tag ?? 'the target'}` : 'Route not planned yet'}
                  </button>
                  <p className="mt-1 text-[10px] font-bold uppercase tracking-wide text-slate-500">
                    mapping is a proposal, not a confirmed identification
                  </p>
                  <div className="mt-2 flex gap-1">
                    <button
                      type="button"
                      onClick={() => setObstacleMode((value) => !value)}
                      className={`flex-1 rounded-md border px-2 py-1 text-[10px] font-black uppercase tracking-wide ${
                        obstacleMode
                          ? 'border-amber-400 bg-amber-500/20 text-amber-200'
                          : 'border-slate-700 bg-slate-950 text-slate-300 hover:border-slate-500'
                      }`}
                    >
                      {obstacleMode ? 'Click the floor' : 'Place obstacle'}
                    </button>
                    <button
                      type="button"
                      onClick={() => setShowOccupancy((value) => !value)}
                      className={`rounded-md border px-2 py-1 text-[10px] font-black uppercase tracking-wide ${
                        showOccupancy
                          ? 'border-cyan-400 bg-cyan-500/20 text-cyan-200'
                          : 'border-slate-700 bg-slate-950 text-slate-300 hover:border-slate-500'
                      }`}
                    >
                      Area
                    </button>
                    {obstacles.length > 0 ? (
                      <button
                        type="button"
                        onClick={clearObstacles}
                        className="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-[10px] font-black uppercase tracking-wide text-slate-300 hover:border-slate-500"
                      >
                        Clear
                      </button>
                    ) : null}
                  </div>
                  {rerouteNote ? (
                    <p className="mt-1 text-[10px] font-semibold leading-snug text-amber-200">{rerouteNote}</p>
                  ) : null}
                </section>

                <section className="order-4 mt-3 rounded-xl border border-slate-700 bg-slate-900/70 p-3">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-black uppercase tracking-[0.16em] text-slate-500">Objects</span>
                    <span className="text-[10px] font-black uppercase tracking-wide text-slate-400">
                      {anchorsPresent
                        ? `${anchors?.counts.anchors ?? 0} reviewed · ${data?.counts.objects ?? 0} raw`
                        : assets
                          ? `${assets.counts.assets} clean · ${data?.counts.objects ?? 0} raw`
                          : 'raw extraction'}
                    </span>
                  </div>
                  <div className="mt-2 grid grid-cols-2 gap-1">
                    <button
                      type="button"
                      onClick={() => setShowRaw(false)}
                      disabled={!assets}
                      className={`rounded-md border px-2 py-1 text-[11px] font-black uppercase tracking-wide ${
                        !showRaw && assets
                          ? 'border-cyan-400 bg-cyan-500/15 text-cyan-200'
                          : 'border-slate-700 bg-slate-950 text-slate-300 hover:border-slate-500'
                      } ${!assets ? 'cursor-not-allowed opacity-40' : ''}`}
                    >
                      {anchorsPresent ? 'Reviewed' : 'Validated'}
                    </button>
                    <button
                      type="button"
                      onClick={() => setShowRaw(true)}
                      className={`rounded-md border px-2 py-1 text-[11px] font-black uppercase tracking-wide ${
                        showRaw
                          ? 'border-cyan-400 bg-cyan-500/15 text-cyan-200'
                          : 'border-slate-700 bg-slate-950 text-slate-300 hover:border-slate-500'
                      }`}
                    >
                      Raw detections
                    </button>
                  </div>
                  {assets && !anchorsPresent ? (
                    <label className="mt-2 block text-[10px] font-black uppercase tracking-[0.12em] text-slate-500">
                      Minimum confidence {Math.round(minConfidence * 100)} %
                      <input
                        type="range"
                        min={0}
                        max={1}
                        step={0.05}
                        value={minConfidence}
                        onChange={(event) => setMinConfidence(Number(event.target.value))}
                        className="mt-1 w-full accent-cyan-400"
                      />
                    </label>
                  ) : null}
                  {hasObjectAssets ? (
                    <label className="mt-2 block text-[10px] font-black uppercase tracking-[0.12em] text-slate-500">
                      Explode objects {Math.round(explode * 100)} %
                      <input
                        type="range"
                        min={0}
                        max={1}
                        step={0.05}
                        value={explode}
                        onChange={(event) => setExplode(Number(event.target.value))}
                        className="mt-1 w-full accent-cyan-400"
                      />
                    </label>
                  ) : null}
                  <p className="mt-2 text-[11px] font-semibold leading-snug text-slate-400">
                    {showRaw
                      ? 'All extracted geometric boxes, shown for debugging. Switch to Reviewed for the demo layer.'
                      : assetsActive
                        ? anchorsPresent
                          ? 'Seven boxes survived a visual audit. Their labels say what the box contains, not what a shape rule guessed.'
                          : 'Validated equipment instances only. Raw geometric boxes stay available for debugging.'
                        : anchorsPresent
                          ? 'Loading the reviewed layer, showing the raw extraction meanwhile.'
                          : assets
                            ? 'No instance passes the confidence filter, showing the raw extraction.'
                            : 'Showing the raw extraction because no reviewed or proposal layer exists yet.'}
                  </p>
                </section>

                {assetsActive ? (
                  <section className="order-3 mt-3 rounded-xl border border-slate-700 bg-slate-900/70 p-3">
                    <div className="flex items-center justify-between">
                      <p className="text-[10px] font-black uppercase tracking-[0.16em] text-slate-500">
                        {anchorsPresent ? 'Reviewed objects' : 'Validated objects'}
                      </p>
                      <span className="text-[10px] font-black uppercase tracking-wide text-slate-400">
                        {visibleAssets.length}
                      </span>
                    </div>
                    <div className="mt-2 max-h-44 space-y-0.5 overflow-y-auto pr-1">
                      {[...visibleAssets]
                        .sort((a, b) => (b.confidence ?? 0) - (a.confidence ?? 0))
                        .slice(0, 16)
                        .map((asset) => (
                          <button
                            key={asset.id}
                            type="button"
                            onClick={() => selectObjectId(asset.id)}
                            className="flex w-full items-center justify-between gap-2 rounded px-1.5 py-1 text-left hover:bg-slate-800/70"
                          >
                            <span className="truncate text-[11px] font-black text-slate-200">
                              {asset.id}{' '}
                              <span className="font-bold text-slate-400">{asset.label ?? asset.class}</span>
                            </span>
                            <span className="shrink-0 text-[10px] font-black text-cyan-300">
                              {Math.round((asset.confidence ?? 0) * 100)}%
                            </span>
                          </button>
                        ))}
                    </div>
                  </section>
                ) : null}

                <section className="order-7 mt-3 rounded-xl border border-slate-700 bg-slate-900/70 p-3">
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
                  <section className="order-6 mt-3 rounded-xl border border-slate-700 bg-slate-900/70 p-3">
                    <div className="flex items-center justify-between">
                      <p className="text-[10px] font-black uppercase tracking-[0.16em] text-slate-500">Builder assets</p>
                      <span className="text-[10px] font-black uppercase tracking-wide text-slate-400">
                        {mapped.counts.mapped}/{mapped.counts.assets} proposed
                      </span>
                    </div>
                    <p className="mt-1 text-sm font-semibold text-slate-300">
                      {attention.length} of {mapped.counts.mapped} proposed need attention
                      {faults.length > 0 ? `, ${faults.length} attention required` : ''}
                    </p>
                    <div className="mt-2 max-h-36 space-y-0.5 overflow-y-auto pr-1">
                      {mapped.mappings
                        .filter((mapping) => mapping.state !== 'healthy')
                        .map((mapping) => (
                          <button
                            key={mapping.tag}
                            type="button"
                            onClick={() => {
                              if (mapping.object_id) {
                                selectObjectId(mapping.object_id)
                              }
                            }}
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

                {diagnosis ? (
                  <section className="order-2 mt-3 rounded-xl border border-red-500/50 bg-red-500/5 p-3">
                    <div className="flex items-center justify-between">
                      <p className="text-[10px] font-black uppercase tracking-[0.16em] text-red-300">Diagnosis on arrival</p>
                      <span className="text-[10px] font-black uppercase tracking-wide text-red-200">
                        {diagnosis.issue?.urgency ?? 'n/a'} urgency
                      </span>
                    </div>
                    <p className="mt-1 text-lg font-black text-white">{diagnosis.issue?.code ?? 'finding'}</p>
                    <p className="text-xs font-semibold text-slate-300">
                      {diagnosis.issue?.summary} · condition {diagnosis.condition} · health {diagnosis.health_score}
                    </p>
                    {diagnosis.trend?.available && (diagnosis.trend.points ?? []).length >= 5 ? (
                      <div className="mt-2 rounded-md border border-slate-700 bg-slate-950/60 px-2 py-1.5">
                        <div className="flex items-center justify-between">
                          <span className="text-[10px] font-black uppercase tracking-[0.12em] text-slate-400">
                            {diagnosis.trend.metric} ({diagnosis.trend.unit})
                          </span>
                          <span className="text-[10px] font-black text-red-300">
                            {diagnosis.trend.summary ? `${diagnosis.trend.summary.change_percent > 0 ? '+' : ''}${diagnosis.trend.summary.change_percent.toFixed(1)} %` : ''}
                          </span>
                        </div>
                        <svg viewBox="0 0 100 28" className="mt-1 h-8 w-full" role="img" aria-label={`${diagnosis.trend.metric} trend`}>
                          <polyline
                            fill="none"
                            stroke="#f87171"
                            strokeWidth="1.6"
                            points={(() => {
                              const values = diagnosis.trend.points.map((point) => point.value)
                              const min = Math.min(...values)
                              const max = Math.max(...values)
                              const span = max - min || 1
                              return values
                                .map((value, index) => {
                                  const x = (index / Math.max(1, values.length - 1)) * 100
                                  const y = 26 - ((value - min) / span) * 24
                                  return `${x.toFixed(1)},${y.toFixed(1)}`
                                })
                                .join(' ')
                            })()}
                          />
                        </svg>
                        <p className="text-[10px] font-semibold leading-snug text-slate-400">{diagnosis.trend.why}</p>
                      </div>
                    ) : null}
                    {(diagnosis.findings ?? []).map((finding) => (
                      <div key={finding.finding_id} className="mt-2">
                        <p className="text-xs font-semibold text-slate-300">
                          {finding.statement}{' '}
                          <span className="text-slate-500">
                            ({Math.round(finding.confidence * 100)} % confidence, {finding.evidence_ids.length} evidence refs)
                          </span>
                        </p>
                        {(finding.evidence ?? []).slice(0, 5).map((item) => (
                          <p key={item.ref} className="mt-1 text-[11px] leading-snug text-slate-400">
                            <span className="mr-1 rounded border border-slate-600 bg-slate-950/70 px-1 py-0.5 text-[9px] font-black uppercase tracking-wide text-cyan-300">
                              {item.kind}
                            </span>
                            <span className="font-bold text-slate-200">{item.ref}</span> {item.detail ?? item.label}
                          </p>
                        ))}
                      </div>
                    ))}
                    {diagnosis.data_quality?.confidence_effect ? (
                      <p className="mt-2 rounded-md border border-amber-500/40 bg-amber-500/5 px-2 py-1.5 text-[11px] font-semibold leading-snug text-amber-200">
                        {diagnosis.data_quality.confidence_effect}
                      </p>
                    ) : null}
                    {diagnosis.next_safe_check ? (
                      <p className="mt-2 rounded-md border border-slate-700 bg-slate-950/60 px-2 py-1.5 text-xs font-semibold text-slate-200">
                        Next safe check: {diagnosis.next_safe_check.action}
                        <span className="block text-slate-400">{diagnosis.next_safe_check.reason}</span>
                      </p>
                    ) : null}
                    {(diagnosis.citations ?? []).slice(0, 2).map((citation) => (
                      <p key={citation.doc_id} className="mt-1.5 rounded-md border border-slate-700 bg-slate-950/60 px-2 py-1.5 text-[11px] font-semibold leading-snug text-slate-400">
                        <span className="font-black text-slate-300">{citation.doc_id}</span> {citation.title}
                        {citation.excerpt ? <span className="mt-0.5 block italic text-slate-300">"{citation.excerpt}"</span> : null}
                        {citation.synthetic_record ? (
                          <span className="mt-0.5 block text-[9px] font-bold uppercase tracking-wide text-slate-500">
                            synthetic record
                          </span>
                        ) : null}
                      </p>
                    ))}
                  </section>
                ) : null}

                {selected ? (
                  <section className="order-5 mt-3 rounded-xl border border-slate-700 bg-slate-900/70 p-3">
                    <p className="text-[10px] font-black uppercase tracking-[0.16em] text-slate-500">Framed object</p>
                    <p className="mt-1 text-lg font-black text-white">
                      {selected.id}{' '}
                      <span className="font-bold" style={{ color: CLASS_COLOURS[selected.class] ?? CLASS_COLOURS.unknown }}>
                        {selected.label ?? selected.class}
                      </span>
                    </p>
                    <p className="text-xs font-semibold text-slate-400">
                      {selected.reviewed
                        ? 'Reviewed box from the audit; generic label because the geometry does not prove a machine class.'
                        : selected.method === 'colour_instance'
                          ? 'Colour-seeded instance, one box around the gaussian cluster.'
                          : selected.class_reason}
                    </p>
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
                          {selectedMapping.class} · {selectedMapping.issue_code.toLowerCase()} · match score{' '}
                          {selectedMapping.match_score?.toFixed(2) ?? selectedMapping.confidence?.toFixed(2) ?? 'unresolved'} via{' '}
                          {selectedMapping.method} (a proposal, not a confirmed identification)
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
                        <dd className="font-black text-white">
                          {Math.round((selected.confidence ?? selected.class_confidence) * 100)} %
                        </dd>
                      </div>
                      <div>
                        <dt className="text-[10px] font-black uppercase tracking-[0.12em] text-slate-500">Size</dt>
                        <dd className="font-black text-white">
                          {selected.extents.map((value) => value.toFixed(2)).join(' x ')}
                        </dd>
                      </div>
                      {selected.verified === undefined ? (
                        <div>
                          <dt className="text-[10px] font-black uppercase tracking-[0.12em] text-slate-500">Above floor</dt>
                          <dd className="font-black text-white">{selected.height_above_floor.toFixed(2)}</dd>
                        </div>
                      ) : (
                        <div>
                          <dt className="text-[10px] font-black uppercase tracking-[0.12em] text-slate-500">Status</dt>
                          <dd className="font-black text-white">{selected.verified ? 'validated' : 'proposal'}</dd>
                        </div>
                      )}
                    </dl>
                    {(selected.source_object_ids ?? []).length > 0 ? (
                      <p className="mt-2 text-[10px] font-bold uppercase tracking-wide text-slate-500">
                        Source frames: {(selected.source_object_ids ?? []).join(', ')}
                      </p>
                    ) : null}
                  </section>
                ) : (
                  <p className="order-5 mt-3 rounded-xl border border-slate-700 bg-slate-900/70 p-3 text-sm font-semibold text-slate-400">
                    Click an object in the room. Validated assets show one box per physical object; raw detections
                    are available in the Objects panel and exist for debugging, not for the demo.
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
