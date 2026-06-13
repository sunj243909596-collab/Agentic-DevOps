import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api, isInProgress, relativeTime, shortSha, duration, categoryLabel, severityLabel, sevClass } from '@/api/client'
import { StatusBadge, TriggerBadge } from '@/components/Badge'
import ScoreRing from '@/components/ScoreRing'
import Pipeline from '@/components/Pipeline'
import Topbar from '@/components/Topbar'
import { pushToast } from '@/components/Toast'
import { useModalLock } from '@/hooks/useModalLock'
import type { Finding, ChangeUnit, RunStatus } from '@/api/client'

// ── Run-level constants ──────────────────────────────────────────────────────

/** Statuses for which the front-end offers a "重新分析" button.
 *  Mirrors RETRYABLE_STATUSES in apps/api-gateway/api_gateway/routers/analysis_runs.py */
const RETRYABLE_STATUSES: ReadonlySet<RunStatus> = new Set([
  'failed',
  'partial_analysis',
  'rejected',
])

// ── Finding card ─────────────────────────────────────────────────────────────

const STATUS_BUTTONS: { value: 'accepted' | 'rejected' | 'disputed' | 'resolved'; label: string }[] = [
  { value: 'accepted',  label: '已确认' },
  { value: 'rejected',  label: '已忽略' },
  { value: 'disputed',  label: '有异议' },
  { value: 'resolved',  label: '已解决' },
]

function FindingCard({ f }: { f: Finding }) {
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<{ status: 'accepted' | 'rejected' | 'disputed' | 'resolved'; reason: string } | null>(null)
  const qc = useQueryClient()
  const closeEditing = () => setEditing(null)
  useModalLock(editing !== null, closeEditing)
  const reasonRef = useRef<HTMLTextAreaElement>(null)
  useEffect(() => { if (editing) reasonRef.current?.focus() }, [editing])

  const mutation = useMutation({
    mutationFn: ({ status, reason }: { status: 'accepted' | 'rejected' | 'disputed' | 'resolved'; reason: string }) =>
      api.updateFindingStatus(f.finding_id, { status, reason }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['findings', f.run_id] })
      setEditing(null)
    },
  })

  const pct = Math.round(f.confidence * 100)
  const fillColor =
    f.severity === 'critical' ? 'var(--red)' :
    f.severity === 'high'     ? 'var(--clay)' :
    f.severity === 'medium'   ? 'var(--amber)' : 'var(--blue)'

  return (
    <div className="finding-card">
      <div className="finding-top" onClick={() => setOpen(o => !o)}>
        <span className={`finding-sev-badge ${sevClass(f.severity)}`}>{severityLabel(f.severity)}</span>
        <span className="finding-cat">{categoryLabel(f.category)}</span>
        <div style={{ flex: 1 }}>
          <div className="finding-title">{f.observation.slice(0, 80)}</div>
          <div className="finding-file">{f.file_path} : {f.start_line}–{f.end_line}</div>
        </div>
        <div className="finding-meta">
          <div className="conf-bar-wrap">
            <div className="conf-track">
              <div className="conf-fill" style={{ width: `${pct}%`, background: fillColor }} />
            </div>
            <span className="conf-num">{f.confidence.toFixed(2)}</span>
          </div>
          <div style={{ display: 'flex', gap: 4 }} onClick={e => e.stopPropagation()}>
            {STATUS_BUTTONS.map(b =>
              f.status === b.value ? (
                <span key={b.value} className="badge badge-done" style={{ fontSize: 10 }}>{b.label}</span>
              ) : (
                <button
                  key={b.value}
                  className="btn-sec"
                  style={{ padding: '2px 8px', fontSize: 11 }}
                  onClick={() => setEditing({ status: b.value, reason: '' })}
                >
                  {b.label}
                </button>
              )
            )}
          </div>
          <svg className={`chevron ${open ? 'open' : ''}`} width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </div>
      </div>

      {open && (
        <div className="finding-body">
          <div className="finding-grid">
            <div>
              <div className="finding-section-label">观测</div>
              <p className="finding-text">{f.observation}</p>
            </div>
            <div>
              <div className="finding-section-label">影响</div>
              <p className="finding-text">{f.impact}</p>
            </div>
            <div>
              <div className="finding-section-label">建议</div>
              <p className="finding-text">{f.recommendation}</p>
            </div>
            <div>
              <div className="finding-section-label">验证方式</div>
              <p className="finding-text">{f.verification}</p>
            </div>
          </div>
          {f.evidence_refs.length > 0 && (
            <div className="evidence-row">
              <span className="evidence-label">证据</span>
              {f.evidence_refs.map(r => (
                <span key={r} className="evidence-val">{r}</span>
              ))}
            </div>
          )}
        </div>
      )}

      {editing && (
        <div
          className="modal-bg"
          role="dialog"
          aria-modal="true"
          onClick={e => e.stopPropagation()}
        >
          <div className="modal-box" style={{ maxWidth: 440, position: 'relative' }}>
            <button
              type="button"
              className="modal-close"
              onClick={closeEditing}
              aria-label="关闭"
              title="关闭 (ESC)"
            >
              ×
            </button>
            <div className="modal-title">变更问题状态</div>
            <div className="form-row">
              <label className="form-label">目标状态</label>
              <div style={{ fontSize: 13, fontWeight: 600 }}>
                {STATUS_BUTTONS.find(b => b.value === editing.status)?.label}
              </div>
            </div>
            <div className="form-row">
              <label className="form-label">理由 <span style={{ color: 'var(--clay)' }}>*</span></label>
              <textarea
                ref={reasonRef}
                className="form-input"
                rows={3}
                value={editing.reason}
                onChange={e => setEditing({ ...editing, reason: e.target.value })}
                placeholder="为什么接受/拒绝这条 Finding？将记录在审计日志中。"
              />
            </div>
            {mutation.isError && (
              <div className="error-msg" style={{ marginBottom: 12 }}>
                {(mutation.error as Error).message}
              </div>
            )}
            <div className="modal-footer">
              <button className="btn-sec" onClick={() => setEditing(null)}>取消</button>
              <button
                className="btn-primary"
                disabled={!editing.reason.trim() || mutation.isPending}
                onClick={() => mutation.mutate(editing)}
              >
                {mutation.isPending ? '提交中…' : '确认'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Change unit row ───────────────────────────────────────────────────────────

function FileRow({ cu }: { cu: ChangeUnit }) {
  const [open, setOpen] = useState(false)
  const { data: hunk, isLoading } = useQuery({
    queryKey: ['hunk', cu.change_unit_id],
    queryFn: () => api.getHunk(cu.change_unit_id),
    enabled: open && !!cu.hunks_ref,
  })
  const typeMap: Record<string, string> = { added: '新增', modified: '修改', deleted: '删除', renamed: '重命名' }
  const clsMap: Record<string, string> = { added: 'ft-a', modified: 'ft-m', deleted: 'ft-d', renamed: 'ft-m' }
  return (
    <div className="file-row-wrap">
      <div className="file-row" onClick={() => setOpen(o => !o)} style={{ cursor: 'pointer' }}>
        <svg width="10" height="10" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}
             style={{ color: 'var(--subtle)', transition: 'transform 0.15s', transform: open ? 'rotate(90deg)' : 'none', flexShrink: 0 }}>
          <polyline points="9 18 15 12 9 6" />
        </svg>
        <span className={`file-type ${clsMap[cu.change_type] ?? 'ft-m'}`}>{typeMap[cu.change_type] ?? cu.change_type}</span>
        <span className="file-name">{cu.file_path}</span>
        {cu.risk_tags.includes('high_risk') && <span className="file-tag ft-risk">高风险</span>}
        {cu.is_test_file && <span className="file-tag ft-test">测试文件</span>}
        <span className="fs-11 text-subtle" style={{ marginLeft: 'auto' }}>{cu.language}</span>
        <span className="fs-11 mono" style={{ marginLeft: 16 }}>
          <span className="text-olive">+{cu.added_lines}</span>{' '}
          <span className="text-red">−{cu.deleted_lines}</span>
        </span>
      </div>
      {open && (
        <div style={{ margin: '4px 0 12px 22px', padding: 12, background: '#0d0d0c', borderRadius: 4, fontFamily: 'monospace', fontSize: 11, color: '#e9e7de', overflowX: 'auto', maxHeight: 360, overflowY: 'auto', whiteSpace: 'pre' }}>
          {isLoading ? '加载 diff…' : hunk || '（无 diff 内容）'}
        </div>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

type Tab = 'findings' | 'files' | 'report'

export default function RunDetail() {
  const { runId } = useParams<{ runId: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [tab, setTab] = useState<Tab>('findings')

  const retryMutation = useMutation({
    mutationFn: (id: string) => api.retryRun(id),
    onSuccess: (newRun) => {
      pushToast({ kind: 'info', text: `已创建重试运行 #${shortSha(newRun.run_id)}，正在跳转…` })
      // Invalidate list of runs so the new entry shows up.
      void qc.invalidateQueries({ queryKey: ['runs'] })
      // Navigate to the new run — its page will poll until done.
      navigate(`/runs/${newRun.run_id}`)
    },
    onError: (err: Error) => {
      pushToast({ kind: 'error', text: `重试失败：${err.message}` })
    },
  })

  function handleRetry() {
    if (!run || retryMutation.isPending) return
    const msg =
      `确认要重新分析这次运行吗？\n\n` +
      `仓库：${run.repository_full_name}\n` +
      `分支：${run.target_branch}\n` +
      `当前状态：${run.status}\n\n` +
      `将创建一条新运行记录，重新拉取代码并跑完整分析流水线。\n` +
      `原运行的发现/评分/报告会保留在新运行之外。`
    if (!window.confirm(msg)) return
    retryMutation.mutate(run.run_id)
  }

  const { data: run, isLoading: runLoading } = useQuery({
    queryKey: ['run', runId],
    queryFn: () => api.getRun(runId!),
    enabled: !!runId,
    refetchInterval: (q) => {
      const r = q.state.data
      return r && isInProgress(r.status) ? 4000 : false
    },
  })

  const { data: findingsData } = useQuery({
    queryKey: ['findings', runId],
    queryFn: () => api.getFindings(runId!),
    enabled: !!runId && run?.status === 'completed',
  })

  const { data: score } = useQuery({
    queryKey: ['score', runId],
    queryFn: () => api.getScore(runId!),
    enabled: !!runId && run?.status === 'completed',
    retry: false,
  })

  const { data: changeUnits } = useQuery({
    queryKey: ['change-units', runId],
    queryFn: () => api.getChangeUnits(runId!),
    enabled: !!runId,
  })

  const { data: report } = useQuery({
    queryKey: ['report', runId],
    queryFn: () => api.getReport(runId!),
    enabled: !!runId && run?.status === 'completed',
    retry: false,
  })

  const { data: reportText } = useQuery({
    queryKey: ['report-text', runId],
    queryFn: () => api.getReportText(runId!),
    enabled: !!runId && run?.status === 'completed' && tab === 'report',
    retry: false,
  })

  if (runLoading) return (
    <>
      <Topbar title="运行详情" showBack />
      <div className="content"><div className="empty-state">加载中…</div></div>
    </>
  )

  if (!run) return (
    <>
      <Topbar title="运行详情" showBack />
      <div className="content"><div className="error-msg">运行记录未找到</div></div>
    </>
  )

  const findings = findingsData?.items ?? []
  const units    = changeUnits?.items ?? []

  const critCount = findings.filter(f => f.severity === 'critical').length
  const highCount = findings.filter(f => f.severity === 'high').length
  const canRetry = RETRYABLE_STATUSES.has(run.status)

  return (
    <>
      <Topbar
        title="运行详情"
        subtitle={`/ ${run.repository_full_name}`}
        showBack
        actions={
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {canRetry && (
              <button
                type="button"
                className="btn-primary"
                onClick={handleRetry}
                disabled={retryMutation.isPending}
                data-testid="run-retry-button"
                title={`当前状态：${run.status}。点击创建一条新的重试运行。`}
              >
                {retryMutation.isPending ? '提交中…' : '↻ 重新分析'}
              </button>
            )}
            <button className="btn-sec">下载报告</button>
          </div>
        }
      />

      <div className="content">
        {/* Run header */}
        <div className="run-header" style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
              <span className="run-h1">{run.repository_full_name}</span>
              <span style={{ fontSize: 14, color: 'var(--mid)' }}>/</span>
              <span style={{ fontSize: 13, color: 'var(--mid)', fontFamily: 'monospace' }}>{run.target_branch}</span>
              <StatusBadge status={run.status} />
            </div>
            <div className="run-meta">
              <span><TriggerBadge type={run.trigger_type} /></span>
              <span>{run.policy_version} · {run.scoring_version}</span>
              <span>{relativeTime(run.started_at)}</span>
              <span>{duration(run.started_at, run.completed_at)}</span>
              {run.trigger_id && (
                <span
                  className="run-meta-retry"
                  title={`由事件 ${run.trigger_id} 触发（事件类型见后端 trigger_events.event_type）`}
                  data-testid="run-retry-badge"
                >
                  ↻ 手动重试 · 事件 <code>{shortSha(run.trigger_id)}</code>
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Failure reason banner — shown when the run ended in a terminal
            failure status and the pipeline wrote a diagnostic message. */}
        {run.failure_reason && (
          <div
            className="run-failure-banner"
            role="alert"
            data-testid="run-failure-banner"
          >
            <strong>失败原因：</strong>
            <code className="run-failure-banner__detail">
              {run.failure_reason}
            </code>
          </div>
        )}

        {/* Score + Pipeline */}
        <div className="detail-grid">
          {score
            ? <ScoreRing score={score} />
            : <div className="score-card" style={{ justifyContent: 'center' }}>
                <span style={{ fontSize: 12, color: 'rgba(255,255,255,.3)' }}>
                  {isInProgress(run.status) ? '评分计算中…' : '暂无评分'}
                </span>
              </div>
          }
          <Pipeline run={run} />
        </div>

        {/* Tabs */}
        <div className="tab-bar">
          <button className={`tab-btn ${tab === 'findings' ? 'active' : ''}`} onClick={() => setTab('findings')}>
            发现问题
            {findings.length > 0 && (
              <span className={`tab-count ${critCount + highCount > 0 ? 'tab-count-err' : 'tab-count-n'}`}>
                {findings.length}
              </span>
            )}
          </button>
          <button className={`tab-btn ${tab === 'files' ? 'active' : ''}`} onClick={() => setTab('files')}>
            变更文件
            {units.length > 0 && <span className="tab-count tab-count-n">{units.length}</span>}
          </button>
          <button className={`tab-btn ${tab === 'report' ? 'active' : ''}`} onClick={() => setTab('report')}>
            报告预览
          </button>
        </div>

        {/* Findings tab */}
        {tab === 'findings' && (
          <div className="tab-pane">
            {findings.length === 0
              ? <div className="empty-state">{isInProgress(run.status) ? 'Agent 审查中…' : '未发现问题'}</div>
              : findings.map(f => <FindingCard key={f.finding_id} f={f} />)
            }
          </div>
        )}

        {/* Files tab */}
        {tab === 'files' && (
          <div className="tab-pane">
            {units.length === 0
              ? <div className="empty-state">暂无变更文件</div>
              : (
                <>
                  <div className="fs-12 text-mid" style={{ marginBottom: 14 }}>
                    {units.length} 个文件变更 ·{' '}
                    <span className="text-olive">+{units.reduce((s, u) => s + u.added_lines, 0)}</span>{' '}
                    <span className="text-red">−{units.reduce((s, u) => s + u.deleted_lines, 0)}</span>
                  </div>
                  {units.map(cu => <FileRow key={cu.change_unit_id} cu={cu} />)}
                </>
              )
            }
          </div>
        )}

        {/* Report tab */}
        {tab === 'report' && (
          <div className="tab-pane">
            {!report
              ? <div className="empty-state">{isInProgress(run.status) ? '报告生成中…' : '暂无报告'}</div>
              : (
                <div className="report-preview">
                  <div className="rpt-h1">DevManager 代码审查报告</div>
                  <div style={{ fontSize: 11, color: 'var(--subtle)', margin: '4px 0 16px' }}>
                    生成时间：{relativeTime(report.generated_at)} · 影子模式 / 只读
                  </div>
                  <dl>
                    {([
                      ['代码仓库', run.repository_full_name],
                      ['分支', run.target_branch],
                      ['目标提交', shortSha(run.target_sha)],
                      ['最终得分', score ? `${Math.round(score.final_score ?? 0)} / 100 — ${score.grade} 级` : '—'],
                      ['置信度', score ? String(score.confidence?.toFixed(2)) : '—'],
                    ] as [string, string][]).map(([k, v]) => (
                      <div key={k} style={{ display: 'grid', gridTemplateColumns: '120px 1fr', gap: 4, marginBottom: 3 }}>
                        <dt style={{ fontSize: 11, color: 'var(--subtle)' }}>{k}</dt>
                        <dd style={{ fontSize: 11, fontWeight: 600 }}>{v}</dd>
                      </div>
                    ))}
                  </dl>
                  {score && (
                    <div className="rpt-section">
                      <div className="rpt-h2">问题汇总</div>
                      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                        {(['critical','high','medium','low'] as const).map(sev => {
                          const cnt = findings.filter(f => f.severity === sev).length
                          if (!cnt) return null
                          return (
                            <span key={sev} className={`badge badge-${sev === 'critical' ? 'fail' : sev === 'high' ? 'push' : 'pr'}`}>
                              {severityLabel(sev)}：{cnt}
                            </span>
                          )
                        })}
                      </div>
                    </div>
                  )}
                  <div className="rpt-warning">
                    ⚠ 本次为影子模式只读分析，不会自动创建工单。请人工审阅后决定是否跟进。
                  </div>
                  {typeof reportText === 'string' && reportText.length > 0 && (
                    <>
                      <div className="rpt-h2" style={{ marginTop: 20 }}>完整报告内容</div>
                      <pre style={{ background: '#0d0d0c', color: '#e9e7de', padding: 16, borderRadius: 4, fontSize: 11, whiteSpace: 'pre-wrap', maxHeight: 600, overflow: 'auto', fontFamily: 'SF Mono, Cascadia Code, monospace' }}>
                        {reportText}
                      </pre>
                    </>
                  )}
                </div>
              )
            }
          </div>
        )}
      </div>
    </>
  )
}
