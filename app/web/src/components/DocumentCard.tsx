import type { ScanState, Section } from '../types'
import Card from './Card'

type DocumentCardProps = {
  section: Section | null
  state: ScanState
  className?: string
}

// The winning manual section: title, page, a two line quote and a link whose
// href is the anchor returned by the API.
export default function DocumentCard({ section, state, className = '' }: DocumentCardProps) {
  return (
    <Card
      title="Manual section"
      className={className}
      badge={
        section ? (
          <span className="text-base font-bold text-slate-700">page {section.page}</span>
        ) : undefined
      }
    >
      {state === 'idle' ? (
        <p className="text-base font-medium text-slate-700">
          No section yet. It appears after a scan with a readable nameplate.
        </p>
      ) : null}

      {state === 'error' ? (
        <p className="text-base font-semibold text-slate-800">
          The last scan did not return a manual section.
        </p>
      ) : null}

      {state === 'done' && !section ? (
        <p className="text-base font-semibold text-slate-800">
          No manual section was cited for this scan.
        </p>
      ) : null}

      {state === 'done' && section ? (
        <>
          <h3 className="text-xl font-bold text-slate-900">{section.title}</h3>
          <p className="mt-1 text-base font-semibold text-slate-700">
            section {section.id}, page {section.page}
          </p>

          <blockquote className="mt-3 line-clamp-2 whitespace-pre-line border-l-4 border-slate-900 bg-slate-50 py-2 pl-3 text-base font-medium italic text-slate-900">
            {section.quote}
          </blockquote>

          <a
            href={section.anchor}
            className="mt-3 inline-block text-base font-bold text-blue-800 underline decoration-2 underline-offset-2 hover:text-blue-900"
          >
            open the manual at page {section.page}
          </a>
        </>
      ) : null}
    </Card>
  )
}
