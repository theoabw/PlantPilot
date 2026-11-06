import type { AssetStatus } from './fixtures'
import type { LabProgress } from './LabWorld'

export const STATUS_LABEL: Record<AssetStatus, string> = {
  healthy: 'healthy',
  watch: 'watch',
  fault: 'fault',
}

export const STATUS_PILL: Record<AssetStatus, string> = {
  healthy: 'border-emerald-500/60 bg-emerald-500/10 text-emerald-200',
  watch: 'border-amber-500/60 bg-amber-500/10 text-amber-200',
  fault: 'border-red-500/60 bg-red-500/10 text-red-200',
}

export function modeTitle(progress: LabProgress): string {
  if (progress.mode === 'moving') {
    return `Moving to ${progress.targetId ?? 'target'}`
  }
  if (progress.mode === 'arrived') {
    return `Arrived at ${progress.targetId ?? 'target'}`
  }
  if (progress.mode === 'blocked') {
    return 'No clear route'
  }
  return 'Robot at dock'
}

export function modeDetail(progress: LabProgress): string {
  if (progress.mode === 'moving') {
    return `${progress.remaining.toFixed(1)} m left, ${progress.waypoint}/${progress.waypoints} waypoints`
  }
  if (progress.mode === 'arrived') {
    return `Route complete, ${progress.pathLength.toFixed(1)} m travelled`
  }
  if (progress.mode === 'blocked') {
    return 'The target is boxed in. Pick another asset or reset the robot.'
  }
  return 'Select a machine, then send the robot to inspect it.'
}

export function progressPercent(progress: LabProgress): number {
  if (progress.mode === 'arrived') {
    return 100
  }
  if (progress.pathLength <= 0) {
    return 0
  }
  return Math.max(0, Math.min(100, ((progress.pathLength - progress.remaining) / progress.pathLength) * 100))
}
