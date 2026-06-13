import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { api, relativeTime } from '@/api/client'
import Topbar from '@/components/Topbar'
import RepoEditModal from '@/components/RepoEditModal'
import type { Repository } from '@/api/client'

const PROVIDER_BADGE: Record<string, { label: string; cls: string }> = {
  github: { label: 'GitHub',   cls: 'badge-push' },
  gitlab: { label: 'GitLab',   cls: 'badge-pr'   },
  other:  { label: '其他',     cls: 'badge-manual' },
}

function providerBadge(p: string) {
  return PROVIDER_BADGE[p] ?? { label: p, cls: 'badge-manual' }
}

function RepoCard({ repo, onEdit, onBrowse }: { repo: Repository; onEdit: () => void; onBrowse: () => void }) {
  const name = repo.full_name.split('/')[1] ?? repo.full_name
  const pb = providerBadge(repo.provider)
  return (
    <div className="repo-card">
      <div onClick={onEdit}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 6 }}>
          <div className="repo-card-name">{name}</div>
          <span className={`badge ${pb.cls}`} style={{ fontSize: '9px' }}>{pb.label}</span>
        </div>
        <div className="repo-card-full">{repo.full_name}</div>
        <div className="repo-card-stats">
          <div>
            <div className="rcs-label">接入时间</div>
            <div style={{ fontSize: 12, fontWeight: 600, marginTop: 3 }}>{relativeTime(repo.created_at)}</div>
          </div>
          <div>
            <div className="rcs-label">状态</div>
            <div style={{ fontSize: 12, fontWeight: 600, marginTop: 3 }}>
              {repo.status === 'active' ? '活跃' : repo.status === 'disabled' ? '停用' : repo.status === 'archived' ? '已归档' : repo.status}
            </div>
          </div>
        </div>
      </div>
      <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px solid var(--border)', display: 'flex', gap: 6 }}>
        <button
          className="btn-sec"
          style={{ flex: 1, padding: '4px 8px', fontSize: 11 }}
          onClick={onBrowse}
        >
          <svg width="10" height="10" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} style={{ verticalAlign: 'middle', marginRight: 4 }}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 19a2 2 0 01-2-2V7a2 2 0 012-2h4l2 2h7a2 2 0 012 2v8a2 2 0 01-2 2H5z" />
          </svg>
          浏览文件
        </button>
        <button
          className="btn-sec"
          style={{ flex: 1, padding: '4px 8px', fontSize: 11 }}
          onClick={onEdit}
        >
          <svg width="10" height="10" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} style={{ verticalAlign: 'middle', marginRight: 4 }}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
          </svg>
          编辑设置
        </button>
      </div>
    </div>
  )
}

export default function Repositories() {
  const navigate = useNavigate()
  const [filter, setFilter] = useState('')
  const [editing, setEditing] = useState<Repository | null>(null)

  const { data, isLoading, error } = useQuery({
    queryKey: ['repositories'],
    queryFn: () => api.listRepositories(),
  })

  const all = data?.items ?? []
  const repos = filter
    ? all.filter(r => r.full_name.toLowerCase().includes(filter.toLowerCase()))
    : all

  return (
    <>
      <Topbar
        title="代码仓库"
        actions={
          <>
            <div className="search-wrap">
              <svg className="search-icon" width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
              <input className="search-input" placeholder="搜索仓库…" value={filter} onChange={e => setFilter(e.target.value)} />
            </div>
            <span style={{ fontSize: 12, color: 'var(--mid)' }}>
              {filter ? `${repos.length} / ${all.length}` : `共 ${all.length} 个`}
            </span>
          </>
        }
      />
      <div className="content">
        {isLoading && <div className="empty-state">加载中…</div>}
        {error && <div className="error-msg">{(error as Error).message}</div>}
        {!isLoading && !error && all.length === 0 && (
          <div className="empty-state">尚未接入任何仓库。请在「控制台」点击「新建运行」首次触发，或配置 GitLab Webhook 后自动接入。</div>
        )}
        {!isLoading && !error && all.length > 0 && repos.length === 0 && (
          <div className="empty-state">没有匹配 "{filter}" 的仓库</div>
        )}
        {!isLoading && !error && repos.length > 0 && (
          <div className="repo-grid">
            {repos.map(r => <RepoCard
              key={r.repository_id}
              repo={r}
              onEdit={() => setEditing(r)}
              onBrowse={() => navigate(`/repositories/${r.repository_id}/browse`)}
            />)}
          </div>
        )}
      </div>
      {editing && <RepoEditModal repo={editing} onClose={() => setEditing(null)} />}
    </>
  )
}
