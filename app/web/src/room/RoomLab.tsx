import { useEffect, useMemo, useRef, useState } from 'react'
import {
  STATE_COLOURS,
  STATE_LABEL,
  fetchRoomAnchors,
  fetchRoomAssets,
  fetchRoomFilters,
  fetchRoomMapped,
  fetchRoomMeshes,
  fetchRoomObjectSplats,
  fetchRoomObjects,
  fetchRoomRoute,
  fetchDiagnosis,
  fetchReroute,
  filterAssetUrl,
  splatAssetUrl,
} from './api'
import type {
  Diagnosis,
  MappedAsset,
  RoomAnchor,
  RoomAnchors,
  RoomAsset,
  RoomAssets,
  RoomFilters,
  RoomMapped,
  RoomMesh,
  RoomMeshes,
  RoomObject,
  RoomObjectSplats,
  RoomObjects,
  RoomRoute,
} from './api'
import SplatRoom, { type TripState } from './SplatRoom'

type Props = {
  onLeave: () => void
}

type MissionTarget = {
  tag: string
  label: string
  condition: string
  issue?: string
}

const VIEW_OPTIONS = [
  { id: 'photo', label: 'Photo' },
  { id: 'height', label: 'Height' },
  { id: 'normals', label: 'Normals' },
  { id: 'edges', label: 'Contours' },
  { id: 'semantics', label: 'Objects tinted' },
  { id: 'objects', label: 'Objects isolated' },
]

const humanize = (value: string | null | undefined): string =>
  (value ?? '').replace(/_/g, ' ').trim().toLowerCase()

const CONDITION_TEXT: Record<string, string> = {
  healthy: 'Healthy',
  watch: 'Watch',
  degraded: 'Degraded',
  attention_required: 'Needs attention',
}

type RobotOption = {
  id: 'humanoid' | 'amr' | 'cargo'
  label: string
  radius: number
}

const ROBOTS: RobotOption[] = [
  { id: 'humanoid', label: 'Humanoid', radius: 0.18 },
  { id: 'amr', label: 'Compact AMR', radius: 0.2 },
  { id: 'cargo', label: 'Cargo AMR', radius: 0.45 },
]

const routeMessage = (route: RoomRoute | null): string => {
  const reason = route?.reason ?? ''
  if (reason.includes('inspection point is blocked')) {
    return 'This robot cannot reach the pump: the inspection point is too tight.'
  }
  if (reason.includes('does not fit at its current position')) {
    return 'This robot does not fit at its current position.'
  }
  if (reason.includes('no walkable route')) {
    return 'No safe path with the current obstacle.'
  }
  return 'No safe route for this robot.'
}

const severityText = (mapping: MappedAsset | null): string => {
  if (!mapping) {
    return 'Condition unknown'
  }
  const state = CONDITION_TEXT[mapping.state] ?? STATE_LABEL[mapping.state] ?? mapping.state
  return `${state} · ${humanize(mapping.issue_code)}`
}

export default function RoomLab({ onLeave }: Props) {
  const [data, setData] = useState<RoomObjects | null>(null)
  const [anchors, setAnchors] = useState<RoomAnchors | null>(null)
  const [mapped, setMapped] = useState<RoomMapped | null>(null)
  const [route, setRoute] = useState<RoomRoute | null>(null)
  const [assets, setAssets] = useState<RoomAssets | null>(null)
  const [filters, setFilters] = useState<RoomFilters | null>(null)
  const [objectSplats, setObjectSplats] = useState<RoomObjectSplats | null>(null)
  const [meshes, setMeshes] = useState<RoomMeshes | null>(null)
  const [diagnosis, setDiagnosis] = useState<Diagnosis | null>(null)
  const [trip, setTrip] = useState<TripState>({ mode: 'idle', travelled: 0, total: 0 })
  const [nearby, setNearby] = useState<string[]>([])
  const [follow, setFollow] = useState(false)
  const [tripToken, setTripToken] = useState(0)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [view, setView] = useState('photo')
  const [showOutlines, setShowOutlines] = useState(true)
  const [showOccupancy, setShowOccupancy] = useState(false)
  const [devMode, setDevMode] = useState(false)
  const [showRawDetections, setShowRawDetections] = useState(false)
  const [layersOpen, setLayersOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [browserOpen, setBrowserOpen] = useState(false)
  const [browserQuery, setBrowserQuery] = useState('')
  const [browserFilter, setBrowserFilter] = useState<'all' | 'attention' | 'reviewed'>('all')
  const [obstacleMode, setObstacleMode] = useState(false)
  const [obstacles, setObstacles] = useState<[number, number][]>([])
  const [rerouteNote, setRerouteNote] = useState<string | null>(null)
  const [explode, setExplode] = useState(0)
  const [robotId, setRobotId] = useState<RobotOption['id']>('amr')
  const [customRadius, setCustomRadius] = useState<number | null>(null)
  const [focusToken, setFocusToken] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [resetToken, setResetToken] = useState(0)
  const [arrivalDismissed, setArrivalDismissed] = useState(false)
  const robotPositionRef = useRef<[number, number] | null>(null)
  const initialStartRef = useRef<[number, number] | null>(null)

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
    fetchRoomAnchors()
      .then((value) => alive && setAnchors(value))
      .catch(() => undefined)
    fetchRoomMapped()
      .then((value) => alive && setMapped(value))
      .catch(() => undefined)
    fetchRoomRoute()
      .then((value) => {
        if (alive) {
          setRoute(value)
          if (value?.path?.length) {
            const axes = value.grid?.horizontal_axes ?? [0, 2]
            initialStartRef.current = [value.path[0][axes[0]], value.path[0][axes[1]]]
          }
        }
      })
      .catch(() => undefined)
    fetchRoomFilters()
      .then((value) => alive && setFilters(value))
      .catch(() => undefined)
    fetchRoomObjectSplats()
      .then((value) => alive && setObjectSplats(value))
      .catch(() => undefined)
    fetchRoomMeshes()
      .then((value) => alive && setMeshes(value))
      .catch(() => undefined)
    fetchRoomAssets()
      .then((value) => alive && setAssets(value))
      .catch(() => undefined)
    return () => {
      alive = false
    }
  }, [])

  useEffect(() => {
    if (trip.mode !== 'arrived' || diagnosis) {
      return
    }
    let alive = true
    fetchDiagnosis()
      .then((value) => {
        if (alive && value) {
          setDiagnosis(value)
        }
      })
      .catch(() => undefined)
    return () => {
      alive = false
    }
  }, [trip.mode, diagnosis])

  const reviewed = useMemo<RoomObject[]>(() => {
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
  }, [anchors])

  const anchorById = useMemo(() => {
    const byId = new Map<string, RoomObject>()
    for (const record of reviewed) {
      byId.set(record.id, record)
    }
    return byId
  }, [reviewed])

  const mappedByObject = useMemo(() => {
    const byObject = new Map<string, MappedAsset>()
    for (const mapping of mapped?.mappings ?? []) {
      if (mapping.object_id) {
        byObject.set(mapping.object_id, mapping)
      }
    }
    return byObject
  }, [mapped])

  const mappedByAnchor = useMemo(() => {
    const byAnchor = new Map<string, MappedAsset>()
    for (const record of reviewed) {
      for (const source of record.source_object_ids ?? []) {
        const mapping = mappedByObject.get(source)
        if (mapping) {
          byAnchor.set(record.id, mapping)
          break
        }
      }
    }
    return byAnchor
  }, [reviewed, mappedByObject])

  const targetAnchor = useMemo(() => {
    const targetObject = mapped?.target_object_id
    if (!targetObject) {
      return null
    }
    for (const anchor of anchors?.anchors ?? []) {
      if (anchor.source_object_ids.includes(targetObject)) {
        return anchorById.get(anchor.id) ?? null
      }
    }
    return null
  }, [mapped, anchors, anchorById])

  const targetPoint: [number, number, number] | null = useMemo(() => {
    const targetObject = mapped?.target_object_id
    if (!targetObject || targetAnchor) {
      return null
    }
    const object = data?.objects.find((candidate) => candidate.id === targetObject)
    return object ? object.centre : null
  }, [mapped, targetAnchor, data])

  const targetMapping = useMemo(() => {
    if (!mapped) {
      return null
    }
    return mapped.mappings.find((record) => record.tag === mapped.target_tag) ?? null
  }, [mapped])

  const mission: MissionTarget | null = useMemo(() => {
    if (!mapped) {
      return null
    }
    return {
      tag: mapped.target_tag,
      label: targetAnchor?.label ?? (humanize(targetMapping?.class) || 'equipment'),
      condition: targetMapping ? severityText(targetMapping) : 'Mapped to the builder pack',
      issue: targetMapping?.issue_code,
    }
  }, [mapped, targetAnchor, targetMapping])

  const displayObjects = useMemo<RoomObject[]>(() => {
    if (view === 'objects') {
      return []
    }
    if (devMode && showRawDetections) {
      return data?.objects ?? []
    }
    return showOutlines ? reviewed : []
  }, [view, devMode, showRawDetections, data, showOutlines, reviewed])

  const equipmentRows = useMemo(() => {
    const rows = reviewed.map((record) => ({
      record,
      mapping: mappedByAnchor.get(record.id) ?? null,
    }))
    const targetObjectId = mapped?.target_object_id
    const targetCovered = targetObjectId
      ? reviewed.some((record) => (record.source_object_ids ?? []).includes(targetObjectId))
      : true
    if (mapped && targetMapping && targetObjectId && !targetCovered) {
      const raw = data?.objects.find((object) => object.id === targetObjectId)
      if (raw) {
        rows.unshift({
          record: {
            ...raw,
            label: humanize(targetMapping.class),
            class_reason: 'The faulty device identified by the builder pack. The frame is the mapped proposal, reviewed condition is from the pack.',
            method: 'mapping_target',
          },
          mapping: targetMapping,
        })
      }
    }
    rows.sort((left, right) => {
      const targetLeft = left.record.id === targetAnchor?.id ? 0 : 1
      const targetRight = right.record.id === targetAnchor?.id ? 0 : 1
      if (targetLeft !== targetRight) {
        return targetLeft - targetRight
      }
      const stateLeft = left.mapping?.state === 'healthy' ? 1 : 0
      const stateRight = right.mapping?.state === 'healthy' ? 1 : 0
      if (stateLeft !== stateRight) {
        return stateLeft - stateRight
      }
      return (left.record.label ?? left.record.class).localeCompare(right.record.label ?? right.record.class)
    })
    return rows
  }, [reviewed, mappedByAnchor, targetAnchor])

  const selectedRow = useMemo(() => {
    if (!selectedId) {
      return null
    }
    return equipmentRows.find((row) => row.record.id === selectedId) ?? null
  }, [selectedId, equipmentRows])

  const selectedObject = useMemo(() => {
    if (!selectedId) {
      return null
    }
    return selectedRow?.record ?? anchorById.get(selectedId) ?? data?.objects.find((object) => object.id === selectedId) ?? null
  }, [selectedId, selectedRow, anchorById, data])

  const selectedMapping = useMemo(() => {
    if (!selectedId) {
      return null
    }
    const direct = selectedRow?.mapping ?? mappedByObject.get(selectedId)
    if (direct) {
      return direct
    }
    return mappedByAnchor.get(selectedId) ?? null
  }, [selectedId, selectedRow, mappedByObject, mappedByAnchor])

  const mappedIds = useMemo(() => {
    const ids: string[] = []
    for (const record of displayObjects) {
      if (mappedByAnchor.has(record.id) || mappedByObject.has(record.id)) {
        ids.push(record.id)
      }
    }
    return ids
  }, [displayObjects, mappedByAnchor, mappedByObject])

  const displayTargetId = useMemo(() => {
    if (!targetAnchor || view === 'objects') {
      return null
    }
    return displayObjects.some((record) => record.id === targetAnchor.id) ? targetAnchor.id : null
  }, [targetAnchor, view, displayObjects])


  const filteredEquipment = useMemo(() => {
    const query = browserQuery.trim().toLowerCase()
    return equipmentRows.filter(({ record, mapping }) => {
      if (browserFilter === 'attention' && (!mapping || mapping.state === 'healthy')) {
        return false
      }
      if (browserFilter === 'reviewed' && !record.reviewed) {
        return false
      }
      if (!query) {
        return true
      }
      const haystack = [record.label, record.class, mapping?.tag, mapping?.issue_code]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()
      return haystack.includes(query)
    })
  }, [equipmentRows, browserQuery, browserFilter])

  const nearbyEquipment = useMemo(() => {
    const rows: { key: string; name: string; state: string }[] = []
    const seen = new Set<string>()
    for (const id of nearby) {
      const record = anchorById.get(id)
      const mapping = mappedByAnchor.get(id)
      const key = mapping?.tag ?? id
      if (seen.has(key)) {
        continue
      }
      seen.add(key)
      rows.push({
        key,
        name: mapping?.tag ?? record?.label ?? id,
        state: mapping?.state ?? 'healthy',
      })
    }
    return rows.slice(0, 5)
  }, [nearby, anchorById, mappedByAnchor])

  const robot = ROBOTS.find((option) => option.id === robotId) ?? ROBOTS[1]
  const clearanceRadius = customRadius ?? robot.radius

  const replanForRobot = (radius: number, note?: string) => {
    const blockers = obstacles.map((item) => [
      item[0] - 0.18,
      item[1] - 0.18,
      item[0] + 0.18,
      item[1] + 0.18,
    ])
    const start = robotPositionRef.current ?? initialStartRef.current
    fetchReroute(blockers, start, radius)
      .then((result) => {
        setRoute(result)
        if (!result.reachable) {
          setRerouteNote(note ?? `No safe route for this robot at ${radius.toFixed(2)} m clearance`)
          return
        }
        setRerouteNote(note ?? `Route replanned for ${radius.toFixed(2)} m clearance`)
        if (driving) {
          setTripToken((value) => value + 1)
        }
      })
      .catch(() => setRerouteNote('Route replan failed'))
  }

  const changeRobot = (id: RobotOption['id'], radius?: number) => {
    setRobotId(id)
    setCustomRadius(radius ?? null)
    const option = ROBOTS.find((candidate) => candidate.id === id) ?? ROBOTS[1]
    replanForRobot(radius ?? option.radius, `${(radius ?? option.radius).toFixed(2)} m clearance for the ${option.label.toLowerCase()}`)
  }

  const routeReady = Boolean(route?.reachable && (route.path?.length ?? 0) > 1)
  const driving = trip.mode === 'moving'
  const arrived = trip.mode === 'arrived'
  const remaining = Math.max(0, (trip.total || route?.distance_m || 0) - (trip.travelled || 0))
  const progress = trip.total > 0 ? Math.min(1, trip.travelled / trip.total) : 0

  const objectAssets = useMemo(() => {
    const splats = objectSplats?.objects ?? []
    if (splats.length > 0) {
      return splats.map((entry) => ({
        id: entry.anchor_id,
        label: entry.label,
        url: `/api/object-splat/${entry.anchor_id}`,
        kind: 'splat' as const,
      }))
    }
    return (meshes?.objects ?? []).map((entry: RoomMesh) => ({
      id: entry.anchor_id,
      label: entry.label,
      url: `/api/mesh/${entry.anchor_id}`,
      kind: 'mesh' as const,
    }))
  }, [objectSplats, meshes])

  const focusTarget = useMemo(() => {
    if (!selectedObject) {
      return null
    }
    return {
      centre: selectedObject.centre,
      radius: Math.max(0.6, Math.max(...selectedObject.extents) / 2),
    }
  }, [selectedObject])

  const startMission = () => {
    if (!routeReady) {
      return
    }
    setSelectedId(null)
    setFollow(true)
    setBrowserOpen(false)
    setArrivalDismissed(false)
    setTripToken((value) => value + 1)
  }

  const placeObstacle = (point: [number, number]) => {
    const blocker: number[] = [
      Math.round((point[0] - 0.18) * 100) / 100,
      Math.round((point[1] - 0.18) * 100) / 100,
      Math.round((point[0] + 0.18) * 100) / 100,
      Math.round((point[1] + 0.18) * 100) / 100,
    ]
    const next = [...obstacles, point]
    setObstacles(next)
    const blockers = next.map((item) => [
      item[0] - 0.18,
      item[1] - 0.18,
      item[0] + 0.18,
      item[1] + 0.18,
    ])
    blockers.push(blocker)
    const start = robotPositionRef.current ?? initialStartRef.current
    fetchReroute(blockers, start, clearanceRadius)
      .then((result) => {
        setRoute(result)
        if (!result.reachable) {
          setRerouteNote('No alternative path from the robot position')
          return
        }
        setRerouteNote(`Rerouted live · ${(result.distance_m ?? 0).toFixed(1)} m`)
        if (driving) {
          setTripToken((value) => value + 1)
        }
      })
      .catch(() => setRerouteNote('Reroute failed'))
  }

  const clearObstacles = () => {
    setObstacles([])
    setObstacleMode(false)
    replanForRobot(clearanceRadius, 'Obstacles cleared, route restored')
  }

  const sceneName = useMemo(() => {
    const capture = data?.source.capture ?? ''
    if (capture) {
      return capture.replace(/\.ply$/i, '').replace(/^\(\d+\)\s*/, '').trim()
    }
    return 'Industrial scene'
  }, [data])

  const showMission = trip.mode === 'idle' || (trip.mode === 'arrived' && arrivalDismissed)
  const showArrival = arrived && !arrivalDismissed

  return (
    <div className="relative h-screen w-full overflow-hidden bg-slate-950 text-slate-100">
      <div className="absolute inset-0">
        {data ? (
          <SplatRoom
            objects={displayObjects}
            frameObjects={data.objects}
            selectedLabel={
              selectedObject
                ? `${selectedObject.label ?? selectedObject.class}${selectedMapping?.tag ? ` · ${selectedMapping.tag}` : ''}`
                : ''
            }
            frameKey={`${data.source.scene}:${data.source.points}`}
            subtle
            frameOpacity={devMode && showRawDetections ? 0.45 : 0.22}
            upAxis={data.source.up_axis}
            floorHeight={data.floor.height}
            resetToken={resetToken}
            selectedId={selectedId}
            mappedIds={mappedIds}
            targetId={displayTargetId}
            targetPoint={targetPoint}
            cameraPose={null}
            maxSplats={data.source.points + 20_000}
            splatUrl={splatAssetUrl(data.source.points)}
            filterUrl={view === 'photo' || view === 'objects' ? null : filterAssetUrl(view)}
            contourUrl={view === 'edges' || view === 'semantics' ? '/api/filter/contours' : null}
            objectOverlayUrl={view === 'semantics' ? '/api/filter/anchors_overlay' : null}
            showLabels={devMode || view === 'objects'}
            framesVisible={displayObjects.length > 0}
            objectMode={view === 'objects'}
            hideSplat={view === 'objects'}
            explode={explode}
            objectAssets={objectAssets}
            obstacleMode={obstacleMode}
            obstacles={obstacles}
            robotPositionRef={robotPositionRef}
            onPlaceObstacle={placeObstacle}
            showOccupancy={showOccupancy}
            showRoute={driving}
            focusTarget={focusTarget}
            focusToken={focusToken}
            robotProfile={robot.id}
            route={route}
            tripToken={tripToken}
            follow={follow}
            focus={follow || driving}
            onNearby={setNearby}
            onTrip={setTrip}
            onSelect={(id) => {
              setSelectedId(id)
              setBrowserOpen(false)
              setLayersOpen(false)
              setSettingsOpen(false)
            }}
          />
        ) : (
          <div className="flex h-full items-center justify-center text-sm font-semibold text-slate-400">
            {error ?? (loading ? 'Loading the captured scene' : 'No scene loaded')}
          </div>
        )}
      </div>

      {error ? (
        <div className="absolute inset-x-0 top-16 z-30 mx-auto max-w-md rounded-lg border border-red-500/40 bg-slate-950/90 px-4 py-3 text-sm text-slate-200">
          {error}
        </div>
      ) : null}

      {/* Header */}
      <header className="pointer-events-none absolute inset-x-0 top-0 z-30 flex items-start justify-between gap-3 px-4 py-3">
        <div className="pointer-events-auto flex items-center gap-3 rounded-lg border border-white/5 bg-slate-950/55 px-3 py-2 backdrop-blur">
          <span className="grid h-5 w-5 place-items-center rounded bg-cyan-400 text-[10px] font-black text-slate-950">P</span>
          <span className="text-sm font-black tracking-tight text-white">PlantPilot</span>
          <span className="hidden h-4 w-px bg-slate-700 sm:block" />
          <span className="hidden text-xs font-semibold text-slate-300 sm:block">{sceneName}</span>
          <span className="flex items-center gap-1.5 rounded-full border border-emerald-400/30 bg-emerald-400/10 px-2 py-0.5 text-[10px] font-black uppercase tracking-wide text-emerald-300">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
            Live
          </span>
        </div>
        <div className="pointer-events-auto flex items-center gap-2">
          <button
            type="button"
            onClick={() => {
              setBrowserOpen((value) => !value)
              setLayersOpen(false)
              setSettingsOpen(false)
            }}
            className="rounded-lg border border-white/5 bg-slate-950/55 px-3 py-2 text-xs font-bold text-slate-200 backdrop-blur hover:border-slate-500"
          >
            Equipment <span className="text-cyan-300">{reviewed.length}</span>
          </button>
          <div className="relative">
            <button
              type="button"
              onClick={() => {
                setLayersOpen((value) => !value)
                setBrowserOpen(false)
                setSettingsOpen(false)
              }}
              className="rounded-lg border border-white/5 bg-slate-950/55 px-3 py-2 text-xs font-bold text-slate-200 backdrop-blur hover:border-slate-500"
            >
              Layers
            </button>
            {layersOpen ? (
              <div className="absolute right-0 mt-2 w-60 rounded-xl border border-slate-700 bg-slate-950/95 p-2 shadow-2xl backdrop-blur">
                <p className="px-2 pb-1 pt-1 text-[10px] font-black uppercase tracking-[0.14em] text-slate-500">Visualisation</p>
                {VIEW_OPTIONS.filter((option) => {
                  if (option.id === 'photo') {
                    return true
                  }
                  if (option.id === 'objects') {
                    return objectAssets.length > 0
                  }
                  return (filters?.filters.applied ?? []).includes(option.id)
                }).map((option) => (
                  <button
                    key={option.id}
                    type="button"
                    onClick={() => {
                      setView(option.id)
                      setLayersOpen(false)
                    }}
                    className={`flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-xs font-semibold ${
                      view === option.id ? 'bg-cyan-500/15 text-cyan-200' : 'text-slate-300 hover:bg-slate-800'
                    }`}
                  >
                    {option.label}
                    {view === option.id ? <span className="text-[10px]">active</span> : null}
                  </button>
                ))}
                <div className="mt-1 border-t border-slate-800 pt-1">
                  <label className="flex cursor-pointer items-center justify-between rounded-md px-2 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-800">
                    Equipment outlines
                    <input
                      type="checkbox"
                      checked={showOutlines}
                      onChange={(event) => setShowOutlines(event.target.checked)}
                      className="accent-cyan-400"
                    />
                  </label>
                  <label className="flex cursor-pointer items-center justify-between rounded-md px-2 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-800">
                    Occupancy
                    <input
                      type="checkbox"
                      checked={showOccupancy}
                      onChange={(event) => setShowOccupancy(event.target.checked)}
                      className="accent-cyan-400"
                    />
                  </label>
                  <button
                    type="button"
                    onClick={() => {
                      setDevMode(true)
                      setLayersOpen(false)
                    }}
                    className="mt-1 flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-xs font-semibold text-amber-300 hover:bg-slate-800"
                  >
                    Developer mode
                    <span className="text-[10px] uppercase tracking-wide">advanced</span>
                  </button>
                </div>
              </div>
            ) : null}
          </div>
          <div className="relative">
            <button
              type="button"
              onClick={() => {
                setSettingsOpen((value) => !value)
                setLayersOpen(false)
                setBrowserOpen(false)
              }}
              aria-label="Settings"
              className="rounded-lg border border-white/5 bg-slate-950/55 px-3 py-2 text-xs font-bold text-slate-200 backdrop-blur hover:border-slate-500"
            >
              Settings
            </button>
            {settingsOpen ? (
              <div className="absolute right-0 mt-2 w-56 rounded-xl border border-slate-700 bg-slate-950/95 p-2 shadow-2xl backdrop-blur">
                <button
                  type="button"
                  onClick={() => {
                    setResetToken((value) => value + 1)
                    setFollow(false)
                    setSettingsOpen(false)
                  }}
                  className="w-full rounded-md px-2 py-1.5 text-left text-xs font-semibold text-slate-300 hover:bg-slate-800"
                >
                  Reset view
                </button>
                <label className="flex cursor-pointer items-center justify-between rounded-md px-2 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-800">
                  Developer mode
                  <input
                    type="checkbox"
                    checked={devMode}
                    onChange={(event) => setDevMode(event.target.checked)}
                    className="accent-cyan-400"
                  />
                </label>
                <button
                  type="button"
                  onClick={() => {
                    setSettingsOpen(false)
                    onLeave()
                  }}
                  className="w-full rounded-md px-2 py-1.5 text-left text-xs font-semibold text-slate-400 hover:bg-slate-800"
                >
                  Back to scene lab
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </header>

      {/* Equipment browser */}
      {browserOpen ? (
        <section className="absolute left-4 top-20 z-30 flex max-h-[62vh] w-80 max-w-[calc(100vw-2rem)] flex-col rounded-xl border border-slate-700 bg-slate-950/95 shadow-2xl backdrop-blur">
          <div className="flex items-center justify-between px-3 pt-3">
            <p className="text-[10px] font-black uppercase tracking-[0.14em] text-slate-500">Equipment</p>
            <button type="button" onClick={() => setBrowserOpen(false)} className="text-xs font-bold text-slate-400 hover:text-white">
              Close
            </button>
          </div>
          <div className="px-3 pt-2">
            <input
              value={browserQuery}
              onChange={(event) => setBrowserQuery(event.target.value)}
              placeholder="Search equipment"
              className="w-full rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-xs font-semibold text-slate-100 placeholder:text-slate-500 focus:border-cyan-400 focus:outline-none"
            />
            <div className="mt-2 flex gap-1">
              {(['all', 'attention', 'reviewed'] as const).map((filter) => (
                <button
                  key={filter}
                  type="button"
                  onClick={() => setBrowserFilter(filter)}
                  className={`rounded px-2 py-1 text-[10px] font-black uppercase tracking-wide ${
                    browserFilter === filter ? 'bg-cyan-500/20 text-cyan-200' : 'text-slate-400 hover:bg-slate-800'
                  }`}
                >
                  {filter}
                </button>
              ))}
            </div>
          </div>
          <div className="mt-2 overflow-y-auto px-2 pb-2">
            {filteredEquipment.map(({ record, mapping }) => (
              <button
                key={record.id}
                type="button"
                onClick={() => {
                  setSelectedId(record.id)
                  setBrowserOpen(false)
                  setFocusToken((value) => value + 1)
                }}
                className={`mb-1 flex w-full items-center justify-between gap-2 rounded-lg px-2 py-2 text-left ${
                  selectedId === record.id ? 'bg-cyan-500/10 ring-1 ring-cyan-400/40' : 'hover:bg-slate-800/80'
                }`}
              >
                <span className="min-w-0">
                  <span className="block truncate text-xs font-bold text-slate-100">
                    {mapping?.tag ? `${mapping.tag} · ` : ''}
                    {humanize(mapping?.class) || record.label || record.class}
                  </span>
                  <span className="block truncate text-[10px] font-semibold text-slate-500">
                    {mapping ? severityText(mapping) : 'No mapped record'}
                  </span>
                </span>
                <span
                  className="h-2 w-2 shrink-0 rounded-full"
                  style={{ backgroundColor: mapping ? STATE_COLOURS[mapping.state] : '#64748b' }}
                />
              </button>
            ))}
            {filteredEquipment.length === 0 ? (
              <p className="px-2 py-4 text-xs font-semibold text-slate-500">Nothing matches that search.</p>
            ) : null}
          </div>
        </section>
      ) : null}

      {/* Equipment detail card */}
      {selectedObject && !devMode ? (
        <aside className="absolute right-4 top-20 z-30 w-80 max-w-[calc(100vw-2rem)] rounded-xl border border-slate-700 bg-slate-950/95 p-4 shadow-2xl backdrop-blur">
          <div className="flex items-start justify-between gap-2">
            <div>
              <p className="text-[10px] font-black uppercase tracking-[0.14em] text-slate-500">
                {selectedMapping?.tag ? `Asset ${selectedMapping.tag}` : 'Reviewed equipment'}
              </p>
              <h2 className="mt-0.5 text-base font-black leading-tight text-white">
                {humanize(selectedMapping?.class) || selectedObject.label || humanize(selectedObject.class)}
              </h2>
            </div>
            <button type="button" onClick={() => setSelectedId(null)} className="text-xs font-bold text-slate-400 hover:text-white">
              Close
            </button>
          </div>
          <p className="mt-2 text-xs font-semibold" style={{ color: selectedMapping ? STATE_COLOURS[selectedMapping.state] : '#94a3b8' }}>
            {selectedMapping ? severityText(selectedMapping) : 'No condition data'}
          </p>
          <p className="mt-2 text-xs font-semibold leading-relaxed text-slate-300">
            {selectedObject.reviewed
              ? selectedObject.class_reason
              : selectedObject.method === 'mapping_target'
                ? selectedObject.class_reason
                : 'Unreviewed proposal from the capture. Treat the frame as a suggestion, not a confirmed object.'}
          </p>
          <dl className="mt-3 grid grid-cols-2 gap-2 text-xs">
            <div>
              <dt className="text-[10px] font-black uppercase tracking-wide text-slate-500">Size</dt>
              <dd className="font-bold text-slate-200">{selectedObject.extents.map((value) => value.toFixed(1)).join(' × ')} m</dd>
            </div>
            <div>
              <dt className="text-[10px] font-black uppercase tracking-wide text-slate-500">Status</dt>
              <dd className="font-bold text-slate-200">{selectedObject.reviewed ? 'Reviewed' : selectedObject.method === 'mapping_target' ? 'Pack target' : 'Proposal'}</dd>
            </div>
          </dl>
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              onClick={() => setFocusToken((value) => value + 1)}
              className="flex-1 rounded-lg border border-slate-600 px-3 py-2 text-xs font-black text-slate-200 hover:border-slate-400"
            >
              Focus
            </button>
            {selectedObject.id === targetAnchor?.id ? (
              <button
                type="button"
                onClick={startMission}
                disabled={!routeReady}
                className="flex-1 rounded-lg bg-cyan-500 px-3 py-2 text-xs font-black text-slate-950 hover:bg-cyan-400 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
              >
                Send robot
              </button>
            ) : null}
          </div>
        </aside>
      ) : null}

      {/* Mission card, progress bar and arrival */}
      {showMission && mission ? (
        <section className="absolute bottom-4 left-4 z-30 w-[22rem] max-w-[calc(100vw-2rem)] rounded-xl border border-slate-700/80 bg-slate-950/90 p-4 shadow-2xl backdrop-blur">
          <div className="flex items-center justify-between">
            <p className="text-[10px] font-black uppercase tracking-[0.16em] text-cyan-300">Mission</p>
            <span className="text-[10px] font-black uppercase tracking-wide text-slate-400">
              {driving ? 'Driving' : 'Ready'}
            </span>
          </div>
          <h2 className="mt-1 text-lg font-black leading-tight text-white">
            {mission.tag} <span className="text-slate-400">·</span> {mission.label}
          </h2>
          <p className="mt-1 text-xs font-semibold" style={{ color: targetMapping ? STATE_COLOURS[targetMapping.state] : '#cbd5e1' }}>
            {mission.condition}
          </p>
          <p className="mt-2 text-[11px] font-semibold text-slate-400">
            {routeReady
              ? `${(route?.distance_m ?? 0).toFixed(1)} m route · ${(route?.clearance_m ?? 0).toFixed(2)} m clearance`
              : routeMessage(route)}
          </p>
          <div className="mt-3">
            <div className="flex rounded-lg border border-slate-700 bg-slate-900/60 p-0.5">
              {ROBOTS.map((option) => (
                <button
                  key={option.id}
                  type="button"
                  onClick={() => changeRobot(option.id)}
                  className={`flex-1 rounded-md px-1.5 py-1 text-[10px] font-black uppercase tracking-wide ${
                    robotId === option.id && customRadius === null
                      ? 'bg-cyan-500/20 text-cyan-200'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <p className="mt-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
              Clearance radius {clearanceRadius.toFixed(2)} m
            </p>
          </div>
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              onClick={startMission}
              disabled={!routeReady}
              className="flex-1 rounded-lg bg-cyan-500 px-3 py-2.5 text-sm font-black text-slate-950 hover:bg-cyan-400 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
            >
              Send robot
            </button>
            {targetAnchor || mapped?.target_object_id ? (
              <button
                type="button"
                onClick={() => setSelectedId(targetAnchor?.id ?? mapped?.target_object_id ?? null)}
                className="rounded-lg border border-slate-600 px-3 py-2 text-xs font-black text-slate-200 hover:border-slate-400"
              >
                Inspect
              </button>
            ) : null}
          </div>
        </section>
      ) : null}

      {driving ? (
        <section className="absolute bottom-5 left-1/2 z-30 w-[24rem] max-w-[calc(100vw-2rem)] -translate-x-1/2 rounded-xl border border-slate-700/80 bg-slate-950/90 px-4 py-3 shadow-2xl backdrop-blur">
          <div className="flex items-center justify-between text-xs font-bold text-slate-200">
            <span>Driving to {mission?.tag ?? 'the target'}</span>
            <span className="text-cyan-300">{remaining.toFixed(1)} m</span>
          </div>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-800">
            <div className="h-full rounded-full bg-cyan-400 transition-[width] duration-300" style={{ width: `${Math.max(3, progress * 100)}%` }} />
          </div>
          {nearbyEquipment.length > 0 ? (
            <div className="mt-2 flex flex-wrap gap-1">
              {nearbyEquipment.map((entry) => (
                <span key={entry.key} className="rounded border px-1.5 py-0.5 text-[10px] font-bold" style={{ borderColor: STATE_COLOURS[entry.state], color: STATE_COLOURS[entry.state] }}>
                  {entry.name}
                </span>
              ))}
            </div>
          ) : null}
        </section>
      ) : null}

      {showArrival && mission ? (
        <section className="absolute bottom-4 left-4 z-30 w-[24rem] max-w-[calc(100vw-2rem)] rounded-xl border border-slate-700/80 bg-slate-950/95 p-4 shadow-2xl backdrop-blur">
          <p className="text-[10px] font-black uppercase tracking-[0.16em] text-emerald-300">Inspection complete</p>
          <h2 className="mt-1 text-lg font-black leading-tight text-white">
            {diagnosis?.issue?.code ?? mission.issue ?? 'Report'} <span className="text-slate-400">at</span> {mission.tag}
          </h2>
          <p className="mt-1 text-xs font-semibold text-slate-300">
            Health {diagnosis?.health_score ?? '—'} · {diagnosis?.issue?.summary ?? mission.condition}
          </p>
          {diagnosis?.next_safe_check ? (
            <p className="mt-2 rounded-md border border-slate-700 bg-slate-900/70 px-2 py-1.5 text-[11px] font-semibold leading-snug text-slate-300">
              Next check: {diagnosis.next_safe_check.action}
            </p>
          ) : null}
          <div className="mt-3 flex gap-2">
            {targetAnchor || mapped?.target_object_id ? (
              <button
                type="button"
                onClick={() => {
                  setSelectedId(targetAnchor?.id ?? mapped?.target_object_id ?? null)
                  setArrivalDismissed(true)
                }}
                className="flex-1 rounded-lg bg-cyan-500 px-3 py-2 text-xs font-black text-slate-950 hover:bg-cyan-400"
              >
                Open equipment
              </button>
            ) : null}
            <button
              type="button"
              onClick={() => {
                setArrivalDismissed(true)
                setFollow(false)
              }}
              className="rounded-lg border border-slate-600 px-3 py-2 text-xs font-black text-slate-200 hover:border-slate-400"
            >
              Dismiss
            </button>
          </div>
        </section>
      ) : null}

      {/* Camera controls */}
      {!devMode ? (
      <div className="absolute bottom-4 right-4 z-20 flex flex-col items-end gap-1">
        {view === 'objects' ? (
          <label className="pointer-events-auto mb-1 w-44 rounded-lg border border-slate-700 bg-slate-950/85 px-2 py-1.5 text-[10px] font-black uppercase tracking-wide text-slate-400 backdrop-blur">
            Explode {Math.round(explode * 100)} %
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
        <div className="pointer-events-auto flex flex-col overflow-hidden rounded-lg border border-slate-700 bg-slate-950/85 text-[11px] font-bold text-slate-300 shadow-xl backdrop-blur">
          <button type="button" onClick={() => setResetToken((value) => value + 1)} className="px-3 py-1.5 hover:bg-slate-800">
            Overview
          </button>
          {driving || arrived ? (
            <button type="button" onClick={() => setFollow((value) => !value)} className={`px-3 py-1.5 hover:bg-slate-800 ${follow ? 'text-cyan-300' : ''}`}>
              {follow ? 'Following' : 'Follow'}
            </button>
          ) : null}
          <button
            type="button"
            onClick={() => {
              setResetToken((value) => value + 1)
              setFollow(false)
            }}
            className="px-3 py-1.5 hover:bg-slate-800"
          >
            Reset
          </button>
        </div>
      </div>
      ) : null}

      {/* Developer drawer */}
      {devMode ? (
        <aside className="absolute bottom-4 right-4 top-20 z-40 w-[23rem] max-w-[calc(100vw-2rem)] overflow-y-auto rounded-xl border border-slate-700 bg-slate-950/97 p-3 shadow-2xl backdrop-blur lg:right-4">
          <div className="flex items-center justify-between">
            <p className="text-[10px] font-black uppercase tracking-[0.16em] text-amber-300">Developer mode</p>
            <button type="button" onClick={() => setDevMode(false)} className="text-xs font-bold text-slate-400 hover:text-white">
              Close
            </button>
          </div>

          <section className="mt-2 rounded-lg border border-slate-800 bg-slate-900/60 p-2">
            <p className="text-[10px] font-black uppercase tracking-wide text-slate-500">Scene</p>
            <dl className="mt-1 grid grid-cols-2 gap-x-2 gap-y-1 text-[11px] font-semibold">
              <dt className="text-slate-500">Gaussians</dt>
              <dd className="text-right text-slate-200">{data?.source.points.toLocaleString() ?? '—'}</dd>
              <dt className="text-slate-500">Raw objects</dt>
              <dd className="text-right text-slate-200">{data?.counts.objects ?? '—'}</dd>
              <dt className="text-slate-500">Reviewed</dt>
              <dd className="text-right text-slate-200">{reviewed.length}</dd>
              <dt className="text-slate-500">Route</dt>
              <dd className="text-right text-slate-200">{route?.distance_m?.toFixed(2) ?? '—'} m</dd>
              <dt className="text-slate-500">Clearance</dt>
              <dd className="text-right text-slate-200">{route?.clearance_m?.toFixed(2) ?? '—'} m</dd>
              <dt className="text-slate-500">Grid blocked</dt>
              <dd className="text-right text-slate-200">
                {typeof route?.grid_stats?.blocked_fraction === 'number'
                  ? `${(route.grid_stats.blocked_fraction * 100).toFixed(0)} %`
                  : '—'}
              </dd>
            </dl>
            <p className="mt-2 text-[10px] font-black uppercase tracking-wide text-slate-500">Robot clearance</p>
            <div className="mt-1 flex items-center gap-2">
              <input
                type="range"
                min={0.15}
                max={0.7}
                step={0.01}
                value={customRadius ?? robot.radius}
                onChange={(event) => setCustomRadius(Number(event.target.value))}
                className="flex-1 accent-amber-400"
              />
              <span className="w-12 text-right text-[10px] font-black text-slate-200">{(customRadius ?? robot.radius).toFixed(2)} m</span>
              <button
                type="button"
                onClick={() => changeRobot(robotId, customRadius ?? robot.radius)}
                className="rounded border border-amber-500/60 px-2 py-1 text-[10px] font-black uppercase tracking-wide text-amber-200"
              >
                Apply
              </button>
            </div>
            <label className="mt-2 flex items-center justify-between text-[11px] font-semibold text-slate-300">
              Raw detections (150 boxes)
              <input type="checkbox" checked={showRawDetections} onChange={(event) => setShowRawDetections(event.target.checked)} className="accent-amber-400" />
            </label>
            <label className="mt-1 flex items-center justify-between text-[11px] font-semibold text-slate-300">
              Occupancy grid
              <input type="checkbox" checked={showOccupancy} onChange={(event) => setShowOccupancy(event.target.checked)} className="accent-amber-400" />
            </label>
            <div className="mt-2 flex gap-1">
              <button
                type="button"
                onClick={() => setObstacleMode((value) => !value)}
                className={`flex-1 rounded border px-2 py-1 text-[10px] font-black uppercase tracking-wide ${
                  obstacleMode ? 'border-amber-400 bg-amber-500/20 text-amber-200' : 'border-slate-700 text-slate-300'
                }`}
              >
                {obstacleMode ? 'Click floor' : 'Place obstacle'}
              </button>
              {obstacles.length > 0 ? (
                <button type="button" onClick={clearObstacles} className="rounded border border-slate-700 px-2 py-1 text-[10px] font-black uppercase tracking-wide text-slate-300">
                  Clear
                </button>
              ) : null}
            </div>
            {rerouteNote ? <p className="mt-1 text-[10px] font-semibold text-amber-200">{rerouteNote}</p> : null}
          </section>

          <section className="mt-2 rounded-lg border border-slate-800 bg-slate-900/60 p-2">
            <p className="text-[10px] font-black uppercase tracking-wide text-slate-500">Proposal confidence</p>
            <p className="mt-1 text-[11px] font-semibold text-slate-400">
              {assets?.counts
                ? `${assets.counts.assets} assets · ${assets.counts.verified} verified · ${assets.counts.suppressed} suppressed`
                : 'No proposal artifact'}
            </p>
            <div className="mt-1 max-h-28 overflow-y-auto">
              {(assets?.assets ?? []).slice(0, 12).map((asset: RoomAsset) => (
                <div key={asset.id} className="flex items-center justify-between text-[10px] font-semibold text-slate-400">
                  <span className="truncate">{asset.label}</span>
                  <span className="ml-2 text-slate-200">{Math.round(asset.confidence * 100)} %</span>
                </div>
              ))}
            </div>
          </section>

          <section className="mt-2 rounded-lg border border-slate-800 bg-slate-900/60 p-2">
            <p className="text-[10px] font-black uppercase tracking-wide text-slate-500">Builder assets</p>
            <div className="mt-1 max-h-40 overflow-y-auto">
              {(mapped?.mappings ?? []).map((mapping) => (
                <div key={mapping.tag} className="flex items-center justify-between gap-2 text-[10px] font-semibold">
                  <span className="truncate text-slate-300">{mapping.tag}</span>
                  <span className="text-slate-500">{mapping.object_id ?? 'unresolved'}</span>
                  <span style={{ color: STATE_COLOURS[mapping.state] }}>{mapping.state}</span>
                  <span className="text-slate-400">{Math.round((mapping.match_score ?? mapping.confidence ?? 0) * 100)} %</span>
                </div>
              ))}
            </div>
          </section>

          {diagnosis ? (
            <section className="mt-2 rounded-lg border border-slate-800 bg-slate-900/60 p-2">
              <p className="text-[10px] font-black uppercase tracking-wide text-slate-500">Diagnosis evidence</p>
              <p className="mt-1 text-[11px] font-black text-slate-200">{diagnosis.issue?.code} · health {diagnosis.health_score}</p>
              {diagnosis.trend?.available ? (
                <svg viewBox="0 0 100 26" className="mt-1 h-7 w-full" role="img" aria-label="metric trend">
                  <polyline
                    fill="none"
                    stroke="#f59e0b"
                    strokeWidth="1.4"
                    points={(() => {
                      const values = diagnosis.trend.points.map((point) => point.value)
                      const min = Math.min(...values)
                      const max = Math.max(...values)
                      const span = max - min || 1
                      return values.map((value, index) => `${(index / Math.max(1, values.length - 1)) * 100},${24 - ((value - min) / span) * 22}`).join(' ')
                    })()}
                  />
                </svg>
              ) : null}
              {(diagnosis.findings ?? []).map((finding) => (
                <div key={finding.finding_id} className="mt-1">
                  <p className="text-[10px] font-semibold leading-snug text-slate-300">{finding.statement}</p>
                  {(finding.evidence ?? []).slice(0, 4).map((item) => (
                    <p key={item.ref} className="text-[9px] font-semibold text-slate-500">
                      <span className="text-amber-300">{item.ref}</span> {item.detail ?? item.label}
                    </p>
                  ))}
                </div>
              ))}
              {diagnosis.data_quality?.confidence_effect ? (
                <p className="mt-1 text-[9px] font-semibold leading-snug text-amber-200">{diagnosis.data_quality.confidence_effect}</p>
              ) : null}
              {(diagnosis.citations ?? []).slice(0, 2).map((citation) => (
                <p key={citation.doc_id} className="mt-1 text-[9px] font-semibold leading-snug text-slate-400">
                  {citation.doc_id}: {citation.excerpt}
                </p>
              ))}
            </section>
          ) : null}
        </aside>
      ) : null}
    </div>
  )
}
