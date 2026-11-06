import type { AssetStatus, LabAsset } from '../scene-lab/fixtures'

const STATUS_DOT: Record<AssetStatus, string> = {
  healthy: 'bg-emerald-400',
  watch: 'bg-amber-400',
  fault: 'bg-red-400',
}

const STATUS_TEXT: Record<AssetStatus, string> = {
  healthy: 'text-emerald-300',
  watch: 'text-amber-300',
  fault: 'text-red-300',
}

type SceneAssetRowProps = {
  asset: LabAsset
  selected: boolean
  onSelect: (id: string) => void
}

export default function SceneAssetRow({ asset, selected, onSelect }: SceneAssetRowProps) {
  return (
    <button
      type="button"
      onClick={() => onSelect(asset.id)}
      className={`flex w-full items-center gap-3 rounded-lg border px-3 py-2 text-left transition-colors ${
        selected
          ? 'border-cyan-400/70 bg-cyan-500/15 text-white'
          : 'border-slate-700 bg-slate-900/70 text-slate-100 hover:border-slate-500 hover:bg-slate-900'
      }`}
    >
      <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${STATUS_DOT[asset.status]}`} />
      <span className="min-w-0 flex-1">
        <span className="flex items-baseline justify-between gap-2">
          <span className="text-base font-black tracking-tight">{asset.id}</span>
          <span className={`text-xs font-bold ${STATUS_TEXT[asset.status]}`}>health {asset.health}</span>
        </span>
        <span className="block truncate text-sm font-semibold text-slate-400">
          {asset.name} - {asset.issue}
        </span>
      </span>
    </button>
  )
}
