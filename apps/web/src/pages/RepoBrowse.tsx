import { useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api, relativeTime } from '@/api/client'
import Topbar from '@/components/Topbar'

function formatSize(bytes: number | null): string {
  if (bytes == null) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function extension(path: string): string {
  const i = path.lastIndexOf('.')
  return i >= 0 ? path.slice(i + 1) : ''
}

const LANG_HINT: Record<string, string> = {
  ts: 'typescript', tsx: 'tsx', js: 'javascript', jsx: 'jsx',
  py: 'python', go: 'go', rs: 'rust', java: 'java', kt: 'kotlin',
  rb: 'ruby', php: 'php', cs: 'csharp', cpp: 'cpp', c: 'c', h: 'c',
  md: 'markdown', json: 'json', yaml: 'yaml', yml: 'yaml',
  toml: 'toml', xml: 'xml', html: 'html', css: 'css', scss: 'scss',
  sh: 'bash', sql: 'sql', vue: 'vue', svelte: 'svelte',
}

function FileIcon({ type, name: _name }: { type: string; name: string }) {
  if (type === 'tree') {
    return (
      <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} style={{ color: 'var(--amber)', flexShrink: 0 }}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
      </svg>
    )
  }
  return (
    <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} style={{ color: 'var(--mid)', flexShrink: 0 }}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
    </svg>
  )
}

function Crumbs({ path, onClick }: { path: string; onClick: (p: string) => void }) {
  const parts = path.split('/').filter(Boolean)
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: 'var(--mid)', fontFamily: 'monospace', flexWrap: 'wrap' }}>
      <button className="link-btn" onClick={() => onClick('')}>root</button>
      {parts.map((p, i) => {
        const full = parts.slice(0, i + 1).join('/')
        return (
          <span key={i} style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            <span style={{ color: 'var(--subtle)' }}>/</span>
            <button className="link-btn" onClick={() => onClick(full)}>{p}</button>
          </span>
        )
      })}
    </div>
  )
}

export default function RepoBrowse() {
  const { repositoryId } = useParams<{ repositoryId: string }>()
  const [search, setSearch] = useSearchParams()
  const ref = search.get('ref') || 'main'
  const path = search.get('path') || ''
  const [view, setView] = useState<'file' | 'tree'>(search.get('view') === 'file' ? 'file' : 'tree')

  const { data: repo, error: repoErr } = useQuery({
    queryKey: ['repository', repositoryId],
    queryFn: () => api.getRepository(repositoryId!),
    enabled: !!repositoryId,
  })

  const { data: refsData } = useQuery({
    queryKey: ['repository-refs', repositoryId],
    queryFn: () => api.listRepositoryRefs(repositoryId!),
    enabled: !!repositoryId,
    retry: false,
  })

  const { data: treeData, error: treeErr, isLoading: treeLoading } = useQuery({
    queryKey: ['repository-tree', repositoryId, ref, path],
    queryFn: () => api.listRepositoryTree(repositoryId!, ref, path),
    enabled: !!repositoryId && view === 'tree',
    retry: false,
  })

  const { data: fileData, error: fileErr, isLoading: fileLoading } = useQuery({
    queryKey: ['repository-file', repositoryId, ref, path],
    queryFn: () => api.readRepositoryFile(repositoryId!, ref, path),
    enabled: !!repositoryId && view === 'file' && !!path,
    retry: false,
  })

  const branches = (refsData?.items ?? []).filter(r => r.type === 'branch')
  const tags = (refsData?.items ?? []).filter(r => r.type === 'tag')

  const setRef = (newRef: string) => {
    setSearch({ ref: newRef, path: '', view: 'tree' })
    setView('tree')
  }
  const setPath = (newPath: string) => {
    setSearch({ ref, path: newPath, view: 'tree' })
    setView('tree')
  }
  const openFile = (p: string) => {
    setSearch({ ref, path: p, view: 'file' })
    setView('file')
  }

  if (repoErr) {
    return (
      <>
        <Topbar title="文件浏览" showBack />
        <div className="content"><div className="error-msg">{(repoErr as Error).message}</div></div>
      </>
    )
  }

  return (
    <>
      <Topbar
        title={repo ? `浏览 ${repo.full_name}` : '文件浏览'}
        subtitle={repo ? `${repo.provider} · 接入于 ${relativeTime(repo.created_at)}` : ''}
        showBack
        actions={
          <select
            className="form-input"
            style={{ minWidth: 160, fontFamily: 'monospace' }}
            value={ref}
            onChange={e => setRef(e.target.value)}
          >
            <optgroup label="分支">
              {branches.map(b => <option key={b.name} value={b.name}>{b.name}</option>)}
            </optgroup>
            {tags.length > 0 && (
              <optgroup label="标签">
                {tags.map(t => <option key={t.name} value={t.name}>{t.name}</option>)}
              </optgroup>
            )}
          </select>
        }
      />

      <div className="content">
        <div className="card" style={{ padding: 16, marginBottom: 12 }}>
          <Crumbs path={path} onClick={setPath} />
        </div>

        {treeErr && <div className="error-msg">{(treeErr as Error).message}</div>}
        {fileErr && <div className="error-msg">{(fileErr as Error).message}</div>}

        {view === 'tree' && (
          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            {treeLoading && <div className="empty-state">加载中…</div>}
            {!treeLoading && treeData && treeData.items.length === 0 && (
              <div className="empty-state">空目录</div>
            )}
            {!treeLoading && treeData && treeData.items.map(item => (
              <div
                key={item.path}
                className="file-row"
                style={{ cursor: 'pointer' }}
                onClick={() => item.type === 'tree' ? setPath(item.path) : openFile(item.path)}
              >
                <FileIcon type={item.type} name={item.name} />
                <span className="file-name" style={{ flex: 1 }}>{item.name}</span>
                {item.type === 'blob' && (
                  <>
                    <span style={{ fontSize: 10, color: 'var(--subtle)', textTransform: 'uppercase' }}>
                      {LANG_HINT[extension(item.name)] ?? extension(item.name)}
                    </span>
                    <span style={{ fontSize: 11, color: 'var(--subtle)', minWidth: 70, textAlign: 'right' }}>
                      {formatSize(item.size)}
                    </span>
                  </>
                )}
                {item.type === 'tree' && (
                  <svg width="12" height="12" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} style={{ color: 'var(--subtle)' }}>
                    <polyline points="9 18 15 12 9 6" />
                  </svg>
                )}
              </div>
            ))}
          </div>
        )}

        {view === 'file' && (
          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            <div style={{ padding: '8px 16px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--surface2)' }}>
              <div style={{ fontSize: 11, color: 'var(--mid)', fontFamily: 'monospace' }}>
                {path} · {fileData?.encoding ?? '...'} · {fileData ? formatSize(fileData.size) : '...'}
              </div>
              <div style={{ display: 'flex', gap: 6 }}>
                <button className="btn-sec" style={{ padding: '2px 10px', fontSize: 11 }} onClick={() => { navigator.clipboard.writeText(fileData?.content ?? ''); }}>
                  复制
                </button>
                <button className="btn-sec" style={{ padding: '2px 10px', fontSize: 11 }} onClick={() => { setView('tree'); setSearch({ ref, path, view: 'tree' }) }}>
                  返回目录
                </button>
              </div>
            </div>
            {fileLoading && <div className="empty-state">加载中…</div>}
            {!fileLoading && fileData && !fileData.is_text && (
              <div className="empty-state">二进制文件，无法预览（{formatSize(fileData.size)}）</div>
            )}
            {!fileLoading && fileData?.content != null && (
              <pre style={{
                background: '#0d0d0c', color: '#e9e7de', padding: 16,
                fontSize: 12, fontFamily: 'SF Mono, Cascadia Code, monospace',
                lineHeight: 1.55, whiteSpace: 'pre', overflowX: 'auto', maxHeight: 'calc(100vh - 240px)',
                margin: 0,
              }}>
                {fileData.content}
              </pre>
            )}
          </div>
        )}
      </div>
    </>
  )
}
