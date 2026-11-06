import type { Health } from '../types'

type TopBarProps = {
  health: Health | null
}

// Product chrome only. What is loaded, how fast it answered and whether a demo
// is being run belong in the pitch, not in the console a plant would operate.
export default function TopBar({ health }: TopBarProps) {
  return (
    <header className="masthead">
      <div className="wordmark">
        PlantPilot<span>inspection missions in a scanned plant</span>
      </div>
      {health ? null : null}
    </header>
  )
}
