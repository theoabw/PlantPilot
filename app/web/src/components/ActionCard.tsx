import type { ScanState, ServiceAction } from '../types'
import Card from './Card'
import Field from './Field'

type ActionCardProps = {
  action: ServiceAction | null
  state: ScanState
  className?: string
}

export default function ActionCard({ action, state, className = '' }: ActionCardProps) {
  return (
    <Card
      title="Next service action"
      className={className}
      badge={
        action ? (
          <span className="rounded-md border-2 border-slate-900 bg-slate-100 px-2 py-0.5 text-base font-bold text-slate-900">
            source {action.source}
          </span>
        ) : undefined
      }
    >
      {state === 'idle' ? (
        <p className="text-base font-medium text-slate-700">
          No action yet. It appears after a scan with an asset match.
        </p>
      ) : null}

      {state === 'error' ? (
        <p className="text-base font-semibold text-slate-800">
          The last scan did not return a service action.
        </p>
      ) : null}

      {state === 'done' && !action ? (
        <p className="text-base font-semibold text-slate-800">
          No service action is listed for this asset.
        </p>
      ) : null}

      {state === 'done' && action ? (
        <dl className="space-y-2">
          <Field label="part" value={action.part} />
          <Field label="action" value={action.action} />
          <Field label="interval" value={action.interval} />
          <Field label="source" value={action.source} />
        </dl>
      ) : null}
    </Card>
  )
}
