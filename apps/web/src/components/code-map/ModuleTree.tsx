import type { CodeMapModule } from '@/api/client'

interface Props {
  modules: CodeMapModule[]
  activeId: string | null
  onSelect: (m: CodeMapModule) => void
}

export default function ModuleTree({ modules, activeId, onSelect }: Props) {
  if (modules.length === 0) {
    return <div className="code-map-empty">该 scope 还没有模块</div>
  }
  return (
    <ul className="code-map-tree" role="tree" aria-label="模块列表">
      {modules.map(m => (
        <li key={m.id} role="treeitem">
          <button
            type="button"
            className={`code-map-tree-item${m.id === activeId ? ' active' : ''}`}
            onClick={() => onSelect(m)}
            aria-current={m.id === activeId ? 'true' : undefined}
          >
            <span className={`code-map-kind code-map-kind-${m.kind}`}>{m.kind}</span>
            <span className="code-map-tree-name">{m.name || m.id}</span>
            <span className="code-map-tree-id">{m.id}</span>
          </button>
        </li>
      ))}
    </ul>
  )
}
