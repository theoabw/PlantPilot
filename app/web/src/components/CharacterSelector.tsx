export type CharacterOption = {
  id: 'humanoid' | 'amr' | 'cargo'
  label: string
  radius: number
  height: number
  crouchHeight?: number
}

type Props = {
  options: CharacterOption[]
  selected: CharacterOption['id']
  open: boolean
  ready: boolean
  onToggle: () => void
  onSelect: (id: CharacterOption['id']) => void
}

export default function CharacterSelector({ options, selected, open, ready, onToggle, onSelect }: Props) {
  const active = options.find((option) => option.id === selected)
  return (
    <div className="relative">
      <button
        type="button"
        aria-expanded={open}
        aria-controls="character-options"
        onClick={onToggle}
        className="rounded-lg border border-white/5 bg-slate-950/55 px-2 py-2 text-[10px] font-bold text-slate-200 backdrop-blur hover:border-slate-500 sm:px-3 sm:text-xs"
      >
        Character <span className="hidden text-brand-mint sm:inline">{active?.label}</span>
      </button>
      {open ? (
        <div id="character-options" className="absolute right-0 mt-2 w-56 rounded-xl border border-slate-700 bg-slate-950/95 p-2 shadow-2xl backdrop-blur">
          <p className="px-2 pb-1 pt-1 text-[10px] font-black uppercase tracking-[0.14em] text-slate-500">Character</p>
          {options.map((option) => (
            <button
              key={option.id}
              type="button"
              aria-pressed={selected === option.id}
              disabled={!ready}
              onClick={() => onSelect(option.id)}
              className={`flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-50 ${
                selected === option.id ? 'bg-brand-mint/15 text-brand-mint' : 'text-slate-300 hover:bg-slate-800'
              }`}
            >
              {option.label}
              {selected === option.id ? <span className="text-[10px]">active</span> : null}
            </button>
          ))}
          {!ready ? <p className="px-2 pt-1 text-[10px] text-slate-400">Waiting for the starting route.</p> : null}
          <p className="px-2 pt-1 text-[10px] text-slate-400">Changing character returns it to the start.</p>
        </div>
      ) : null}
    </div>
  )
}
