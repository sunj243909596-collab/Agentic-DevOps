import { shortSha } from '@/api/client'
import type { CodeMapChange } from '@/api/client'

interface Props {
  commits: Array<{ sha: string; subject: string }>
  files: CodeMapChange[]
}

const STATUS_LABEL: Record<string, string> = { A: '新增', M: '修改', D: '删除', R: '重命名' }

export default function ChangeList({ commits, files }: Props) {
  if (commits.length === 0) {
    return <div className="code-map-empty">暂无 git 变更记录</div>
  }
  return (
    <div className="code-map-changes">
      {commits.map(c => {
        const fileList = files.filter(f => f.commit === c.sha)
        return (
          <div key={c.sha} className="code-map-commit">
            <div className="code-map-commit-head">
              <code className="code-map-commit-sha">{shortSha(c.sha)}</code>
              <span className="code-map-commit-subject">{c.subject}</span>
            </div>
            <ul className="code-map-commit-files">
              {fileList.map(f => (
                <li key={f.path} className="code-map-commit-file">
                  <div className="code-map-commit-file-head">
                    <span className={`code-map-status code-map-status-${f.status}`}>
                      {STATUS_LABEL[f.status] || f.status}
                    </span>
                    <code className="code-map-commit-file-path">{f.path}</code>
                  </div>
                  {f.module ? (
                    <div className="code-map-commit-file-context">
                      <span className="code-map-commit-file-module">{f.module.module_id}</span>
                      <span className="code-map-commit-file-resp">{f.module.responsibility || '（无职责说明）'}</span>
                    </div>
                  ) : (
                    <div className="code-map-commit-file-context unowned">未归属</div>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )
      })}
    </div>
  )
}
