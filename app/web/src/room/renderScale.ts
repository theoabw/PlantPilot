/**
 * How much of the full resolution to draw while the view is moving.
 *
 * The splat passes are fill bound, so frame time follows pixel count. A slow GPU
 * trades sharpness for motion while something moves, and the still image is
 * always drawn at full resolution.
 */
export const RENDER_SCALE_MIN = 0.45
const SLOW_FRAME_MS = 30
const FAST_FRAME_MS = 19
const STEP_DOWN = 0.75
const STEP_UP = 1.1

/** The next scale, given the average time per frame at the current one. */
export function nextRenderScale(scale: number, averageFrameMs: number): number {
  if (averageFrameMs > SLOW_FRAME_MS) {
    return Math.max(RENDER_SCALE_MIN, scale * STEP_DOWN)
  }
  if (averageFrameMs < FAST_FRAME_MS) {
    return Math.min(1, scale * STEP_UP)
  }
  return scale
}
