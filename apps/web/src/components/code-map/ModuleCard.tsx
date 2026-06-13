import type { CodeMapModule } from '@/api/client'

interface Props { m: CodeMapModule }

const filename = (path: string) => path.split('/').pop() || path

export default function ModuleCard({ m }: Props) {
  return (
    <div className="code-map-card">
      <div className="code-map-card-head">
        <h2 className="code-map-card-name">{m.name || m.id}</h2>
        <span className="code-map-card-id">{m.id}</span>
        <span className={`code-map-kind code-map-kind-${m.kind}`}>{m.kind}</span>
      </div>

      {m.responsibility && (
        <div className="code-map-card-row">
          <div className="code-map-card-label">职责</div>
          <div className="code-map-card-value">{m.responsibility}</div>
        </div>
      )}

      {m.entry_points.length > 0 && (
        <div className="code-map-card-row">
          <div className="code-map-card-label">入口</div>
          <ul className="code-map-card-files">
            {m.entry_points.map(p => <li key={p}><code>{filename(p)}</code></li>)}
          </ul>
        </div>
      )}

      {m.key_files.length > 0 && (
        <div className="code-map-card-row">
          <div className="code-map-card-label">核心文件</div>
          <ul className="code-map-card-files">
            {m.key_files.map(p => <li key={p}><code>{filename(p)}</code></li>)}
          </ul>
        </div>
      )}
    </div>
  )
}
