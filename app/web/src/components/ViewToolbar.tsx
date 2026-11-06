import type { ReactNode } from 'react'

type ViewToolbarProps = {
  follow: boolean
  followEnabled?: boolean
  panelOpen: boolean
  faultCount: number
  onOverview: () => void
  onFollow: () => void
  onReset: () => void
  onTogglePanel: () => void
}

type ToolButtonProps = {
  label: string
  active?: boolean
  badge?: number
  onClick: () => void
  children: ReactNode
}

function ToolButton({ label, active = false, badge, onClick, children }: ToolButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      aria-pressed={active}
      className={`relative flex w-10 flex-col items-center gap-1 rounded-lg border px-1.5 py-2 text-[10px] font-black uppercase tracking-[0.12em] backdrop-blur transition-colors lg:w-[86px] lg:px-2 ${
        active
          ? 'border-cyan-400/70 bg-cyan-500/20 text-cyan-200'
          : 'border-slate-600/80 bg-slate-950/75 text-slate-300 hover:border-slate-400 hover:text-white'
      }`}
    >
      {children}
      <span className="hidden lg:block">{label}</span>
      {badge && badge > 0 ? (
        <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full border border-slate-950 bg-red-500 px-1 text-[9px] font-black text-white">
          {badge}
        </span>
      ) : null}
    </button>
  )
}

export default function ViewToolbar({
  follow,
  followEnabled = true,
  panelOpen,
  faultCount,
  onOverview,
  onFollow,
  onReset,
  onTogglePanel,
}: ViewToolbarProps) {
  return (
    <div
      className={`pointer-events-auto absolute right-3 top-3 z-20 flex flex-col gap-1.5 transition-[right] duration-200 lg:top-1/2 lg:-translate-y-1/2 ${
        panelOpen ? 'lg:right-[402px]' : 'lg:right-3'
      }`}
      aria-label="Scene view controls"
    >
      <p className="hidden text-center text-[9px] font-black uppercase tracking-[0.2em] text-slate-500 lg:block">View</p>

      <ToolButton label="Overview" onClick={onOverview}>
        <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <path d="M3 10.8 12 3l9 7.8" />
          <path d="M5.5 9.5V21h13V9.5" />
          <path d="M9.5 21v-6h5v6" />
        </svg>
      </ToolButton>

      {followEnabled ? (
      <ToolButton label={follow ? 'Following' : 'Follow'} active={follow} onClick={onFollow}>
        <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="6.5" />
          <circle cx="12" cy="12" r="2" />
          <path d="M12 2v3M12 19v3M2 12h3M19 12h3" />
        </svg>
      </ToolButton>
      ) : null}

      <ToolButton label="Reset" onClick={onReset}>
        <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <path d="M4 5v5h5" />
          <path d="M4.8 10a8 8 0 1 0 2.2-5.2L4 8" />
        </svg>
      </ToolButton>

      <div className={`flex flex-col gap-1.5 ${panelOpen ? 'max-lg:hidden' : ''}`}>
        <div className="my-0.5 h-px w-full bg-slate-700/70" />

        <ToolButton label={panelOpen ? 'Close' : 'Panel'} active={panelOpen} badge={faultCount} onClick={onTogglePanel}>
          <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="4" width="18" height="16" rx="2" />
            <path d="M15 4v16" />
            <path d="M7 9h4M7 13h4" />
          </svg>
        </ToolButton>
      </div>
    </div>
  )
}
