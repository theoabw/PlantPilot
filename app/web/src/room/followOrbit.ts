/** Keep a stationary robot's user-selected view instead of overriding its orbit. */
export function followCameraGoal<T>(
  desired: T,
  userSelected: boolean,
  robotMoving: boolean,
  avoidObstacles: (position: T) => T,
): T {
  return userSelected && !robotMoving ? desired : avoidObstacles(desired)
}

/** Distinguish orbit input and its damping from follow-camera updates. */
export class FollowOrbitInput {
  private active = false
  private settling = false
  private updating = false

  start(): void {
    this.active = true
    this.settling = true
  }

  end(): void {
    this.active = false
  }

  reset(): void {
    this.active = false
    this.settling = false
  }

  isInputChange(): boolean {
    return this.settling && !this.updating
  }

  update(updateControls: () => void, didMove: () => boolean): boolean {
    this.updating = true
    try {
      updateControls()
    } finally {
      this.updating = false
    }
    if (!this.settling) return false
    const moved = didMove()
    if (!this.active && !moved) this.settling = false
    return moved
  }
}
