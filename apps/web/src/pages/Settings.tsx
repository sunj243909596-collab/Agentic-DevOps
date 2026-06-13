import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import Topbar from '@/components/Topbar'
import { pushToast } from '@/components/Toast'
import type { Setting } from '@/api/client'

const PATH_KEYS = new Set(['git_workspace', 'git_hunks_dir'])

// Note: this `Section` type is intentionally a string-literal union,
// used as the active-tab key in the new two-column layout (Task 8).
type Section = 'llm' | 'paths' | 'versions'

const SECTION_LABELS: Record<Section, string> = {
  llm:      'LLM 大模型',
  paths:    '路径',
  versions: '版本',
}

const LLM_PROVIDERS = [
  { value: 'claude', label: 'Anthropic (Claude)', desc: '需要 Anthropic API key' },
  { value: 'mock',   label: 'Mock (演示用)',       desc: '无 API 调用的占位 provider' },
] as const

// TODO: extend this map when adding new path settings; the `?? s.key`
// fallback in PathsSection will display the raw key otherwise.
const PATH_LABELS: Record<string, string> = {
  git_workspace: 'Git 工作目录',
  git_hunks_dir: 'Hunks 缓存目录',
}

function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string
  hint?: string
  error?: string
  children: React.ReactNode
}) {
  return (
    <div className="settings-field">
      <div className="settings-h2">
        {label}
        {hint && <span className="settings-field-hint">{hint}</span>}
      </div>
      {children}
      {error && <div className="settings-field-error">{error}</div>}
    </div>
  )
}

function NavItem({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      className={`settings-nav-item${active ? ' active' : ''}`}
      onClick={onClick}
      aria-current={active ? 'page' : undefined}
    >
      {children}
    </button>
  )
}

function PathConfirmBanner({
  onConfirm,
  onCancel,
}: {
  onConfirm: () => void
  onCancel: () => void
}) {
  return (
    <div
      className="card"
      role="alertdialog"
      aria-label="路径配置修改确认"
      style={{
        padding: 14,
        marginBottom: 12,
        background: 'rgba(217,119,87,.06)',
        border: '1px solid rgba(217,119,87,.25)',
      }}
    >
      <div style={{ fontSize: 12, color: 'var(--text)' }}>
        <strong>⚠ 检测到路径类配置修改。</strong>确认要保存并执行目录迁移吗？
        <div style={{ fontSize: 11, color: 'var(--mid)', marginTop: 6 }}>
          新路径下若已有同名目录，保存会失败（409）。请先手动处理冲突。
        </div>
      </div>
      <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
        <button type="button" className="btn-primary" onClick={onConfirm}>确认保存</button>
        <button type="button" className="btn-sec" onClick={onCancel}>取消</button>
      </div>
    </div>
  )
}

function LLMSection({
  llmSettings,
  drafts,
  setDrafts,
  fieldErrors,
  showSecret,
  onToggleSecret,
  savedProvider,
}: {
  llmSettings: Setting[]
  drafts: Record<string, string>
  setDrafts: React.Dispatch<React.SetStateAction<Record<string, string>>>
  fieldErrors: Record<string, string>
  showSecret: boolean
  onToggleSecret: () => void
  savedProvider: string
}) {
  const currentProvider =
    drafts.llm_provider ??
    llmSettings.find(s => s.key === 'llm_provider')?.value ??
    'mock'
  const providerChanged =
    drafts.llm_provider !== undefined && drafts.llm_provider !== savedProvider

  const draftOf = (s: Setting) => drafts[s.key] ?? s.value
  const onChangeOf = (s: Setting) => (v: string) =>
    setDrafts(d => ({ ...d, [s.key]: v }))

  const modelKey    = llmSettings.find(s => s.key === 'llm_model')
  const baseUrlKey  = llmSettings.find(s => s.key === 'llm_base_url')
  const apiKeyKey   = llmSettings.find(s => s.key === 'llm_api_key')

  return (
    <div className="card" style={{ padding: '28px 32px' }}>
      <div className="settings-h2" style={{ marginBottom: 16 }}>
        大语言模型（LLM）
      </div>

      {/* Provider 2x2 grid */}
      <Field label="Provider">
        <div className="settings-provider-grid">
          {LLM_PROVIDERS.map(p => {
            const active = currentProvider === p.value
            return (
              <button
                key={p.value}
                type="button"
                className={`settings-provider-cell${active ? ' active' : ''}`}
                aria-pressed={active}
                onClick={() =>
                  setDrafts(d => ({ ...d, llm_provider: p.value }))
                }
              >
                <div className="name">{p.label}</div>
                <div className="desc">{p.desc}</div>
              </button>
            )
          })}
        </div>
      </Field>

      {/* 模型名称 */}
      {modelKey && (
        <Field label="模型名称">
          <input
            className="form-input"
            style={{ width: '100%' }}
            value={draftOf(modelKey)}
            onChange={e => onChangeOf(modelKey)(e.target.value)}
            placeholder="claude-sonnet-4-6"
          />
        </Field>
      )}

      {/* API 端点 URL — only when Claude */}
      {baseUrlKey && currentProvider === 'claude' && (
        <Field label="API 端点 URL" hint="留空使用默认" error={fieldErrors.llm_base_url}>
          <input
            className="form-input"
            style={{ width: '100%', fontFamily: 'monospace' }}
            value={draftOf(baseUrlKey)}
            onChange={e => onChangeOf(baseUrlKey)(e.target.value)}
            placeholder="https://api.anthropic.com"
          />
        </Field>
      )}

      {/* API KEY */}
      {apiKeyKey && (
        <Field label="API KEY" error={fieldErrors.llm_api_key}>
          <div className="settings-key-row">
            <input
              className="form-input"
              type={showSecret ? 'text' : 'password'}
              value={draftOf(apiKeyKey)}
              onChange={e => onChangeOf(apiKeyKey)(e.target.value)}
              placeholder={
                apiKeyKey.is_set ? '已配置（输入新值覆盖）' : '请输入'
              }
            />
            <button
              type="button"
              className="btn-sec"
              onClick={onToggleSecret}
              style={{ padding: '6px 14px' }}
            >
              {showSecret ? '隐藏' : '显示'}
            </button>
          </div>
          {apiKeyKey.is_set && (
            <div className="settings-hint-ok">✓ 已配置 API Key</div>
          )}
          {providerChanged && (
            <div className="settings-hint-warn">
              ⚠ 切换 Provider 会清空 API KEY
            </div>
          )}
        </Field>
      )}
    </div>
  )
}

function PathsSection({
  pathSettings,
  drafts,
  setDrafts,
  fieldErrors,
}: {
  pathSettings: Setting[]
  drafts: Record<string, string>
  setDrafts: React.Dispatch<React.SetStateAction<Record<string, string>>>
  fieldErrors: Record<string, string>
}) {
  const draftOf = (s: Setting) => drafts[s.key] ?? s.value
  const onChangeOf = (s: Setting) => (v: string) =>
    setDrafts(d => ({ ...d, [s.key]: v }))

  return (
    <div className="card" style={{ padding: '28px 32px' }}>
      <div className="settings-h2" style={{ marginBottom: 16 }}>路径</div>
      {pathSettings.map(s => (
        <Field key={s.key} label={PATH_LABELS[s.key] ?? s.key} error={fieldErrors[s.key]}>
          <input
            className="form-input"
            style={{ width: '100%', fontFamily: 'monospace' }}
            value={draftOf(s)}
            onChange={e => onChangeOf(s)(e.target.value)}
          />
          {s.description && (
            <div className="settings-hint-info" style={{ marginTop: 6 }}>
              {s.description}
            </div>
          )}
        </Field>
      ))}
    </div>
  )
}

function VersionsSection({
  versionSettings,
}: {
  versionSettings: Setting[]
}) {
  return (
    <div className="card" style={{ padding: '28px 32px' }}>
      <div className="settings-h2" style={{ marginBottom: 16 }}>版本</div>
      {versionSettings.map(s => {
        const labelMap: Record<string, string> = {
          api_version: 'API 版本',
          worker_version: 'Worker 版本',
        }
        return (
          <Field key={s.key} label={labelMap[s.key] ?? s.key}>
            <input
              className="form-input"
              style={{ width: '100%', fontFamily: 'monospace' }}
              value={s.value}
              disabled
              readOnly
            />
          </Field>
        )
      })}
    </div>
  )
}

export default function Settings() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: () => api.getSettings(),
  })
  const [section, setSection] = useState<Section>('llm')
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [confirmingPath, setConfirmingPath] = useState(false)
  const [showSecret, setShowSecret] = useState(false)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})

  // Clear drafts that are no longer dirty (after save)
  useEffect(() => {
    if (!data) return
    setDrafts(d => {
      const next: Record<string, string> = {}
      for (const [k, v] of Object.entries(d)) {
        const cur = data.items.find(s => s.key === k)
        if (cur && cur.value !== v) next[k] = v
      }
      return next
    })
  }, [data])

  const update = useMutation({
    mutationFn: (items: Record<string, string>) => api.updateSettings(items),
    onSuccess: (resp) => {
      void qc.invalidateQueries({ queryKey: ['settings'] })
      setConfirmingPath(false)
      setFieldErrors({})
      const moved = resp.migration.filter(m => m.migrated)
      if (moved.length > 0) {
        pushToast({ kind: 'info', text: `已迁移 ${moved.length} 个目录，worker 重启后生效` })
      } else {
        pushToast({ kind: 'info', text: '已保存' })
      }
    },
    onError: (e) => {
      const msg = (e as Error).message
      pushToast({ kind: 'error', text: msg })
      // Heuristic: detect URL-validation errors and surface them inline
      if (msg.includes('llm_base_url') || msg.includes('不是合法 URL')) {
        setFieldErrors({ llm_base_url: msg })
      }
    },
  })

  const settings = data?.items ?? []
  const llmSettings     = settings.filter(s => s.key.startsWith('llm_'))
  const pathSettings    = settings.filter(s => PATH_KEYS.has(s.key))
  const versionSettings = settings.filter(s => s.key.endsWith('_version'))

  const hasChanges = Object.keys(drafts).length > 0
  const hasPathChange = Object.keys(drafts).some(k => PATH_KEYS.has(k))
  const savedProvider =
    llmSettings.find(s => s.key === 'llm_provider')?.value ?? 'mock'

  const submit = () => {
    if (hasPathChange && !confirmingPath) {
      setConfirmingPath(true)
      return
    }
    update.mutate(drafts)
  }

  return (
    <>
      <Topbar
        title="系统设置"
        subtitle="配置 LLM / 路径 / 版本"
        actions={
          <button
            className="btn-primary"
            disabled={!hasChanges || update.isPending}
            onClick={submit}
          >
            {update.isPending ? '保存中…' : '保存所有修改'}
          </button>
        }
      />
      <div className="content">
        <div className="settings-layout">
          <nav className="settings-nav" aria-label="设置分组">
            {(['llm', 'paths', 'versions'] as const).map(s => (
              <NavItem
                key={s}
                active={section === s}
                onClick={() => setSection(s)}
              >
                {SECTION_LABELS[s]}
              </NavItem>
            ))}
          </nav>

          <div className="settings-main">
            {confirmingPath && (
              <PathConfirmBanner
                onConfirm={submit}
                onCancel={() => setConfirmingPath(false)}
              />
            )}

            {isLoading && section === 'llm' && (
              <div className="card" style={{ padding: '28px 32px' }}>
                <div className="settings-h2" style={{ marginBottom: 16 }}>
                  大语言模型（LLM）
                </div>
                {[0, 1, 2, 3].map(i => (
                  <div
                    key={i}
                    style={{
                      height: 14,
                      background: 'var(--surface2)',
                      marginBottom: 24,
                      opacity: 0.6,
                    }}
                  />
                ))}
              </div>
            )}

            {!isLoading && section === 'llm' && (
              <LLMSection
                llmSettings={llmSettings}
                drafts={drafts}
                setDrafts={setDrafts}
                fieldErrors={fieldErrors}
                showSecret={showSecret}
                onToggleSecret={() => setShowSecret(s => !s)}
                savedProvider={savedProvider}
              />
            )}

            {section === 'paths' && (
              <PathsSection
                pathSettings={pathSettings}
                drafts={drafts}
                setDrafts={setDrafts}
                fieldErrors={fieldErrors}
              />
            )}

            {section === 'versions' && (
              <VersionsSection versionSettings={versionSettings} />
            )}
          </div>
        </div>
      </div>
    </>
  )
}
