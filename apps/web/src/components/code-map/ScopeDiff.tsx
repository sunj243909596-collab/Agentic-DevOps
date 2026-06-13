import type { CodeMapDiff } from '@/api/client'

export default function ScopeDiff({ diff }: { diff: CodeMapDiff }) {
  return (
    <div className="code-map-diff">
      <div className="code-map-diff-versions">
        <span className="code-map-diff-from">v{diff.from_version}</span>
        <span> → </span>
        <span className="code-map-diff-to">v{diff.to_version}</span>
      </div>

      {diff.added_modules.length > 0 && (
        <section className="code-map-diff-section">
          <h3>新增模块 ({diff.added_modules.length})</h3>
          <ul>{diff.added_modules.map(m => <li key={m.id} className="added">+ {m.id} <em>{m.name}</em></li>)}</ul>
        </section>
      )}

      {diff.removed_modules.length > 0 && (
        <section className="code-map-diff-section">
          <h3>删除模块 ({diff.removed_modules.length})</h3>
          <ul>{diff.removed_modules.map(m => <li key={m.id} className="removed">- {m.id} <em>{m.name}</em></li>)}</ul>
        </section>
      )}

      {diff.changed_modules.length > 0 && (
        <section className="code-map-diff-section">
          <h3>修改模块 ({diff.changed_modules.length})</h3>
          <ul>{diff.changed_modules.map(c => (
            <li key={c.id} className="changed">
              ~ {c.id} <em>[{c.fields_changed.join(', ')}]</em>
            </li>
          ))}</ul>
        </section>
      )}

      {(diff.added_edges.length > 0 || diff.removed_edges.length > 0) && (
        <section className="code-map-diff-section">
          <h3>依赖变更</h3>
          <ul>
            {diff.added_edges.map((e, i) => (
              <li key={`a${i}`} className="added">+ edge: {e.from} → {e.to}{e.via ? ` (${e.via})` : ''}</li>
            ))}
            {diff.removed_edges.map((e, i) => (
              <li key={`r${i}`} className="removed">- edge: {e.from} → {e.to}</li>
            ))}
          </ul>
        </section>
      )}

      {diff.added_modules.length === 0 && diff.removed_modules.length === 0
       && diff.changed_modules.length === 0 && diff.added_edges.length === 0
       && diff.removed_edges.length === 0 && (
        <div className="code-map-empty">v{diff.from_version} → v{diff.to_version} 无变更</div>
       )}
    </div>
  )
}
