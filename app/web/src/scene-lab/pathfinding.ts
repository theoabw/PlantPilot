import { ROOM, type LabAsset } from './fixtures'

// Small A* grid used by the lab scene. The real pipeline will replace this with
// the occupancy grid produced from the splat, but the shape of the call is the
// same: build a grid from obstacles, find a path, smooth it.

export const CELL = 0.25
export const ROBOT_RADIUS = 0.42
const WALL_MARGIN = 0.45

export type Point2 = { x: number; z: number }

export type NavGrid = {
  cols: number
  rows: number
  cell: number
  minX: number
  minZ: number
  blocked: Uint8Array
}

export function buildNavGrid(assets: LabAsset[]): NavGrid {
  const cols = Math.ceil((ROOM.maxX - ROOM.minX) / CELL)
  const rows = Math.ceil((ROOM.maxZ - ROOM.minZ) / CELL)
  const blocked = new Uint8Array(cols * rows)

  for (let r = 0; r < rows; r += 1) {
    for (let c = 0; c < cols; c += 1) {
      const x = ROOM.minX + (c + 0.5) * CELL
      const z = ROOM.minZ + (r + 0.5) * CELL

      let isBlocked =
        x < ROOM.minX + WALL_MARGIN ||
        x > ROOM.maxX - WALL_MARGIN ||
        z < ROOM.minZ + WALL_MARGIN ||
        z > ROOM.maxZ - WALL_MARGIN

      if (!isBlocked) {
        for (const asset of assets) {
          const halfW = asset.width / 2 + ROBOT_RADIUS
          const halfD = asset.depth / 2 + ROBOT_RADIUS
          if (Math.abs(x - asset.x) <= halfW && Math.abs(z - asset.z) <= halfD) {
            isBlocked = true
            break
          }
        }
      }

      if (isBlocked) {
        blocked[r * cols + c] = 1
      }
    }
  }

  return { cols, rows, cell: CELL, minX: ROOM.minX, minZ: ROOM.minZ, blocked }
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value))
}

function cellAt(grid: NavGrid, point: Point2): { c: number; r: number } {
  return {
    c: clamp(Math.floor((point.x - grid.minX) / grid.cell), 0, grid.cols - 1),
    r: clamp(Math.floor((point.z - grid.minZ) / grid.cell), 0, grid.rows - 1),
  }
}

function cellCentre(grid: NavGrid, c: number, r: number): Point2 {
  return {
    x: grid.minX + (c + 0.5) * grid.cell,
    z: grid.minZ + (r + 0.5) * grid.cell,
  }
}

function isFree(grid: NavGrid, c: number, r: number): boolean {
  return c >= 0 && r >= 0 && c < grid.cols && r < grid.rows && grid.blocked[r * grid.cols + c] === 0
}

function isFreeWorld(grid: NavGrid, point: Point2): boolean {
  const { c, r } = cellAt(grid, point)
  return isFree(grid, c, r)
}

export function nearestFree(grid: NavGrid, point: Point2): Point2 {
  const start = cellAt(grid, point)
  if (isFree(grid, start.c, start.r)) {
    return cellCentre(grid, start.c, start.r)
  }

  const seen = new Uint8Array(grid.cols * grid.rows)
  const queue: Array<{ c: number; r: number }> = [start]
  seen[start.r * grid.cols + start.c] = 1
  const neighbours = [
    [1, 0],
    [-1, 0],
    [0, 1],
    [0, -1],
    [1, 1],
    [1, -1],
    [-1, 1],
    [-1, -1],
  ] as const

  for (let head = 0; head < queue.length; head += 1) {
    const current = queue[head]
    for (const [dc, dr] of neighbours) {
      const c = current.c + dc
      const r = current.r + dr
      if (!isFree(grid, c, r) || seen[r * grid.cols + c] === 1) {
        continue
      }
      // Do not squeeze diagonally between two blocked cells.
      if (dc !== 0 && dr !== 0 && (!isFree(grid, current.c + dc, current.r) || !isFree(grid, current.c, current.r + dr))) {
        continue
      }
      seen[r * grid.cols + c] = 1
      return cellCentre(grid, c, r)
    }
    // Expand one ring at a time; the first free cell found is close enough.
    for (const [dc, dr] of neighbours) {
      const c = current.c + dc
      const r = current.r + dr
      if (c < 0 || r < 0 || c >= grid.cols || r >= grid.rows || seen[r * grid.cols + c] === 1) {
        continue
      }
      seen[r * grid.cols + c] = 1
      queue.push({ c, r })
    }
  }

  return cellCentre(grid, start.c, start.r)
}

function lineClear(grid: NavGrid, a: Point2, b: Point2): boolean {
  const distance = Math.hypot(b.x - a.x, b.z - a.z)
  const steps = Math.max(1, Math.ceil(distance / (grid.cell * 0.5)))
  for (let i = 0; i <= steps; i += 1) {
    const t = i / steps
    if (!isFreeWorld(grid, { x: a.x + (b.x - a.x) * t, z: a.z + (b.z - a.z) * t })) {
      return false
    }
  }
  return true
}

// An approach point is outside the asset footprint, on the side facing the
// robot, with enough clearance to stop without clipping into the machine.
export function approachPoint(grid: NavGrid, asset: LabAsset, from: Point2): Point2 {
  const base = Math.max(asset.width, asset.depth) / 2 + ROBOT_RADIUS + 0.35
  let best: Point2 | null = null
  let bestScore = Number.POSITIVE_INFINITY

  for (let ring = 0; ring < 5 && !best; ring += 1) {
    const radius = base + ring * 0.35
    for (let i = 0; i < 48; i += 1) {
      const angle = (i / 48) * Math.PI * 2
      const point = {
        x: asset.x + Math.cos(angle) * radius,
        z: asset.z + Math.sin(angle) * radius,
      }
      if (!isFreeWorld(grid, point)) {
        continue
      }
      const score = Math.hypot(point.x - from.x, point.z - from.z)
      if (score < bestScore) {
        best = point
        bestScore = score
      }
    }
  }

  return best ?? nearestFree(grid, { x: asset.x + base, z: asset.z })
}

class MinHeap {
  private items: Array<{ index: number; score: number }> = []

  get size(): number {
    return this.items.length
  }

  push(index: number, score: number): void {
    const items = this.items
    items.push({ index, score })
    let i = items.length - 1
    while (i > 0) {
      const parent = (i - 1) >> 1
      if (items[parent].score <= items[i].score) {
        break
      }
      ;[items[parent], items[i]] = [items[i], items[parent]]
      i = parent
    }
  }

  pop(): number | null {
    const items = this.items
    if (items.length === 0) {
      return null
    }
    const top = items[0]
    const last = items.pop()
    if (items.length > 0 && last) {
      items[0] = last
      let i = 0
      for (;;) {
        const left = i * 2 + 1
        const right = left + 1
        let smallest = i
        if (left < items.length && items[left].score < items[smallest].score) {
          smallest = left
        }
        if (right < items.length && items[right].score < items[smallest].score) {
          smallest = right
        }
        if (smallest === i) {
          break
        }
        ;[items[smallest], items[i]] = [items[i], items[smallest]]
        i = smallest
      }
    }
    return top.index
  }
}

export function findPath(grid: NavGrid, startPoint: Point2, goalPoint: Point2): Point2[] | null {
  const start = cellAt(grid, startPoint)
  const goal = cellAt(grid, goalPoint)
  const startFree = isFree(grid, start.c, start.r)
  const goalFree = isFree(grid, goal.c, goal.r)

  const snappedStart = startFree ? start : cellAt(grid, nearestFree(grid, startPoint))
  const snappedGoal = goalFree ? goal : cellAt(grid, nearestFree(grid, goalPoint))

  const startIndex = snappedStart.r * grid.cols + snappedStart.c
  const goalIndex = snappedGoal.r * grid.cols + snappedGoal.c

  const gScore = new Float32Array(grid.cols * grid.rows).fill(Number.POSITIVE_INFINITY)
  const cameFrom = new Int32Array(grid.cols * grid.rows).fill(-1)
  const closed = new Uint8Array(grid.cols * grid.rows)
  const open = new MinHeap()

  gScore[startIndex] = 0
  open.push(startIndex, 0)

  const directions = [
    [1, 0, 1],
    [-1, 0, 1],
    [0, 1, 1],
    [0, -1, 1],
    [1, 1, Math.SQRT2],
    [1, -1, Math.SQRT2],
    [-1, 1, Math.SQRT2],
    [-1, -1, Math.SQRT2],
  ] as const

  while (open.size > 0) {
    const current = open.pop()
    if (current === null) {
      break
    }
    if (closed[current] === 1) {
      continue
    }
    if (current === goalIndex) {
      break
    }
    closed[current] = 1

    const c = current % grid.cols
    const r = Math.floor(current / grid.cols)

    for (const [dc, dr, cost] of directions) {
      const nc = c + dc
      const nr = r + dr
      if (!isFree(grid, nc, nr)) {
        continue
      }
      if (dc !== 0 && dr !== 0 && (!isFree(grid, c + dc, r) || !isFree(grid, c, r + dr))) {
        continue
      }
      const next = nr * grid.cols + nc
      if (closed[next] === 1) {
        continue
      }
      const tentative = gScore[current] + cost
      if (tentative >= gScore[next]) {
        continue
      }
      gScore[next] = tentative
      cameFrom[next] = current
      const dx = Math.abs(nc - snappedGoal.c)
      const dz = Math.abs(nr - snappedGoal.r)
      const heuristic = Math.max(dx, dz) + (Math.SQRT2 - 1) * Math.min(dx, dz)
      open.push(next, tentative + heuristic)
    }
  }

  if (startIndex !== goalIndex && cameFrom[goalIndex] === -1) {
    return null
  }

  const cells: number[] = []
  let cursor = goalIndex
  while (cursor !== -1) {
    cells.push(cursor)
    if (cursor === startIndex) {
      break
    }
    cursor = cameFrom[cursor]
  }
  cells.reverse()

  if (cells[0] !== startIndex) {
    return null
  }

  const raw = cells.map((index) =>
    cellCentre(grid, index % grid.cols, Math.floor(index / grid.cols)),
  )

  // Keep the exact endpoints when they are reachable, then remove redundant
  // corners with a line-of-sight pass.
  const withEndpoints: Point2[] = []
  if (lineClear(grid, startPoint, raw[0])) {
    withEndpoints.push(startPoint)
  }
  withEndpoints.push(...raw)
  const last = raw[raw.length - 1]
  if (lineClear(grid, last, goalPoint)) {
    withEndpoints.push(goalPoint)
  }

  const smoothed: Point2[] = [withEndpoints[0]]
  let i = 0
  while (i < withEndpoints.length - 1) {
    let j = withEndpoints.length - 1
    while (j > i + 1 && !lineClear(grid, withEndpoints[i], withEndpoints[j])) {
      j -= 1
    }
    smoothed.push(withEndpoints[j])
    i = j
  }

  return smoothed
}

export function pathLength(points: Point2[]): number {
  let total = 0
  for (let i = 1; i < points.length; i += 1) {
    total += Math.hypot(points[i].x - points[i - 1].x, points[i].z - points[i - 1].z)
  }
  return total
}
