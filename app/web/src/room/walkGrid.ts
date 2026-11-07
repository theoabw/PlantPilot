export type WalkGrid = {
  rows: number
  cols: number
  bits: Uint8Array
}

/** Four-connected distance to the nearest free cell, for escaping blocked starts. */
export function escapeDistances(grid: WalkGrid): Int32Array {
  const size = grid.rows * grid.cols
  const distances = new Int32Array(size).fill(-1)
  const queue = new Int32Array(size)
  let head = 0
  let tail = 0
  for (let index = 0; index < size; index += 1) {
    if ((grid.bits[index >> 3] & (0x80 >> (index & 7))) === 0) {
      distances[index] = 0
      queue[tail++] = index
    }
  }
  while (head < tail) {
    const index = queue[head++]
    const row = Math.floor(index / grid.cols)
    const col = index % grid.cols
    for (const [dr, dc] of [[-1, 0], [1, 0], [0, -1], [0, 1]]) {
      const r = row + dr
      const c = col + dc
      if (r < 0 || r >= grid.rows || c < 0 || c >= grid.cols) continue
      const next = r * grid.cols + c
      if (distances[next] !== -1) continue
      distances[next] = distances[index] + 1
      queue[tail++] = next
    }
  }
  return distances
}

export function canEscapeCell(from: number, to: number, distances: Int32Array): boolean {
  if (from < 0 || to < 0 || from >= distances.length || to >= distances.length) return false
  if (distances[from] < 0 || distances[to] < 0) return false
  return from === to || distances[to] < distances[from]
}
