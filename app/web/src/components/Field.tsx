import type { ReactNode } from 'react'

type FieldProps = {
  label: string
  value: ReactNode
}

export default function Field({ label, value }: FieldProps) {
  return (
    <div className="flex items-baseline gap-3">
      <dt className="w-40 shrink-0 whitespace-nowrap text-base font-semibold text-slate-700">
        {label}
      </dt>
      <dd className="text-base font-semibold text-slate-900">{value}</dd>
    </div>
  )
}
