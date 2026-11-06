import type { Asset, Plate, ScanState } from '../types'
import Card from './Card'
import Field from './Field'

type AssetCardProps = {
  plate: Plate | null
  asset: Asset | null
  closestTypes: string[]
  state: ScanState
  className?: string
}

function criticalityBadge(criticality: string) {
  switch (criticality.toLowerCase()) {
    case 'high':
      return 'border-red-700 bg-red-100 text-red-900'
    case 'medium':
      return 'border-amber-600 bg-amber-100 text-amber-900'
    default:
      return 'border-slate-500 bg-slate-100 text-slate-900'
  }
}

function plateSummary(plate: Plate): string {
  const parts = [
    plate.fields.type,
    plate.fields.dn,
    plate.fields.pn,
    plate.fields.body,
    plate.fields.serial,
  ].filter((value): value is string => Boolean(value))
  return parts.length > 0 ? parts.join(', ') : 'no fields read'
}

function PlateStrip({ plate }: { plate: Plate }) {
  return (
    <p className="mt-4 rounded-lg border-2 border-slate-200 bg-slate-50 px-3 py-2 text-base font-semibold text-slate-800">
      plate: {plateSummary(plate)}
    </p>
  )
}

export default function AssetCard({
  plate,
  asset,
  closestTypes,
  state,
  className = '',
}: AssetCardProps) {
  const confidence = plate?.confidence.type
  const closest = closestTypes.slice(0, 3)

  return (
    <Card title="Asset" className={className}>
      {state === 'idle' ? (
        <p className="text-base font-medium text-slate-700">
          No scan yet. Point the camera at a nameplate and press scan.
        </p>
      ) : null}

      {state === 'error' ? (
        <p className="text-base font-semibold text-slate-800">
          The last scan did not return an asset.
        </p>
      ) : null}

      {state === 'done' && asset ? (
        <>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-4xl font-black tracking-tight text-slate-900">
                {asset.tag}
              </div>
              <div className="mt-1 text-lg font-semibold text-slate-800">
                {asset.line ?? 'line unknown'}
              </div>
            </div>
            {asset.criticality ? (
              <span
                className={`rounded-full border-2 px-3 py-0.5 text-base font-bold ${criticalityBadge(
                  asset.criticality,
                )}`}
              >
                criticality {asset.criticality}
              </span>
            ) : null}
          </div>

          <dl className="mt-4 space-y-2">
            <Field label="last service" value={asset.last_service ?? 'unknown'} />
            {plate ? <Field label="family" value={plate.family ?? 'unknown'} /> : null}
            {typeof confidence === 'number' ? (
              <Field label="confidence" value={`${Math.round(confidence * 100)} %`} />
            ) : null}
          </dl>

          {plate ? <PlateStrip plate={plate} /> : null}
        </>
      ) : null}

      {state === 'done' && !asset ? (
        <>
          <div className="text-2xl font-black text-slate-900">No asset match</div>
          <p className="mt-1 text-base font-medium text-slate-800">
            {plate
              ? 'The plate was read, but this type is not in the asset register.'
              : 'No nameplate could be read from this frame.'}
          </p>

          <button
            type="button"
            className="mt-3 rounded-lg border-2 border-slate-900 bg-slate-900 px-5 py-3 text-lg font-bold text-white hover:bg-slate-800"
          >
            Create asset
          </button>
          <p className="mt-2 text-base font-medium text-slate-700">
            Create asset is not wired up yet.
          </p>

          {closest.length > 0 ? (
            <div className="mt-4">
              <div className="text-base font-bold text-slate-900">closest types</div>
              <ul className="mt-2 space-y-1">
                {closest.map((type) => (
                  <li key={type} className="text-base font-semibold text-slate-900">
                    {type}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {plate ? <PlateStrip plate={plate} /> : null}
        </>
      ) : null}
    </Card>
  )
}
