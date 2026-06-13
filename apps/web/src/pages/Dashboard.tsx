import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, isInProgress, relativeTime, duration, shortSha } from '@/api/client'
import { StatusBadge, TriggerBadge } from '@/components/Badge'
import Topbar from '@/components/Topbar'
import TriggerModal from '@/components/TriggerModal'
import type { AnalysisRun } from '@/api/client'

function GradeTag({ score }: { score: number | null }) {
  if (score === null) return <span style={{ color: 'var(--subtle)' }}>—</span>
  const grade = score >= 90 ? 'A' : score >= 75 ? 'B' : score >= 60 ? 'C' : 'F'
  const cls = `grade-${grade.toLowerCase()}`
  const scCls = score >= 90 ? 'score-a' : score >= 75 ? 'score-b' : score >= 60 ? 'score-c' : 'score-f'
  return (
    <>
      <span className={scCls} style={{ fontWeight: 800 }}>{Math.round(score)}</span>
      <span className={`grade-tag ${cls}`}>{grade}</span>
    </>
  )
}

function RunRow({ run }: { run: AnalysisRun }) {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [confirming, setConfirming] = useState(false)
  const del = useMutation({
    mutationFn: () => api.deleteRun(run.run_id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['runs'] }),
  })

  return (
    <tr className="row-clickable" onClick={() => navigate(`/runs/${run.run_id}`)}>
      <td>
        <div style={{ fontSize: 13, fontWeight: 600 }}>{run.repository_full_name}</div>
        <div style={{ fontSize: 11, color: 'var(--mid)', fontFamily: 'monospace', marginTop: 2 }}>
          {run.target_branch} · {shortSha(run.target_sha)}
        </div>
      </td>
      <td><TriggerBadge type={run.trigger_type} /></td>
      <td><StatusBadge status={run.status} /></td>
      <td>
        {run.status === 'completed'
          ? <RunScoreCell runId={run.run_id} />
          : <span style={{ color: 'var(--subtle)' }}>—</span>}
      </td>
      <td style={{ fontSize: 12, color: 'var(--mid)' }}>
        {duration(run.started_at, run.completed_at)}
      </td>
      <td style={{ fontSize: 12, color: 'var(--subtle)' }}>{relativeTime(run.started_at)}</td>
      <td onClick={e => e.stopPropagation()} style={{ textAlign: 'right' }}>
        {confirming ? (
          <span style={{ display: 'inline-flex', gap: 4 }}>
            <button
              className="btn-sec"
              style={{ padding: '2px 8px', fontSize: 11, color: 'var(--clay)', borderColor: 'var(--clay)' }}
              onClick={() => del.mutate()}
              disabled={del.isPending}
            >
              {del.isPending ? '…' : '确认删除'}
            </button>
            <button
              className="btn-sec"
              style={{ padding: '2px 8px', fontSize: 11 }}
              onClick={() => setConfirming(false)}
            >
              取消
            </button>
          </span>
        ) : (
          <button
            className="btn-sec"
            style={{ padding: '2px 8px', fontSize: 11, opacity: 0.5 }}
            onClick={() => setConfirming(true)}
            title="删除此运行（级联清理）"
          >
            <svg width="11" height="11" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path d="M3 6h18M8 6V4a1 1 0 011-1h6a1 1 0 011 1v2m3 0v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6h14z" strokeLinecap="round" />
            </svg>
          </button>
        )}
      </td>
    </tr>
  )
}

function RunScoreCell({ runId }: { runId: string }) {
  const { data } = useQuery({
    queryKey: ['score', runId],
    queryFn: () => api.getScore(runId),
    retry: false,
  })
  return <GradeTag score={data?.final_score ?? null} />
}

export default function Dashboard() {
  const [showModal, setShowModal] = useState(false)
  const [filter, setFilter] = useState<string>('')

  const { data, isLoading, error } = useQuery({
    queryKey: ['runs'],
    queryFn: () => api.listRuns(50),
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? []
      return items.some(r => isInProgress(r.status)) ? 5000 : false
    },
  })

  const runs = data?.items ?? []
  const filtered = filter
    ? runs.filter(r => r.repository_full_name.toLowerCase().includes(filter.toLowerCase()))
    : runs

  // Aggregate stats
  const total = runs.length
  const pending = runs.filter(r => r.status !== 'completed' && r.status !== 'failed').length

  return (
    <>
      <Topbar
        title="控制台"
        actions={
          <>
            <div className="search-wrap">
              <svg className="search-icon" width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
              <input className="search-input" placeholder="搜索仓库…" value={filter} onChange={e => setFilter(e.target.value)} />
            </div>
            <button className="btn-primary" onClick={() => setShowModal(true)}>
              <svg width="12" height="12" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                <line x1="12" y1="5" x2="12" y2="19" strokeLinecap="round" />
                <line x1="5" y1="12" x2="19" y2="12" strokeLinecap="round" />
              </svg>
              新建运行
            </button>
          </>
        }
      />

      <div className="content">
        {/* Stats */}
        <div className="stat-grid">
          <div className="stat-card">
            <div className="stat-label">总运行次数</div>
            <div className="stat-value">{total}</div>
            <div className="stat-sub">历史全部记录</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">进行中</div>
            <div className="stat-value" style={{ color: pending > 0 ? 'var(--blue)' : undefined }}>{pending}</div>
            <div className="stat-sub">实时刷新</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">已完成</div>
            <div className="stat-value score-a">{runs.filter(r => r.status === 'completed').length}</div>
            <div className="stat-sub" />
          </div>
          <div className="stat-card">
            <div className="stat-label">运行失败</div>
            <div className="stat-value score-f">{runs.filter(r => r.status === 'failed').length}</div>
            <div className="stat-sub" />
          </div>
        </div>

        {/* Runs table */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">最近运行记录</span>
          </div>

          {isLoading && <div className="empty-state">加载中…</div>}
          {error && <div className="error-msg">{(error as Error).message}</div>}

          {!isLoading && !error && (
            <>
              <table>
                <thead>
                  <tr>
                    <th style={{ width: '28%' }}>仓库 / 分支</th>
                    <th style={{ width: '10%' }}>触发方式</th>
                    <th style={{ width: '14%' }}>状态</th>
                    <th style={{ width: '12%' }}>分数</th>
                    <th style={{ width: '10%' }}>耗时</th>
                    <th style={{ width: '18%' }}>触发时间</th>
                    <th style={{ width: '8%' }} />
                  </tr>
                </thead>
                <tbody>
                  {filtered.map(r => <RunRow key={r.run_id} run={r} />)}
                </tbody>
              </table>
              {filtered.length === 0 && (
                <div className="empty-state">
                  {filter ? '未找到匹配的记录' : '暂无运行记录，点击「新建运行」开始'}
                </div>
              )}
              <div className="table-footer">
                <span className="table-footer-text">显示 {filtered.length} / {total} 条记录</span>
              </div>
            </>
          )}
        </div>
      </div>

      {showModal && <TriggerModal onClose={() => setShowModal(false)} />}
    </>
  )
}
