import { useEffect, useState } from 'react'
import { WORDMARK_SVG } from './brandWordmark'

// The intro is for a first visit. Direct links, screenshots and recordings skip it:
// ?demo or ?skipintro, and the capture flags ?sharp, ?perf and a camera pose (?eye=).
const SKIP_PARAMS = ['demo', 'skipintro', 'sharp', 'perf', 'eye']

export function shouldShowIntro(search: string): boolean {
  const params = new URLSearchParams(search)
  return !SKIP_PARAMS.some((name) => params.has(name))
}

type Props = {
  progress: number
  loaded: boolean
  onStart: () => void
}

const OUTLINE = 'M16 92V48L40 32V48L64 32V48L96 24V92Z'
const ARROW = 'M78 55L65 83L60 70L46 65Z'

/** Full-screen first impression: the mark draws itself, the arrow drops in, one line, one button. */
export default function StartScreen({ progress, loaded, onStart }: Props) {
  const [leaving, setLeaving] = useState(false)

  const start = () => {
    if (leaving) {
      return
    }
    setLeaving(true)
    window.setTimeout(onStart, 420)
  }

  // Enter starts the demo without stealing focus (an auto-focused button shows a focus ring on load).
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Enter') {
        start()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  const percent = Math.max(0, Math.min(100, Math.round(progress)))

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="pp-intro-title"
      className={`pp-intro absolute inset-0 z-50 flex flex-col items-center justify-center bg-brand-navy/80 px-6 text-center text-white backdrop-blur-md ${leaving ? 'pp-intro-leave' : ''}`}
    >
      <div className="pp-intro-glow pointer-events-none absolute left-1/2 top-1/2 h-[34rem] w-[34rem] -translate-x-1/2 -translate-y-1/2 rounded-full" />

      <h1 id="pp-intro-title" className="relative flex items-center gap-2 sm:gap-3">
        <svg className="h-20 w-20 overflow-visible sm:h-28 sm:w-28" viewBox="0 0 112 112" aria-hidden="true">
          <path className="pp-intro-outline" d={OUTLINE} pathLength={1} fill="none" stroke="#FFFFFF" strokeWidth={6} strokeLinejoin="round" />
          <path className="pp-intro-arrow" d={ARROW} fill="#26D6BC" />
        </svg>
        <svg className="pp-intro-word h-14 w-auto sm:h-20" viewBox="124 20 236 80" role="img" aria-label="PlantPilot" dangerouslySetInnerHTML={{ __html: WORDMARK_SVG }} />
      </h1>

      <p className="pp-intro-rise relative mt-6 text-2xl font-semibold tracking-wide sm:text-3xl" style={{ animationDelay: '1.35s' }}>
        From scan to service.
      </p>
      <p className="pp-intro-rise relative mt-3 max-w-md text-balance text-base text-slate-300 sm:text-lg" style={{ animationDelay: '1.5s' }}>
        A raw 3D scan, turned into a plant a robot can work in.
      </p>

      <div className="pp-intro-rise relative mt-10 flex flex-col items-center gap-3" style={{ animationDelay: '1.7s' }}>
        <button
          type="button"
          onClick={start}
          className="pp-intro-button rounded-full bg-brand-mint px-10 py-4 text-lg font-black text-brand-navy shadow-[0_10px_40px_-8px_rgba(38,214,188,0.65)] transition hover:-translate-y-0.5 hover:bg-[#3ee3cb] focus:outline-none focus-visible:ring-4 focus-visible:ring-brand-mint/40 active:translate-y-0"
        >
          Start demo
        </button>
        {/* Only while the capture loads; once it is drawn the button stands alone. */}
        <div className={`flex h-4 items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-400 transition-opacity duration-500 ${loaded ? 'opacity-0' : 'opacity-100'}`} aria-live="polite" aria-hidden={loaded}>
          {loaded ? null : (
            <>
              <span className="relative block h-1 w-24 overflow-hidden rounded-full bg-white/10">
                <span className="absolute inset-y-0 left-0 rounded-full bg-brand-mint transition-[width] duration-300" style={{ width: `${Math.max(4, percent)}%` }} />
              </span>
              <span>Loading the scan {percent}%</span>
            </>
          )}
        </div>
      </div>

      <p className="pp-intro-rise absolute inset-x-0 bottom-6 text-balance px-6 text-xs text-slate-400" style={{ animationDelay: '1.9s' }}>
        Valmet challenge · Since AI Hackathon 2026 · Team Temporary Solution
      </p>
    </div>
  )
}
