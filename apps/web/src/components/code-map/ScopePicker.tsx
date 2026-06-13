interface Props {
  scopes: string[]
  active: string
  onChange: (scope: string) => void
}

export default function ScopePicker({ scopes, active, onChange }: Props) {
  if (scopes.length === 0) return null
  return (
    <div className="code-map-scope-picker" role="tablist" aria-label="代码地图 scope 选择">
      {scopes.map(s => (
        <button
          key={s}
          type="button"
          role="tab"
          aria-current={s === active ? 'page' : undefined}
          className={`code-map-scope-tab${s === active ? ' active' : ''}`}
          onClick={() => onChange(s)}
        >
          {s}
        </button>
      ))}
    </div>
  )
}
