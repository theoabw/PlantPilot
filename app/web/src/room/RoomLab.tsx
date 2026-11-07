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
  upVector,
} from './api'
import type {
  Diagnosis,
  MappedAsset,
  ReasoningDifferential,
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
  RoomCamera,
} from './api'
import SplatRoom, { type TripState } from './SplatRoom'
import { destinationTarget, prefersCrouched, routeStatusText, shouldTryCrouched, toggleManualCrouch, transitionDestinationPlan, type DestinationPlanState } from './routeMotion'
import CharacterSelector, { type CharacterOption } from '../components/CharacterSelector'

type DestinationDetails = {
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

/** World-vertical extent of an oriented box, for a capture with any up axis. */
function boxHeight(
  axes: [number, number, number][],
  extents: number[],
  upAxis: string | undefined,
): number {
  const up = upVector(upAxis)
  return axes.reduce(
    (total, axis, index) =>
      total + Math.abs(axis[0] * up[0] + axis[1] * up[1] + axis[2] * up[2]) * extents[index],
    0,
  )
}

const CONDITION_TEXT: Record<string, string> = {
  healthy: 'Healthy',
  watch: 'Watch',
  degraded: 'Degraded',
  attention_required: 'Needs attention',
}

// The verdict badge reuses the treatment already on this screen: emerald for
// something the evidence supports, slate for a weaker reading, amber for a pair
// the pack cannot separate.
const VERDICT_CLASSES: Record<ReasoningDifferential['verdict'], string> = {
  supported: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-300',
  'less likely': 'border-slate-600 bg-slate-800/70 text-slate-300',
  'cannot separate': 'border-amber-400/60 bg-amber-500/20 text-amber-200',
}

const ROBOTS: CharacterOption[] = [
  { id: 'humanoid', label: 'Humanoid', radius: 0.18, height: 1.35, crouchHeight: 0.95 },
  { id: 'amr', label: 'Compact AMR', radius: 0.2, height: 0.55 },
  { id: 'cargo', label: 'Cargo AMR', radius: 0.45, height: 0.9 },
]

const routeMessage = (route: RoomRoute | null): string => routeStatusText(route)

const severityText = (mapping: MappedAsset | null): string => {
  if (!mapping) {
    return 'Condition unknown'
  }
  const state = CONDITION_TEXT[mapping.state] ?? STATE_LABEL[mapping.state] ?? mapping.state
  return `${state} · ${humanize(mapping.issue_code)}`
}

export default function RoomLab() {
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
  const [cameraMove, setCameraMove] = useState(false)
  const [manualControl, setManualControl] = useState(false)
  const [manualCrouch, setManualCrouch] = useState(false)
  const [firstPerson, setFirstPerson] = useState(false)
  const [tripToken, setTripToken] = useState(0)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [view, setView] = useState('photo')
  const [topDown, setTopDown] = useState(false)
  const topDownRef = useRef(topDown)
  topDownRef.current = topDown
  const [topDownToken, setTopDownToken] = useState(0)
  const [cutHeight, setCutHeight] = useState(1.5)
  const [showOutlines, setShowOutlines] = useState(true)
  const [boxedSplatsOnly, setBoxedSplatsOnly] = useState(false)
  const [showMappedFrames, setShowMappedFrames] = useState(false)
  const [showOccupancy, setShowOccupancy] = useState(false)
  // The depth pass redraws half the splats each frame, the price of hiding the
  // robot and route behind the room. ?occlusion=off starts without it.
  const [occlusion, setOcclusion] = useState(() => new URLSearchParams(window.location.search).get('occlusion') !== 'off')
  const [devMode, setDevMode] = useState(false)
  const [showRawDetections, setShowRawDetections] = useState(false)
  const [layersOpen, setLayersOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [characterOpen, setCharacterOpen] = useState(false)
  const [browserOpen, setBrowserOpen] = useState(false)
  const [browserQuery, setBrowserQuery] = useState('')
  const [browserFilter, setBrowserFilter] = useState<'all' | 'attention' | 'reviewed'>('all')
  const [obstacleMode, setObstacleMode] = useState(false)
  const [obstacles, setObstacles] = useState<[number, number][]>([])
  const [rerouteNote, setRerouteNote] = useState<string | null>(null)
  const [explode, setExplode] = useState(0)
  const [robotId, setRobotId] = useState<CharacterOption['id']>('amr')
  const [planning, setPlanning] = useState(false)
  const [crouchSpans, setCrouchSpans] = useState<[number, number][]>([])
  const [destinationScene, setDestinationScene] = useState<[number, number, number] | null>(null)
  const [destinationLabel, setDestinationLabel] = useState<string | null>(null)
  const [destinationTag, setDestinationTag] = useState<string | null>(null)
  const [destinationCondition, setDestinationCondition] = useState<string | null>(null)
  const [destinationObjectId, setDestinationObjectId] = useState<string | null>(null)
  const [customRadius, setCustomRadius] = useState<number | null>(null)
  const [focusToken, setFocusToken] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [resetToken, setResetToken] = useState(0)
  const [characterResetToken, setCharacterResetToken] = useState(0)
  const [arrivalDismissed, setArrivalDismissed] = useState(false)
  const [robotDeployed, setRobotDeployed] = useState(false)
  const robotPositionRef = useRef<[number, number] | null>(null)
  const motionPausedRef = useRef(false)
  const planRequestRef = useRef(0)
  const resumeAfterPlanRef = useRef(false)
  const initialStartRef = useRef<[number, number] | null>(null)
  const initialRouteRef = useRef<RoomRoute | null>(null)
  const destinationPlanRef = useRef<DestinationPlanState>({ committed: { target: null }, pending: null })
  const initialPositionRef = useRef<[number, number, number] | null>(null)

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
          initialRouteRef.current = value
          if (value?.start) {
            const axes = value.grid?.horizontal_axes ?? [0, 2]
            const start = value.path[0] ?? value.start
            initialStartRef.current = [start[axes[0]], start[axes[1]]]
            initialPositionRef.current = [start[0], start[1], start[2]]
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
    if (mapped?.target_tag && destinationTag && destinationTag !== mapped.target_tag) {
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
  }, [trip.mode, diagnosis, destinationTag, mapped])

  // A replan reports an idle trip, and that must not take away a robot that has
  // already driven: it is standing in the room until someone resets it.
  useEffect(() => {
    if (trip.mode === 'moving') {
      setRobotDeployed(true)
    }
  }, [trip.mode])

  // A camera pose in the URL pins the view, for comparing two builds from the
  // same viewpoint. Coordinates are in the capture's own frame, like the object
  // centres, for example ?eye=0.2,-0.2,4.5&target=-1.9,0.8,2.3. A pinned view
  // also stops the follow camera from moving it once the robot starts driving.
  const pinnedPose = useMemo<RoomCamera | null>(() => {
    const read = (value: string | null): [number, number, number] | null => {
      if (!value) {
        return null
      }
      const parts = value.split(',').map(Number)
      if (parts.length !== 3 || parts.some((part) => !Number.isFinite(part))) {
        return null
      }
      return [parts[0], parts[1], parts[2]]
    }
    const params = new URLSearchParams(window.location.search)
    const eye = read(params.get('eye'))
    const target = read(params.get('target'))
    return eye && target ? { eye, target, up: [0, 1, 0] } : null
  }, [])

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
      observed_type: anchor.observed_type,
      inferred_function: anchor.inferred_function,
      category: anchor.category,
      classification_confidence: anchor.classification_confidence,
      evidence: anchor.evidence,
      sam3: anchor.sam3,
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

  const mappedFrames = useMemo(() => {
    if (!data || !mapped) {
      return []
    }
    const objectsById = new Map(data.objects.map((object) => [object.id, object]))
    const frames: {
      id: string
      tag: string
      state: string
      centre: [number, number, number]
      axes: [number, number, number][]
      extents: [number, number, number]
    }[] = []
    for (const record of mapped.mappings) {
      const object = record.object_id ? objectsById.get(record.object_id) : undefined
      if (!object) {
        continue
      }
      frames.push({
        id: object.id,
        tag: record.tag,
        state: record.state,
        centre: object.centre,
        axes: object.axes,
        extents: object.extents,
      })
    }
    return frames
  }, [data, mapped])

  const targetAnchor = useMemo(() => {
    if (!destinationObjectId) {
      return null
    }
    for (const anchor of anchors?.anchors ?? []) {
      if (anchor.id === destinationObjectId || anchor.source_object_ids.includes(destinationObjectId)) {
        return anchorById.get(anchor.id) ?? null
      }
    }
    return null
  }, [destinationObjectId, anchors, anchorById])

  const targetPoint: [number, number, number] | null = useMemo(() => {
    if (!destinationObjectId || targetAnchor) {
      return null
    }
    const object = data?.objects.find((candidate) => candidate.id === destinationObjectId)
    return object ? object.centre : null
  }, [destinationObjectId, targetAnchor, data])

  const targetMapping = useMemo(() => {
    if (!mapped) {
      return null
    }
    return mapped.mappings.find((record) => record.tag === mapped.target_tag) ?? null
  }, [mapped])

  const destinationDetails: DestinationDetails | null = useMemo(() => {
    const tag = destinationTag
    if (!tag) {
      return null
    }
    const isMappedTarget = destinationTag === mapped?.target_tag
    return {
      tag,
      label:
        destinationLabel ??
        targetAnchor?.label ??
        (humanize(targetMapping?.class) || 'equipment'),
      condition:
        destinationCondition ??
        (isMappedTarget && targetMapping ? severityText(targetMapping) : 'Selected equipment'),
      issue: isMappedTarget ? targetMapping?.issue_code : undefined,
    }
  }, [destinationTag, destinationLabel, destinationCondition, mapped, targetAnchor, targetMapping])

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

  // What the robot turns to face when it arrives at the explicitly selected object.
  const arrivalCentre = useMemo(() => {
    const id = destinationObjectId ?? targetAnchor?.id ?? null
    if (!id) {
      return null
    }
    return anchorById.get(id)?.centre ?? data?.objects.find((object) => object.id === id)?.centre ?? null
  }, [destinationObjectId, targetAnchor, anchorById, data])

  const selectedObject = useMemo(() => {
    if (!selectedId) {
      return null
    }
    return selectedRow?.record ?? anchorById.get(selectedId) ?? data?.objects.find((object) => object.id === selectedId) ?? null
  }, [selectedId, selectedRow, anchorById, data])

  // The reviewed anchor carries the multi-view fusion evidence. The card shows
  // it so a reader can see the box was measured from many views, not proposed.
  const selectedAnchor = useMemo(() => {
    if (!selectedId) {
      return null
    }
    return anchors?.anchors.find((anchor) => anchor.id === selectedId) ?? null
  }, [selectedId, anchors])

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

  const planRoute = (
    blockers: number[][],
    radius: number,
    profile: CharacterOption,
    note?: string,
    options: {
      target?: [number, number] | null
      startAfter?: boolean
      label?: string
      tag?: string | null
      condition?: string | null
      objectId?: string | null
      start?: [number, number] | null
      resumeMoving?: boolean
    } = {},
  ) => {
    const { start: requestedStart, resumeMoving, ...intentOptions } = options
    const start = requestedStart ?? robotPositionRef.current ?? initialStartRef.current
    const target = intentOptions.target ?? destinationTarget(destinationPlanRef.current)
    if (!target) {
      return
    }
    setPlanning(true)
    setRerouteNote(null)
    // A replacement inherits the pending intent without changing the destination
    // of the route still in use. Cancellation discards only that pending intent.
    const planState = transitionDestinationPlan(destinationPlanRef.current, {
      type: 'begin',
      intent: { ...intentOptions, target },
    })
    destinationPlanRef.current = planState
    const intent = planState.pending!
    // The robot holds still while a replan is out, across both requests of a
    // crouch fallback, so the route it gets starts where it actually stands.
    // Only the latest request counts: an older answer is from an older position.
    const request = planRequestRef.current + 1
    planRequestRef.current = request
    if (driving && resumeMoving !== false) {
      motionPausedRef.current = true
      resumeAfterPlanRef.current = true
    }
    const planWithHeight = (height: number, standingHeightM: number | null = null) =>
      fetchReroute(blockers, start, radius, height, {
        target,
        standingHeightM,
      })
    const finish = (result: RoomRoute, crouched: boolean) => {
      if (request !== planRequestRef.current) {
        return
      }
      const resume = resumeAfterPlanRef.current
      resumeAfterPlanRef.current = false
      motionPausedRef.current = false
      setPlanning(false)
      setRoute(result)
      const waypoint = result.target_waypoint
      let waypointXZ: [number, number] | null = null
      if (waypoint) {
        const axes = result.grid?.horizontal_axes ?? [0, 2]
        setDestinationScene([waypoint[0], waypoint[1], waypoint[2]])
        waypointXZ = [waypoint[axes[0]], waypoint[axes[1]]]
      }
      destinationPlanRef.current = transitionDestinationPlan(destinationPlanRef.current, {
        type: 'commit',
        intent,
        waypoint: waypointXZ,
      })
      const destination = destinationPlanRef.current.committed
      setCrouchSpans(crouched ? result.crouch_spans_m ?? [] : [])
      setDestinationLabel(destination.label ?? null)
      setDestinationTag(destination.tag ?? null)
      setDestinationCondition(destination.condition ?? null)
      setDestinationObjectId(destination.objectId ?? null)
      if (!result.reachable) {
        setRerouteNote(routeMessage(result))
        return
      }
      setRerouteNote(
        note ??
          (crouched ? 'Crouches under low pipework on this route' : `Route replanned for ${radius.toFixed(2)} m clearance`),
      )
      if (intent.startAfter) {
        setSelectedId(null)
        setFollow(!topDownRef.current)
        setArrivalDismissed(false)
        setTripToken((value) => value + 1)
      } else if (resume) {
        setTripToken((value) => value + 1)
      }
    }
    planWithHeight(profile.height)
      .then((result) => {
        if (request !== planRequestRef.current) {
          return
        }
        if (!profile.crouchHeight || !shouldTryCrouched(result)) {
          finish(result, false)
          return
        }
        // A humanoid can duck, so a refused route or a stop short of the machine
        // gets a crouched plan too. The planner says which stretches actually
        // need crouching, so the model walks upright everywhere else.
        planWithHeight(profile.crouchHeight, profile.height)
          .then((crouched) => {
            const useCrouched = prefersCrouched(result, crouched)
            finish(useCrouched ? crouched : result, useCrouched && (crouched.crouch_spans_m?.length ?? 0) > 0)
          })
          .catch(() => finish(result, false))
      })
      .catch(() => {
        if (request !== planRequestRef.current) {
          return
        }
        // The old route is still valid, so a paused robot carries on along it.
        resumeAfterPlanRef.current = false
        motionPausedRef.current = false
        destinationPlanRef.current = transitionDestinationPlan(destinationPlanRef.current, { type: 'cancel' })
        setPlanning(false)
        setRerouteNote('Route replan failed')
      })
  }

  // A plan still out when the user takes the robot back must not land afterwards:
  // its answer would count as the latest and drive the robot off again.
  const cancelPlan = () => {
    planRequestRef.current += 1
    resumeAfterPlanRef.current = false
    motionPausedRef.current = false
    destinationPlanRef.current = transitionDestinationPlan(destinationPlanRef.current, { type: 'cancel' })
    setPlanning(false)
  }

  const obstacleBlockers = () =>
    obstacles.map((item) => [
      item[0] - 0.18,
      item[1] - 0.18,
      item[0] + 0.18,
      item[1] + 0.18,
    ])

  const replanForRobot = (radius: number, note?: string) => {
    const target = destinationTarget(destinationPlanRef.current)
    if (!target) {
      return
    }
    planRoute(obstacleBlockers(), radius, robot, note, { target })
  }

  const changeRobot = (id: CharacterOption['id']) => {
    setCharacterOpen(false)
    if (id === robotId) return
    cancelPlan()
    setRobotDeployed(false)
    setRobotId(id)
    setManualCrouch(false)
    setCustomRadius(null)
    const option = ROBOTS.find((candidate) => candidate.id === id) ?? ROBOTS[1]
    robotPositionRef.current = initialStartRef.current
    setCharacterResetToken((value) => value + 1)
    setTrip({ mode: 'idle', travelled: 0, total: 0 })
    setCrouchSpans([])
    setManualControl(false)
    setCameraMove(false)
    setFirstPerson(false)
    setFollow(false)
    setArrivalDismissed(true)
    const target = destinationTarget(destinationPlanRef.current)
    if (target) {
      setRoute(null)
      planRoute(
        obstacleBlockers(),
        option.radius,
        option,
        `${option.radius.toFixed(2)} m clearance for the ${option.label.toLowerCase()}`,
        { start: initialStartRef.current, target, resumeMoving: false },
      )
    }
  }

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

  const sendToEquipment = () => {
    if (!selectedObject || planning) {
      return
    }
    setManualControl(false)
    setFirstPerson(false)
    setCameraMove(false)
    const axes = route?.grid?.horizontal_axes ?? [0, 2]
    const target: [number, number] = [
      selectedObject.centre[axes[0]],
      selectedObject.centre[axes[1]],
    ]
    const displayName =
      humanize(selectedMapping?.class) || selectedObject.label || humanize(selectedObject.class)
    planRoute(obstacleBlockers(), clearanceRadius, robot, undefined, {
      target,
      startAfter: true,
      label: displayName,
      tag: selectedMapping?.tag ?? displayName,
      condition: selectedMapping ? severityText(selectedMapping) : 'Selected equipment',
      objectId: selectedObject.id,
    })
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
    const target = destinationTarget(destinationPlanRef.current)
    if (target) {
      planRoute(blockers, clearanceRadius, robot, 'Rerouted live · obstacles on the path', { target })
    }
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

  const showArrival = arrived && !arrivalDismissed
  const mappedDestination = Boolean(destinationObjectId && destinationTag && destinationTag === mapped?.target_tag)

  return (
    <div className="relative h-screen w-full overflow-hidden bg-brand-navy text-slate-100">
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
            topDownToken={topDownToken}
            heightCutoff={topDown ? cutHeight : null}
            characterResetToken={characterResetToken}
            characterStart={initialPositionRef.current}
            selectedId={selectedId}
            mappedIds={mappedIds}
            targetId={displayTargetId}
            targetPoint={destinationScene ?? targetPoint}
            cameraPose={pinnedPose}
            maxSplats={data.source.points + 20_000}
            splatUrl={splatAssetUrl(data.source.points)}
            filterUrl={view === 'photo' || view === 'objects' ? null : filterAssetUrl(view)}
            contourUrl={view === 'edges' || view === 'semantics' ? '/api/filter/contours' : null}
            objectOverlayUrl={view === 'semantics' ? '/api/filter/anchors_overlay' : null}
            showLabels={devMode || view === 'objects'}
            framesVisible={displayObjects.length > 0}
            boxedSplatsOnly={boxedSplatsOnly}
            filterBoxes={reviewed}
            objectMode={view === 'objects'}
            hideSplat={view === 'objects'}
            occlusion={occlusion}
            explode={explode}
            objectAssets={objectAssets}
            mappedFrames={mappedFrames}
            showMappedFrames={showMappedFrames}
            obstacleMode={obstacleMode}
            obstacles={obstacles}
            robotPositionRef={robotPositionRef}
            motionPausedRef={motionPausedRef}
            arrivalCentre={arrivalCentre}
            onPlaceObstacle={placeObstacle}
            showOccupancy={showOccupancy}
            showRoute={driving}
            showRobot={initialStartRef.current !== null || manualControl || robotDeployed || trip.mode !== 'idle'}
            crouchSpans={crouchSpans}
            focusTarget={topDown ? null : focusTarget}
            focusToken={focusToken}
            robotProfile={robot.id}
            manualControl={manualControl}
            manualCrouch={manualCrouch}
            onToggleManualCrouch={() => {
              setManualCrouch((current) => toggleManualCrouch(current, manualControl, robot.id === 'humanoid'))
            }}
            firstPerson={firstPerson}
            route={route}
            tripToken={tripToken}
            cameraMove={cameraMove}
            follow={pinnedPose ? false : follow}
            focus={follow || driving}
            onNearby={setNearby}
            onTrip={setTrip}
            onSelect={(id) => {
              setSelectedId(id)
              setBrowserOpen(false)
              setLayersOpen(false)
              setSettingsOpen(false)
              setCharacterOpen(false)
            }}
          />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-sm font-semibold text-slate-400">
            <img src="/brand/plantpilot-stacked-on-dark.svg" alt="" className="h-40 w-auto" />
            {error ?? (loading ? 'Loading the captured scene' : 'No scene loaded')}
          </div>
        )}
      </div>

      {error ? (
        <div className="absolute inset-x-0 top-16 z-30 mx-auto max-w-md rounded-lg border border-red-500/40 bg-slate-950/90 px-4 py-3 text-sm text-slate-200">
          {error}
        </div>
      ) : null}
      {rerouteNote === 'Route replan failed' ? (
        <div role="alert" className="absolute inset-x-0 top-16 z-30 mx-auto max-w-md rounded-lg border border-red-500/40 bg-slate-950/90 px-4 py-3 text-sm text-slate-200">
          Route replan failed. Try sending the character again.
        </div>
      ) : null}

      {/* Header */}
      <header className="pointer-events-none absolute inset-x-0 top-0 z-40 flex flex-wrap items-start justify-between gap-3 px-4 py-3">
        <div className="pointer-events-auto flex items-center gap-3 rounded-lg border border-white/5 bg-brand-navy/85 py-1 pl-1 pr-3 backdrop-blur">
          <img src="/brand/plantpilot-horizontal-on-dark.svg" alt="PlantPilot" className="h-10 w-auto" />
          <span className="hidden h-4 w-px bg-slate-700 sm:block" />
          <span className="hidden text-xs font-semibold text-slate-300 sm:block">{sceneName}</span>
          <span className="flex items-center gap-1.5 rounded-full border border-emerald-400/30 bg-emerald-400/10 px-2 py-0.5 text-[10px] font-black uppercase tracking-wide text-emerald-300">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
            Live
          </span>
          <span className="rounded-full border border-amber-400/40 bg-amber-400/10 px-2 py-0.5 text-[10px] font-black uppercase tracking-wide text-amber-300">
            Synthetic scenario
          </span>
        </div>
        <div className="pointer-events-auto flex w-full flex-wrap items-center justify-end gap-1 sm:w-auto sm:gap-2">
          <button
            type="button"
            onClick={() => {
              setBrowserOpen((value) => !value)
              setLayersOpen(false)
              setSettingsOpen(false)
              setCharacterOpen(false)
            }}
            className="rounded-lg border border-white/5 bg-slate-950/55 px-2 py-2 text-[10px] font-bold text-slate-200 backdrop-blur hover:border-slate-500 sm:px-3 sm:text-xs"
          >
            Equipment <span className="text-brand-mint">{reviewed.length}</span>
          </button>
          <CharacterSelector
            options={ROBOTS}
            selected={robotId}
            open={characterOpen}
            ready={initialStartRef.current !== null}
            onToggle={() => {
              setCharacterOpen((value) => !value)
              setBrowserOpen(false)
              setLayersOpen(false)
              setSettingsOpen(false)
            }}
            onSelect={changeRobot}
          />
          <div className="relative">
            <button
              type="button"
              onClick={() => {
                setLayersOpen((value) => !value)
                setBrowserOpen(false)
                setSettingsOpen(false)
                setCharacterOpen(false)
              }}
              className="rounded-lg border border-white/5 bg-slate-950/55 px-2 py-2 text-[10px] font-bold text-slate-200 backdrop-blur hover:border-slate-500 sm:px-3 sm:text-xs"
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
                      setTopDown(false)
                      setBoxedSplatsOnly(false)
                      setLayersOpen(false)
                    }}
                    className={`flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-xs font-semibold ${
                      view === option.id ? 'bg-brand-mint/15 text-brand-mint' : 'text-slate-300 hover:bg-slate-800'
                    }`}
                  >
                    {option.label}
                    {view === option.id ? <span className="text-[10px]">active</span> : null}
                  </button>
                ))}
                <div className="mt-1 border-t border-slate-800 pt-1">
                  <button
                    type="button"
                    aria-pressed={boxedSplatsOnly}
                    disabled={reviewed.length === 0}
                    onClick={() => {
                      setView('photo')
                      setTopDown(false)
                      setBoxedSplatsOnly((value) => !value)
                    }}
                    className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-xs font-semibold text-slate-300 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Only splats in equipment boxes
                    {boxedSplatsOnly ? <span className="text-[10px] text-brand-mint">on</span> : null}
                  </button>
                  <p className="px-2 pb-1 text-[10px] text-slate-500">
                    {reviewed.length === 0
                      ? 'No reviewed equipment boxes available.'
                      : 'Keeps splat centres inside reviewed boxes. Outside is hidden, not deleted.'}
                  </p>
                  <label className="flex cursor-pointer items-center justify-between rounded-md px-2 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-800">
                    Equipment outlines
                    <input
                      type="checkbox"
                      checked={showOutlines}
                      onChange={(event) => setShowOutlines(event.target.checked)}
                      className="accent-brand-mint"
                    />
                  </label>
                  <label className="flex cursor-pointer items-center justify-between rounded-md px-2 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-800">
                    Synthetic pack frames ({mappedFrames.length})
                    <input
                      type="checkbox"
                      checked={showMappedFrames}
                      onChange={(event) => setShowMappedFrames(event.target.checked)}
                      className="accent-brand-mint"
                    />
                  </label>
                  <label className="flex cursor-pointer items-center justify-between rounded-md px-2 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-800">
                    Occupancy
                    <input
                      type="checkbox"
                      checked={showOccupancy}
                      onChange={(event) => setShowOccupancy(event.target.checked)}
                      className="accent-brand-mint"
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
                setCharacterOpen(false)
              }}
              aria-label="Settings"
              className="rounded-lg border border-white/5 bg-slate-950/55 px-2 py-2 text-[10px] font-bold text-slate-200 backdrop-blur hover:border-slate-500 sm:px-3 sm:text-xs"
            >
              Settings
            </button>
            {settingsOpen ? (
              <div className="absolute right-0 mt-2 w-56 rounded-xl border border-slate-700 bg-slate-950/95 p-2 shadow-2xl backdrop-blur">
                <button
                  type="button"
                  onClick={() => {
                    setTopDown(false)
                    setResetToken((value) => value + 1)
                    setFollow(false)
                    setSettingsOpen(false)
                  }}
                  className="w-full rounded-md px-2 py-1.5 text-left text-xs font-semibold text-slate-300 hover:bg-slate-800"
                >
                  Reset view
                </button>
                <label className="flex cursor-pointer items-center justify-between rounded-md px-2 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-800">
                  Realistic occlusion (slower)
                  <input
                    type="checkbox"
                    checked={occlusion}
                    onChange={(event) => setOcclusion(event.target.checked)}
                    className="accent-brand-mint"
                  />
                </label>
                <label className="flex cursor-pointer items-center justify-between rounded-md px-2 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-800">
                  Developer mode
                  <input
                    type="checkbox"
                    checked={devMode}
                    onChange={(event) => setDevMode(event.target.checked)}
                    className="accent-brand-mint"
                  />
                </label>
              </div>
            ) : null}
          </div>
        </div>
      </header>

      {/* Equipment browser */}
      {browserOpen ? (
        <section className="absolute left-4 top-32 z-30 flex max-h-[62vh] w-80 max-w-[calc(100vw-2rem)] flex-col rounded-xl border border-slate-700 bg-slate-950/95 shadow-2xl backdrop-blur sm:top-20">
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
              className="w-full rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-xs font-semibold text-slate-100 placeholder:text-slate-500 focus:border-brand-mint focus:outline-none"
            />
            <div className="mt-2 flex gap-1">
              {(['all', 'attention', 'reviewed'] as const).map((filter) => (
                <button
                  key={filter}
                  type="button"
                  onClick={() => setBrowserFilter(filter)}
                  className={`rounded px-2 py-1 text-[10px] font-black uppercase tracking-wide ${
                    browserFilter === filter ? 'bg-brand-mint/20 text-brand-mint' : 'text-slate-400 hover:bg-slate-800'
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
                  selectedId === record.id ? 'bg-brand-mint/10 ring-1 ring-brand-mint/40' : 'hover:bg-slate-800/80'
                }`}
              >
                <span className="min-w-0">
                  <span className="block truncate text-xs font-bold text-slate-100">
                    {record.label || humanize(record.class)}
                  </span>
                  <span className="block truncate text-[10px] font-semibold text-slate-500">
                    {mapping ? `${mapping.tag} · ${severityText(mapping)}` : 'No mapped record'}
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
          <div className="border-t border-slate-800 px-2 pb-2 pt-1">
            <p className="px-2 pb-1 text-[10px] font-black uppercase tracking-[0.14em] text-amber-300/80">
              Synthetic pack records · {mapped?.counts.mapped ?? 0}/{mapped?.counts.assets ?? 30} procedurally mapped
            </p>
            <p className="px-2 pb-1 text-[9px] font-semibold leading-snug text-slate-500">
              Supplied synthetic metadata. The placement is procedural and is not a verified identity or location for this room.
            </p>
            <div className="max-h-44 overflow-y-auto">
              {(mapped?.mappings ?? []).map((record) => (
                <button
                  key={record.asset_id}
                  type="button"
                  onClick={() => {
                    if (record.object_id) {
                      setSelectedId(record.object_id)
                      setBrowserOpen(false)
                      setFocusToken((value) => value + 1)
                    }
                  }}
                  className="mb-0.5 flex w-full items-center justify-between gap-2 rounded px-2 py-1 text-left hover:bg-slate-800/80"
                >
                  <span className="min-w-0">
                    <span className="block truncate text-[11px] font-bold text-slate-200">
                      {record.tag} · {humanize(record.class)}
                    </span>
                    <span className="block truncate text-[9px] font-semibold text-slate-500">
                      {record.status} · {record.method.replace(/_/g, ' ')}
                    </span>
                  </span>
                  <span className="flex shrink-0 items-center gap-1">
                    <span className="text-[9px] font-bold" style={{ color: STATE_COLOURS[record.state] }}>
                      {record.state.replace(/_/g, ' ')}
                    </span>
                    <span
                      className="h-1.5 w-1.5 rounded-full"
                      style={{ backgroundColor: STATE_COLOURS[record.state] }}
                    />
                  </span>
                </button>
              ))}
            </div>
          </div>
        </section>
      ) : null}

      {/* Equipment detail card */}
      {selectedObject && !devMode ? (
        <aside className="absolute right-4 top-32 z-30 w-80 max-w-[calc(100vw-2rem)] rounded-xl border border-slate-700 bg-slate-950/95 p-4 shadow-2xl backdrop-blur sm:top-20">
          <div className="flex items-start justify-between gap-2">
            <div>
              <p className="text-[10px] font-black uppercase tracking-[0.14em] text-slate-500">
                {selectedMapping?.tag ? `Asset ${selectedMapping.tag}` : 'Reviewed equipment'}
              </p>
              <h2 className="mt-0.5 text-base font-black leading-tight text-white">
                {selectedObject.label || humanize(selectedObject.class)}
              </h2>
              {selectedMapping?.tag ? (
                <p className="mt-0.5 text-[10px] font-semibold text-slate-500">
                  Synthetic pack record {selectedMapping.tag} · {humanize(selectedMapping.class)} (procedural, not verified)
                </p>
              ) : null}
            </div>
            <button type="button" onClick={() => setSelectedId(null)} className="text-xs font-bold text-slate-400 hover:text-white">
              Close
            </button>
          </div>
          <p className="mt-2 text-xs font-semibold" style={{ color: selectedMapping ? STATE_COLOURS[selectedMapping.state] : '#94a3b8' }}>
            {selectedMapping
              ? `Synthetic scenario condition: ${severityText(selectedMapping)}`
              : 'No synthetic scenario record'}
          </p>
          {selectedObject.reviewed && selectedObject.observed_type ? (
            <div className="mt-2 space-y-1">
              <p className="text-[11px] font-semibold leading-snug text-slate-300">
                <span className="text-slate-500">Observed:</span> {selectedObject.observed_type}
                {selectedObject.category ? (
                  <span className="ml-1 rounded bg-slate-800 px-1 py-0.5 text-[9px] font-black uppercase tracking-wide text-slate-400">
                    {selectedObject.category}
                  </span>
                ) : null}
              </p>
              {selectedObject.inferred_function ? (
                <p className="text-[11px] font-semibold leading-snug text-amber-200">
                  <span className="text-amber-400/70">Likely use:</span> {selectedObject.inferred_function}
                  {selectedObject.classification_confidence ? (
                    <span className="ml-1 text-[9px] font-black uppercase tracking-wide text-amber-400/70">
                      {selectedObject.classification_confidence} confidence
                    </span>
                  ) : null}
                </p>
              ) : null}
              {selectedObject.evidence ? (
                <p className="text-[10px] font-semibold leading-snug text-slate-500">{selectedObject.evidence}</p>
              ) : null}
              {selectedObject.sam3 ? (
                <p className="text-[10px] font-semibold leading-snug text-brand-mint/80">
                  SAM 3 check: {selectedObject.sam3.label} · score {selectedObject.sam3.score.toFixed(2)} ·{' '}
                  {selectedObject.sam3.views} views · centre agrees within{' '}
                  {selectedObject.sam3.centre_delta_m.toFixed(2)} m
                </p>
              ) : null}
              {selectedAnchor?.fused && (selectedAnchor.fused.views ?? 0) > 0 ? (
                <p className="text-[10px] font-semibold leading-snug text-brand-mint/80">
                  Fusion check:{' '}
                  {[
                    `${selectedAnchor.fused.views} views`,
                    selectedAnchor.fused.score != null
                      ? `score ${selectedAnchor.fused.score.toFixed(2)}`
                      : null,
                    `box ${boxHeight(selectedAnchor.axes, selectedAnchor.extents, data?.source.up_axis).toFixed(2)} m`,
                    selectedAnchor.fused.floor_gap_m != null
                      ? `${selectedAnchor.fused.floor_gap_m.toFixed(2)} m stand gap`
                      : null,
                    selectedAnchor.fused.visible_fraction != null
                      ? `${Math.round(selectedAnchor.fused.visible_fraction * 100)} percent visible`
                      : null,
                  ]
                    .filter((part): part is string => Boolean(part))
                    .join(', ')}
                </p>
              ) : null}
            </div>
          ) : (
            <p className="mt-2 text-xs font-semibold leading-relaxed text-slate-300">
              {selectedObject.reviewed
                ? selectedObject.class_reason
                : selectedObject.method === 'mapping_target'
                  ? selectedObject.class_reason
                  : 'Unreviewed proposal from the capture. Treat the frame as a suggestion, not a confirmed object.'}
            </p>
          )}
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
            <button
              type="button"
              onClick={sendToEquipment}
              disabled={planning}
              className="flex-1 rounded-lg bg-brand-mint px-3 py-2 text-xs font-black text-brand-navy hover:bg-brand-teal disabled:cursor-not-allowed disabled:opacity-50"
            >
              Send robot here
            </button>
          </div>
        </aside>
      ) : null}

      {driving ? (
        <section className="absolute bottom-5 left-1/2 z-30 w-[24rem] max-w-[calc(100vw-2rem)] -translate-x-1/2 rounded-xl border border-slate-700/80 bg-slate-950/90 px-4 py-3 shadow-2xl backdrop-blur">
          <div className="flex items-center justify-between text-xs font-bold text-slate-200">
            <span>Driving to {destinationTag ?? destinationLabel ?? 'the selected object'}</span>
            <span className="text-brand-mint">{remaining.toFixed(1)} m</span>
          </div>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-800">
            <div className="h-full rounded-full bg-brand-mint transition-[width] duration-300" style={{ width: `${Math.max(3, progress * 100)}%` }} />
          </div>
          {nearbyEquipment.length > 0 ? (
            <p className="mt-2 text-[9px] font-black uppercase tracking-wide text-amber-300/70">
              Synthetic pack status
            </p>
          ) : null}
          {nearbyEquipment.length > 0 ? (
            <div className="mt-1 flex flex-wrap gap-1">
              {nearbyEquipment.map((entry) => (
                <span key={entry.key} className="rounded border px-1.5 py-0.5 text-[10px] font-bold" style={{ borderColor: STATE_COLOURS[entry.state], color: STATE_COLOURS[entry.state] }}>
                  {entry.name}
                </span>
              ))}
            </div>
          ) : null}
        </section>
      ) : null}

      {showArrival && destinationDetails ? (
        <section className="absolute bottom-4 left-4 z-30 w-[24rem] max-w-[calc(100vw-2rem)] rounded-xl border border-slate-700/80 bg-slate-950/95 p-4 shadow-2xl backdrop-blur">
          <p className="text-[10px] font-black uppercase tracking-[0.16em] text-emerald-300">
            {mappedDestination ? 'Synthetic scenario diagnosis' : 'Arrived'}
          </p>
          <h2 className="mt-1 text-lg font-black leading-tight text-white">
            {mappedDestination
              ? `${diagnosis?.issue?.code ?? destinationDetails.issue ?? 'Report'} at ${destinationDetails.tag}`
              : (destinationLabel ?? destinationDetails.label)}
          </h2>
          {mappedDestination ? (
            <>
              <p className="mt-1 text-xs font-semibold text-slate-300">
                Health {diagnosis?.health_score ?? 'n/a'} · {diagnosis?.issue?.summary ?? destinationDetails.condition}
              </p>
              <p className="mt-1 text-[9px] font-semibold leading-snug text-amber-300/80">
                Computed from the supplied synthetic pack, not measured from this capture.
              </p>
              {diagnosis?.next_safe_check ? (
                <p className="mt-2 rounded-md border border-slate-700 bg-slate-900/70 px-2 py-1.5 text-[11px] font-semibold leading-snug text-slate-300">
                  Next check: {diagnosis.next_safe_check.action}
                </p>
              ) : null}
              {(() => {
                const refs = (diagnosis?.findings ?? [])
                  .flatMap((finding) => finding.evidence ?? [])
                  .map((item) => item.ref)
                  .filter((ref, index, all) => ref && all.indexOf(ref) === index)
                  .slice(0, 3)
                const citation = diagnosis?.citations?.[0]
                return (
                  <div className="mt-2 space-y-1">
                    {refs.length > 0 ? (
                      <p className="text-[10px] font-semibold leading-snug text-slate-400">
                        <span className="text-slate-500">Evidence:</span> {refs.join(' · ')}
                      </p>
                    ) : null}
                    {citation ? (
                      <p className="text-[10px] font-semibold leading-snug text-slate-500">
                        {citation.doc_id}: {citation.excerpt}
                      </p>
                    ) : null}
                  </div>
                )
              })()}
              {(() => {
                const reasoning = diagnosis?.reasoning
                if (!reasoning) {
                  return null
                }
                const claims = Array.isArray(reasoning.claims) ? reasoning.claims : []
                const differential = Array.isArray(reasoning.differential) ? reasoning.differential : []
                if (claims.length === 0 && differential.length === 0) {
                  return null
                }
                const guardrail = reasoning.guardrail
                return (
                  <div className="mt-2 border-t border-slate-800 pt-2">
                    {claims.length > 0 ? (
                      <>
                        <p className="text-[10px] font-black uppercase tracking-wide text-slate-500">Why</p>
                        <ul className="mt-1 space-y-1">
                          {claims.map((claim) => {
                            const refs = Array.isArray(claim.refs) ? claim.refs : []
                            return (
                              <li key={claim.claim_id}>
                                <p className="line-clamp-3 text-[11px] font-semibold leading-snug text-slate-300" title={claim.text}>
                                  {claim.text}
                                </p>
                                {refs.length > 0 ? (
                                  <div className="mt-0.5 flex flex-wrap gap-1">
                                    {refs.slice(0, 4).map((ref) => (
                                      <span
                                        key={ref}
                                        className="rounded border border-slate-700 bg-slate-950/70 px-1 py-0.5 font-mono text-[10px] leading-none text-slate-400"
                                      >
                                        {ref}
                                      </span>
                                    ))}
                                    {refs.length > 4 ? (
                                      <span className="rounded border border-slate-700 bg-slate-950/70 px-1 py-0.5 font-mono text-[10px] leading-none text-slate-500">
                                        +{refs.length - 4}
                                      </span>
                                    ) : null}
                                  </div>
                                ) : null}
                              </li>
                            )
                          })}
                        </ul>
                      </>
                    ) : null}
                    {differential.length > 0 ? (
                      <>
                        <p className="mt-2 text-[10px] font-black uppercase tracking-wide text-slate-500">Ruled out</p>
                        <ul className="mt-1 space-y-1">
                          {differential.map((entry) => (
                            <li key={entry.hypothesis}>
                              <p className="flex flex-wrap items-center gap-1 text-[11px] font-bold text-slate-200">
                                <span>{entry.hypothesis}</span>
                                <span
                                  className={`rounded border px-1 py-0.5 text-[10px] font-black uppercase tracking-wide ${VERDICT_CLASSES[entry.verdict]}`}
                                >
                                  {entry.verdict}
                                </span>
                              </p>
                              <p className="line-clamp-3 text-[10px] font-semibold leading-snug text-slate-400" title={entry.because}>
                                {entry.because}
                              </p>
                            </li>
                          ))}
                        </ul>
                      </>
                    ) : null}
                    {guardrail ? (
                      <p className="mt-2 text-[10px] font-semibold leading-snug text-slate-400">
                        {guardrail.claims} claims, {guardrail.cited} cited, {guardrail.unsupported} unsupported
                        <span className="text-slate-500"> · {reasoning.generated_by}</span>
                      </p>
                    ) : null}
                  </div>
                )
              })()}
            </>
          ) : (
            <p className="mt-1 text-xs font-semibold text-slate-300">
              Robot is waiting here. Choose another machine to send it onward.
            </p>
          )}
          <div className="mt-3 flex gap-2">
            {destinationObjectId ? (
              <button
                type="button"
                onClick={() => {
                  setSelectedId(destinationObjectId)
                  setArrivalDismissed(true)
                }}
                className="flex-1 rounded-lg bg-brand-mint px-3 py-2 text-xs font-black text-brand-navy hover:bg-brand-teal"
              >
                Open equipment
              </button>
            ) : null}
            <button
              type="button"
              onClick={() => {
                setArrivalDismissed(true)
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
              className="mt-1 w-full accent-brand-mint"
            />
          </label>
        ) : null}
        <div className="pointer-events-auto flex flex-col overflow-hidden rounded-lg border border-slate-700 bg-slate-950/85 text-[11px] font-bold text-slate-300 shadow-xl backdrop-blur">
          <button
            type="button"
            onClick={() => {
              setTopDown(false)
              setResetToken((value) => value + 1)
              setFollow(false)
              setCameraMove(false)
              setFirstPerson(false)
            }}
            className="px-3 py-1.5 hover:bg-slate-800"
          >
            Overview
          </button>
          <button
            type="button"
            disabled={!data?.objects.length || data.floor.height === null || !/^[+-][xyz]$/.test(data.source.up_axis)}
            title="Hide splats above the selected height"
            aria-pressed={topDown}
            onClick={() => {
              setTopDown(true)
              setTopDownToken((value) => value + 1)
              setView('photo')
              setBoxedSplatsOnly(false)
              setFollow(false)
              setManualControl(false)
              setCameraMove(false)
              setFirstPerson(false)
            }}
            className={`px-3 py-1.5 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50 ${topDown ? 'text-cyan-300' : ''}`}
          >
            Top down · height cut
          </button>
          {topDown ? (
            <label className="w-48 px-3 py-2 text-[10px] text-slate-400">
              Cut height: {cutHeight.toFixed(2)} scene units above floor
              <input
                type="range"
                min={0.1}
                max={4}
                step={0.05}
                value={cutHeight}
                onChange={(event) => setCutHeight(Number(event.target.value))}
                className="mt-1 w-full accent-cyan-400"
              />
              Hides splat centres above the cut, including equipment.
            </label>
          ) : null}
          <button
            type="button"
            aria-pressed={manualControl}
            disabled={!route}
            onClick={() => {
              cancelPlan()
              const next = !manualControl
              setManualCrouch(false)
              if (next) setTopDown(false)
              setManualControl(next)
              setCameraMove(false)
              setFirstPerson(false)
              setFollow(next)
              if (next) {
                setTrip({ mode: 'idle', travelled: 0, total: 0 })
                setArrivalDismissed(true)
              }
            }}
            className={`px-3 py-1.5 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50 ${manualControl ? 'text-brand-mint' : ''}`}
          >
            {manualControl ? 'Manual control · WASD / arrows' : 'Manual control'}
          </button>
          {manualControl ? (
            <div className="px-3 py-2 text-[10px] leading-relaxed text-slate-400">
              WASD or arrow keys to move · Shift toggles humanoid crouch · drag to look in first person
            </div>
          ) : null}
          {manualControl ? (
            <>
              <button
                type="button"
                aria-pressed={!firstPerson}
                onClick={() => {
                  setFirstPerson(false)
                  setFollow(true)
                }}
                className={`px-3 py-1.5 hover:bg-slate-800 ${!firstPerson ? 'text-brand-mint' : ''}`}
              >
                Third person
              </button>
              <button
                type="button"
                aria-pressed={firstPerson}
                onClick={() => {
                  setFollow(false)
                  setFirstPerson(true)
                }}
                className={`px-3 py-1.5 hover:bg-slate-800 ${firstPerson ? 'text-brand-mint' : ''}`}
              >
                First person
              </button>
            </>
          ) : null}
          {!manualControl && (driving || arrived) ? (
            <button
              type="button"
              onClick={() => {
                setCameraMove(false)
                if (!follow) setTopDown(false)
                setFollow((value) => !value)
              }}
              className={`px-3 py-1.5 hover:bg-slate-800 ${follow ? 'text-brand-mint' : ''}`}
            >
              {follow ? 'Following' : 'Follow'}
            </button>
          ) : null}
          {!manualControl ? (
            <button
              type="button"
              aria-pressed={cameraMove}
              onClick={() => {
                const next = !cameraMove
                setCameraMove(next)
                if (next) {
                  setFollow(false)
                }
              }}
              className={`px-3 py-1.5 hover:bg-slate-800 ${cameraMove ? 'text-brand-mint' : ''}`}
            >
              {cameraMove ? 'Move camera · WASD / arrows' : 'Move camera'}
            </button>
          ) : null}
          <button
            type="button"
            disabled={initialStartRef.current === null}
            onClick={() => {
              cancelPlan()
              setTopDown(false)
              setResetToken((value) => value + 1)
              setCharacterResetToken((value) => value + 1)
              setRobotDeployed(false)
              robotPositionRef.current = initialStartRef.current
              setTrip({ mode: 'idle', travelled: 0, total: 0 })
              setCrouchSpans([])
              setFollow(false)
              setCameraMove(false)
              setFirstPerson(false)
              setManualControl(false)
              setArrivalDismissed(true)
              destinationPlanRef.current = { committed: { target: null }, pending: null }
              setDestinationScene(null)
              setDestinationLabel(null)
              setDestinationTag(null)
              setDestinationCondition(null)
              setDestinationObjectId(null)
              setRoute(initialRouteRef.current)
            }}
            className="px-3 py-1.5 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
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
              <dd className="text-right text-slate-200">{data?.source.points.toLocaleString() ?? 'n/a'}</dd>
              <dt className="text-slate-500">Raw objects</dt>
              <dd className="text-right text-slate-200">{data?.counts.objects ?? 'n/a'}</dd>
              <dt className="text-slate-500">Reviewed</dt>
              <dd className="text-right text-slate-200">{reviewed.length}</dd>
              <dt className="text-slate-500">Route</dt>
              <dd className="text-right text-slate-200">{route?.distance_m?.toFixed(2) ?? 'n/a'} m</dd>
              <dt className="text-slate-500">Clearance</dt>
              <dd className="text-right text-slate-200">{route?.clearance_m?.toFixed(2) ?? 'n/a'} m</dd>
              <dt className="text-slate-500">Grid blocked</dt>
              <dd className="text-right text-slate-200">
                {typeof route?.grid_stats?.blocked_fraction === 'number'
                  ? `${(route.grid_stats.blocked_fraction * 100).toFixed(0)} %`
                  : 'n/a'}
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
                onClick={() => replanForRobot(customRadius ?? robot.radius)}
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
            <p className="text-[10px] font-black uppercase tracking-wide text-slate-500">Synthetic builder assets</p>
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
