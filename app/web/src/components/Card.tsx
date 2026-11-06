import type { ReactNode } from 'react'

type CardProps = {
  title: string
  badge?: ReactNode
  children: ReactNode
  className?: string
}

// One card style for the whole right column. Titles are 20px, body copy is 16px
// and never lighter than slate-700, so the cards stay readable from a distance.
export default function Card({ title, badge, children, className = '' }: CardProps) {
  return (
    <section
      className={`rounded-xl border-2 border-slate-300 bg-white p-4 shadow-sm ${className}`}
    >
      <header className="mb-3 flex items-baseline justify-between gap-3">
        <h2 className="text-xl font-bold tracking-tight text-slate-900">{title}</h2>
        {badge}
      </header>
      {children}
    </section>
  )
}
