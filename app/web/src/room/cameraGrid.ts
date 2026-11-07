export type CameraGridMask = {
  x0: number
  z0: number
  cell_m: number
  rows: number
  cols: number
  bits: Uint8Array
}

/** Distance from a scene point to the nearest blocked grid cell. */
export function cameraGridClearance(
  mask: CameraGridMask,
  x: number,
  z: number,
  limit: number,
): number {
  const cell = mask.cell_m
  if (cell <= 0 || !Number.isFinite(cell) || limit < 0) {
    return 0
  }
  const col = Math.floor((x - mask.x0) / cell)
  const row = Math.floor((z - mask.z0) / cell)
  const radius = Math.ceil(limit / cell) + 1
  let clearance = limit
  for (let dr = -radius; dr <= radius; dr += 1) {
    for (let dc = -radius; dc <= radius; dc += 1) {
      const cellCol = col + dc
      const cellRow = row + dr
      const index = cellRow * mask.cols + cellCol
      const blocked =
        cellCol < 0
        || cellRow < 0
        || cellCol >= mask.cols
        || cellRow >= mask.rows
        || (mask.bits[index >> 3] & (0x80 >> (index & 7))) !== 0
      if (!blocked) {
        continue
      }
      const left = mask.x0 + cellCol * cell
      const top = mask.z0 + cellRow * cell
      const dx = Math.max(left - x, 0, x - (left + cell))
      const dz = Math.max(top - z, 0, z - (top + cell))
      const distance = Math.hypot(dx, dz)
      if (distance < clearance) {
        clearance = distance
      }
    }
  }
  return clearance
}

/** Whether a camera point has more than the required clearance. */
export function cameraGridIsFree(
  mask: CameraGridMask,
  x: number,
  z: number,
  margin: number,
): boolean {
  return cameraGridClearance(mask, x, z, margin + mask.cell_m) > margin
}
