import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, relativeTime } from '@/api/client'
import { useModalLock } from '@/hooks/useModalLock'

interface TriggerModalProps { onClose: () => void }

type Provider = 'github' | 'gitlab' | 'other'

const PROVIDER_OPTIONS: { value: Provider; label: string; placeholder: string; needToken: boolean }[] = [
  { value: 'github', label: 'GitHub',   placeholder: 'https://github.com/org/repo.git',         needToken: false },
  { value: 'gitlab', label: 'GitLab',   placeholder: 'https://gitlab.example.com/org/repo.git', needToken: true  },
  { value: 'other',  label: '其他',     placeholder: 'https://your-git-host.com/org/repo.git',  needToken: true  },
]

export default function TriggerModal({ onClose }: TriggerModalProps) {
  const qc = useQueryClient()
  const [form, setForm] = useState({
    repository: '',
    target_branch: 'main',
    clone_url: '',
    target_sha: '',
    access_token: '',
    provider: 'gitlab' as Provider,
  })
  const [lookupName, setLookupName] = useState<string | null>(null)
  const firstInputRef = useRef<HTMLInputElement>(null)

  useModalLock(true, onClose)

  // Focus the first input on open so Enter doesn't accidentally re-trigger
  // the "新建运行" button that was just clicked.
  useEffect(() => {
    firstInputRef.current?.focus()
  }, [])

  const { data: existingRepo } = useQuery({
    queryKey: ['repository', lookupName],
    queryFn: async () => {
      const d = await api.listRepositories()
      return d.items.find(r => r.full_name === lookupName) ?? null
    },
    enabled: !!lookupName,
  })

  // Auto-pick provider from existing repo
  useEffect(() => {
    if (existingRepo?.provider) {
      const p = existingRepo.provider as Provider
      if (['github', 'gitlab', 'other'].includes(p)) {
        setForm(f => ({ ...f, provider: p }))
      }
    }
  }, [existingRepo])

  const mutation = useMutation({
    mutationFn: () => api.createRun({
      repository: form.repository,
      target_branch: form.target_branch,
      clone_url: form.clone_url || undefined,
      target_sha: form.target_sha || undefined,
      access_token: form.access_token || undefined,
      provider: form.provider,
    }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['runs'] })
      void qc.invalidateQueries({ queryKey: ['repositories'] })
      onClose()
    },
  })

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }))

  const tokenConfigured = !!existingRepo && !!lookupName
  const currentProvider = PROVIDER_OPTIONS.find(p => p.value === form.provider)!

  return (
    <div
      className="modal-bg"
      role="dialog"
      aria-modal="true"
      aria-labelledby="trigger-modal-title"
      onClick={e => e.stopPropagation()}
    >
      <div className="modal-box">
        <button
          type="button"
          className="modal-close"
          onClick={onClose}
          aria-label="关闭"
          title="关闭 (ESC)"
        >
          ×
        </button>
        <div className="modal-title" id="trigger-modal-title">手动触发运行</div>

        <div className="form-row">
          <label className="form-label">代码托管平台 <span style={{ color: 'var(--clay)' }}>*</span></label>
          <div style={{ display: 'flex', gap: 6 }}>
            {PROVIDER_OPTIONS.map(p => (
              <button
                key={p.value}
                type="button"
                className={form.provider === p.value ? 'btn-primary' : 'btn-sec'}
                style={{ flex: 1, justifyContent: 'center' }}
                onClick={() => setForm(f => ({ ...f, provider: p.value }))}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        <div className="form-row">
          <label className="form-label">代码仓库 <span style={{ color: 'var(--clay)' }}>*</span></label>
          <input
            ref={firstInputRef}
            className="form-input"
            placeholder={form.provider === 'github' ? 'org/repo-name' : form.provider === 'gitlab' ? 'group/subgroup/repo' : 'org/repo-name'}
            value={form.repository}
            onChange={set('repository')}
            onBlur={e => setLookupName(e.target.value || null)}
          />
          {lookupName && existingRepo && (
            <div style={{ fontSize: 11, marginTop: 4, color: 'var(--olive)' }}>
              ✓ 已存在（{relativeTime(existingRepo.created_at)} 接入 · {existingRepo.provider}）
            </div>
          )}
          {lookupName && !existingRepo && existingRepo !== undefined && (
            <div style={{ fontSize: 11, marginTop: 4, color: 'var(--mid)' }}>
              首次接入 — 填写以下信息后即可触发
            </div>
          )}
        </div>

        <div className="form-row">
          <label className="form-label">克隆地址</label>
          <input
            className="form-input"
            placeholder={currentProvider.placeholder}
            value={form.clone_url}
            onChange={set('clone_url')}
          />
          {existingRepo?.clone_url && (
            <div style={{ fontSize: 11, marginTop: 4, color: 'var(--subtle)', fontFamily: 'monospace' }}>
              当前：{existingRepo.clone_url}
            </div>
          )}
        </div>

        <div className="form-row">
          <label className="form-label">
            {currentProvider.label} 访问令牌
            {tokenConfigured && (
              <span style={{ marginLeft: 8, fontSize: 10, color: 'var(--olive)' }}>✓ 已配置</span>
            )}
          </label>
          <input
            className="form-input"
            type="password"
            placeholder={tokenConfigured ? '留空保持现状，填写则更新令牌' :
              currentProvider.needToken
                ? `${currentProvider.label} 私有仓库必填`
                : '公开仓库无需令牌'}
            value={form.access_token}
            onChange={set('access_token')}
          />
          <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 4 }}>
            令牌保存到仓库配置后，后续触发自动复用。
          </div>
        </div>

        <div className="form-2col">
          <div>
            <label className="form-label">目标分支 <span style={{ color: 'var(--clay)' }}>*</span></label>
            <input className="form-input" value={form.target_branch} onChange={set('target_branch')} />
          </div>
          <div>
            <label className="form-label">目标提交（可选）</label>
            <input className="form-input mono" style={{ fontSize: 12 }} placeholder="HEAD（最新）" value={form.target_sha} onChange={set('target_sha')} />
          </div>
        </div>

        {mutation.isError && (
          <div className="error-msg" style={{ marginBottom: 12 }}>
            {(mutation.error as Error).message}
          </div>
        )}

        <div className="modal-tip">
          流水线将异步执行。提交后可在控制台立即看到新记录，初始状态为「已接收触发」。
        </div>

        <div className="modal-footer">
          <button className="btn-sec" onClick={onClose}>取消</button>
          <button
            className="btn-primary"
            onClick={() => mutation.mutate()}
            disabled={!form.repository || !form.target_branch || mutation.isPending}
          >
            {mutation.isPending ? '提交中…' : '触发运行'}
          </button>
        </div>
      </div>
    </div>
  )
}
