import { useEffect, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, relativeTime } from '@/api/client'
import type { Repository } from '@/api/client'
import { useModalLock } from '@/hooks/useModalLock'

interface RepoEditModalProps {
  repo: Repository
  onClose: () => void
}

export default function RepoEditModal({ repo, onClose }: RepoEditModalProps) {
  const qc = useQueryClient()
  useModalLock(true, onClose)
  const firstInputRef = useRef<HTMLInputElement>(null)
  useEffect(() => { firstInputRef.current?.focus() }, [])
  const [cloneUrl, setCloneUrl] = useState(repo.clone_url ?? '')
  const [accessToken, setAccessToken] = useState('')
  const [clearToken, setClearToken] = useState(false)
  const [defaultBranch, setDefaultBranch] = useState(
    (repo as unknown as { default_branch?: string }).default_branch ?? 'main'
  )
  const [status, setStatus] = useState<'active' | 'disabled' | 'archived'>(
    repo.status as 'active' | 'disabled' | 'archived'
  )
  const [provider, setProvider] = useState<'github' | 'gitlab' | 'other'>(
    (repo.provider as 'github' | 'gitlab' | 'other') ?? 'other'
  )

  // Reset state when repo changes
  useEffect(() => {
    setCloneUrl(repo.clone_url ?? '')
    setAccessToken('')
    setClearToken(false)
    setStatus(repo.status as 'active' | 'disabled' | 'archived')
    setProvider((repo.provider as 'github' | 'gitlab' | 'other') ?? 'other')
  }, [repo])

  const update = useMutation({
    mutationFn: () => api.updateRepository(repo.repository_id, {
      clone_url: cloneUrl || null,
      access_token: accessToken || null,
      clear_access_token: clearToken,
      default_branch: defaultBranch,
      status,
      provider,
    }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['repositories'] })
      void qc.invalidateQueries({ queryKey: ['repository', repo.full_name] })
      onClose()
    },
  })

  const del = useMutation({
    mutationFn: () => api.deleteRepository(repo.repository_id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['repositories'] })
      onClose()
    },
  })

  const deleteBlocked = del.error && (del.error as Error).message.includes('409')

  return (
    <div
      className="modal-bg"
      role="dialog"
      aria-modal="true"
      aria-labelledby="repo-edit-modal-title"
      onClick={e => e.stopPropagation()}
    >
      <div className="modal-box" style={{ maxWidth: 520, position: 'relative' }}>
        <button
          type="button"
          className="modal-close"
          onClick={onClose}
          aria-label="关闭"
          title="关闭 (ESC)"
        >
          ×
        </button>
        <div className="modal-title" id="repo-edit-modal-title">编辑仓库</div>

        <div className="form-row">
          <label className="form-label">仓库标识</label>
          <div className="form-input" style={{ background: 'var(--surface)', fontFamily: 'monospace' }}>
            {repo.full_name}
          </div>
          <div style={{ fontSize: 11, color: 'var(--subtle)', marginTop: 4 }}>
            接入于 {relativeTime(repo.created_at)}
          </div>
        </div>

        <div className="form-row">
          <label className="form-label">代码托管平台</label>
          <div style={{ display: 'flex', gap: 6 }}>
            {(['github', 'gitlab', 'other'] as const).map(p => (
              <button
                key={p}
                type="button"
                className={provider === p ? 'btn-primary' : 'btn-sec'}
                style={{ flex: 1, justifyContent: 'center' }}
                onClick={() => setProvider(p)}
              >
                {p === 'github' ? 'GitHub' : p === 'gitlab' ? 'GitLab' : '其他'}
              </button>
            ))}
          </div>
        </div>

        <div className="form-row">
          <label className="form-label">克隆地址</label>
          <input
            ref={firstInputRef}
            className="form-input"
            placeholder="https://gitlab.example.com/org/repo.git"
            value={cloneUrl}
            onChange={e => setCloneUrl(e.target.value)}
          />
        </div>

        <div className="form-row">
          <label className="form-label">
            GitLab PAT
            {(repo as unknown as { has_token?: boolean }).has_token && (
              <span style={{ marginLeft: 8, fontSize: 10, color: 'var(--olive)' }}>✓ 已配置</span>
            )}
          </label>
          <input
            className="form-input"
            type="password"
            placeholder="留空则不修改；填入则覆盖现有令牌"
            value={accessToken}
            onChange={e => { setAccessToken(e.target.value); setClearToken(false) }}
          />
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--mid)', marginTop: 4 }}>
            <input type="checkbox" checked={clearToken} onChange={e => {
              setClearToken(e.target.checked)
              if (e.target.checked) setAccessToken('')
            }} />
            清除已保存的令牌
          </label>
        </div>

        <div className="form-2col">
          <div>
            <label className="form-label">默认分支</label>
            <input className="form-input" value={defaultBranch} onChange={e => setDefaultBranch(e.target.value)} />
          </div>
          <div>
            <label className="form-label">状态</label>
            <select className="form-input" value={status} onChange={e => setStatus(e.target.value as 'active' | 'disabled' | 'archived')}>
              <option value="active">活跃</option>
              <option value="disabled">停用</option>
              <option value="archived">已归档</option>
            </select>
          </div>
        </div>

        {update.isError && (
          <div className="error-msg" style={{ marginBottom: 12 }}>{(update.error as Error).message}</div>
        )}
        {del.isError && !deleteBlocked && (
          <div className="error-msg" style={{ marginBottom: 12 }}>{(del.error as Error).message}</div>
        )}
        {deleteBlocked && (
          <div className="error-msg" style={{ marginBottom: 12 }}>
            仓库存在历史运行 / 基线 / 触发事件，不能直接删除。请先删除相关运行，或将状态改为「已归档」。
          </div>
        )}

        <div className="modal-footer" style={{ justifyContent: 'space-between' }}>
          <button
            className="btn-sec"
            style={{ color: 'var(--red)', borderColor: 'var(--red)' }}
            disabled={del.isPending || update.isPending}
            onClick={() => {
              if (confirm(`确认删除仓库 "${repo.full_name}"？\n（仅当无历史运行时可删除）`)) {
                del.mutate()
              }
            }}
          >
            {del.isPending ? '删除中…' : '删除仓库'}
          </button>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn-sec" onClick={onClose}>取消</button>
            <button
              className="btn-primary"
              disabled={update.isPending}
              onClick={() => update.mutate()}
            >
              {update.isPending ? '保存中…' : '保存'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
