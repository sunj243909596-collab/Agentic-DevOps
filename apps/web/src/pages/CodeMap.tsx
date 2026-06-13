import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import Topbar from '@/components/Topbar'
import { pushToast } from '@/components/Toast'
import ScopePicker from '@/components/code-map/ScopePicker'
import ModuleTree from '@/components/code-map/ModuleTree'
import ModuleCard from '@/components/code-map/ModuleCard'
import ScopeDiff from '@/components/code-map/ScopeDiff'
import ChangeList from '@/components/code-map/ChangeList'
import type { CodeMapModule, RegenJob } from '@/api/client'

type Tab = 'map' | 'diff' | 'changes'

const TAB_LABELS: Record<Tab, string> = {
  map: 'Map', diff: 'Diff', changes: 'Changes',
}

const POLL_INTERVAL_MS = 2000

type JobKind = 'regen' | 'repull-regen'

interface JobContext {
  kind: JobKind
  scope: string | null
  forceFull: boolean
}

export default function CodeMap() {
  const [tab, setTab] = useState<Tab>('map')
  const [activeScope, setActiveScope] = useState<string>('')
  const [activeModule, setActiveModule] = useState<CodeMapModule | null>(null)
  const [diffFrom, setDiffFrom] = useState<number>(0)
  const [diffTo, setDiffTo] = useState<number>(0)
  const [forceFull, setForceFull] = useState(false)

  // Live job state (the most recent regen attempt). When null, no job is in flight.
  const [job, setJob] = useState<RegenJob | null>(null)
  const [jobCtx, setJobCtx] = useState<JobContext | null>(null)
  const pollRef = useRef<number | null>(null)
  const qc = useQueryClient()

  const { data: idx, isLoading: idxLoading, error: idxError } = useQuery({
    queryKey: ['code-map-index'],
    queryFn: () => api.getCodeMapIndex(),
  })

  // Pick first non-empty scope as default
  useEffect(() => {
    if (!idx || activeScope) return
    const scopes = Object.keys(idx.scopes).filter(s => idx.scopes[s].module_count > 0)
    if (scopes.length > 0) setActiveScope(scopes[0])
  }, [idx, activeScope])

  const { data: scopeData, isLoading: scopeLoading } = useQuery({
    queryKey: ['code-map-scope', activeScope],
    queryFn: () => api.getCodeMapScope(activeScope),
    enabled: !!activeScope,
  })

  // Diff defaults
  useEffect(() => {
    if (!scopeData) return
    setDiffFrom(Math.max(1, scopeData.version - 1))
    setDiffTo(scopeData.version)
  }, [scopeData?.version, scopeData?.scope])

  const { data: diffData } = useQuery({
    queryKey: ['code-map-diff', activeScope, diffFrom, diffTo],
    queryFn: () => api.getCodeMapDiff(activeScope, diffFrom, diffTo),
    enabled: tab === 'diff' && !!activeScope && diffFrom > 0 && diffTo > diffFrom,
  })

  const { data: changesData } = useQuery({
    queryKey: ['code-map-changes'],
    queryFn: () => api.getCodeMapChanges('0000000000000000000000000000000000000000'),
    enabled: tab === 'changes',
  })

  // Stop polling when the job reaches a terminal state.
  useEffect(() => {
    if (!job) return
    if (job.status === 'succeeded' || job.status === 'failed') {
      if (pollRef.current !== null) {
        window.clearInterval(pollRef.current)
        pollRef.current = null
      }
    }
  }, [job?.status])

  // Cleanup on unmount.
  useEffect(() => () => {
    if (pollRef.current !== null) window.clearInterval(pollRef.current)
  }, [])

  // Shared polling kickoff. Called by both mutations on success.
  function startPolling(runId: string, ctx: JobContext) {
    setJobCtx(ctx)
    setJob({
      run_id: runId,
      status: 'queued',
      phase: ctx.kind === 'repull-regen' ? 'queued' : 'regenerating',
      scope: ctx.scope,
      force_full: ctx.forceFull,
      started_at: null,
      finished_at: null,
      scopes_processed: [],
      scopes_failed: [],
      error: null,
      pull_result: null,
    })

    if (pollRef.current !== null) window.clearInterval(pollRef.current)
    pollRef.current = window.setInterval(async () => {
      try {
        const next = await api.getRegenStatus(runId)
        setJob(next)
        if (next.status === 'succeeded' || next.status === 'failed') {
          qc.invalidateQueries({ queryKey: ['code-map-index'] })
          if (next.status === 'succeeded') {
            const scopeN = next.scopes_processed.length
            const prefix = ctx.kind === 'repull-regen' ? '已拉取并重新生成代码地图' : '代码地图已重新生成'
            pushToast({ kind: 'info', text: `${prefix}（${scopeN} 个 scope）` })
          } else {
            const msg = describeFailure(next)
            pushToast({ kind: 'error', text: msg })
          }
        }
      } catch (err) {
        // Polling failure is non-fatal — try again next tick.
        pushToast({ kind: 'error', text: `轮询失败：${(err as Error).message}` })
      }
    }, POLL_INTERVAL_MS)
  }

  const regenMutation = useMutation({
    mutationFn: (body: { scope?: string; force_full: boolean }) => api.postRegen(body),
    onSuccess: (data, variables) => {
      pushToast({ kind: 'info', text: '已提交代码地图重新生成任务' })
      startPolling(data.run_id, {
        kind: 'regen',
        scope: variables.scope ?? null,
        forceFull: variables.force_full,
      })
    },
    onError: (err: Error) => {
      pushToast({ kind: 'error', text: `提交重新生成失败：${err.message}` })
    },
  })

  const repullMutation = useMutation({
    mutationFn: (body: { scope?: string; force_full: boolean }) => api.postRepullRegen(body),
    onSuccess: (data, variables) => {
      pushToast({ kind: 'info', text: '已提交重拉+重生任务' })
      startPolling(data.run_id, {
        kind: 'repull-regen',
        scope: variables.scope ?? null,
        forceFull: variables.force_full,
      })
    },
    onError: (err: Error) => {
      pushToast({ kind: 'error', text: `提交重拉+重生失败：${err.message}` })
    },
  })

  function currentScopeArg(): string {
    return tab === 'map' && activeScope ? activeScope : ''
  }

  function handleRegen() {
    if (regenMutation.isPending || repullMutation.isPending) return
    const scopeArg = currentScopeArg()
    const scopeLabel = scopeArg || '全部'
    const mode = forceFull ? '强制全量' : '增量'
    const msg = `确认要${mode}重新生成代码地图（${scopeLabel}）？\n该操作会调用 LLM，可能耗时数分钟。`
    if (!window.confirm(msg)) return
    regenMutation.mutate({
      ...(scopeArg ? { scope: scopeArg } : {}),
      force_full: forceFull,
    })
  }

  function handleRepullRegen() {
    if (regenMutation.isPending || repullMutation.isPending) return
    const scopeArg = currentScopeArg()
    const scopeLabel = scopeArg || '全部'
    const msg =
      `确认要执行 "重拉+重生" 吗？\n` +
      `1. 先在仓库根目录执行 git pull（60s 超时）\n` +
      `2. 然后${forceFull ? '全量' : '增量'}重新生成代码地图（${scopeLabel}）\n\n` +
      `整个过程可能耗时数分钟。`
    if (!window.confirm(msg)) return
    repullMutation.mutate({
      ...(scopeArg ? { scope: scopeArg } : {}),
      force_full: forceFull,
    })
  }

  // Stale banner
  const staleScopes = idx ? Object.entries(idx.scopes).filter(([, v]) => v.stale) : []
  const hasStale = staleScopes.length > 0
  if (idxError) pushToast({ kind: 'error', text: '代码地图加载失败' })

  const isRunning = job?.status === 'queued' || job?.status === 'running'
  const isRepull = jobCtx?.kind === 'repull-regen'
  const lastError = job?.status === 'failed' ? describeFailure(job) : null
  const lastErrorIsPull = isRepull && job?.pull_result != null && job.pull_result.ok === false

  return (
    <>
      <Topbar
        title="代码地图"
        subtitle="仓库结构视图 · 变更影响面分析"
        actions={
          <label className="code-map-force-full">
            <input
              type="checkbox"
              checked={forceFull}
              onChange={e => setForceFull(e.target.checked)}
              disabled={isRunning}
            />
            强制全量
          </label>
        }
      />
      <div className="content">
        {isRunning && job && (
          <div className="code-map-regen-progress" role="status">
            {job.phase === 'pulling' ? (
              <>正在拉取代码仓库…{' '}
                <code>git pull</code>{' '}
                (60s 超时)
              </>
            ) : (
              <>正在{job.force_full ? '全量' : '增量'}重新生成代码地图
                （{job.scope ? `scope=${job.scope}` : '全部 scope'}）…{' '}
              </>
            )}
            <span>
              状态: <code>{job.phase}</code>
              {job.scopes_processed.length > 0 && (
                <> · 已完成 {job.scopes_processed.length}</>
              )}
              {job.scopes_failed.length > 0 && (
                <> · 失败 {job.scopes_failed.length}</>
              )}
            </span>
          </div>
        )}

        {hasStale && (
          <div className="code-map-stale-banner" role="alert">
            ⚠ 代码地图已过期（{staleScopes.map(([s, v]) => `${s} × ${v.stale_streak}`).join(', ')}），
            请用顶部「重拉+重生」或「重新生成」按钮重试
          </div>
        )}

        {!isRunning && lastError && lastErrorIsPull && (
          <div className="code-map-stale-banner code-map-stale-banner--pull-error" role="alert">
            <strong>git pull 失败：</strong>
            <code className="code-map-stale-banner__detail">{job?.pull_result?.error}</code>
            <button
              type="button"
              className="code-map-regen-button"
              style={{ marginLeft: 12 }}
              onClick={handleRepullRegen}
              data-testid="code-map-retry-pull"
            >
              再试一次
            </button>
          </div>
        )}

        <div className="code-map-tabs" role="tablist" aria-label="代码地图视图">
          {(Object.keys(TAB_LABELS) as Tab[]).map(t => (
            <button
              key={t}
              type="button"
              role="tab"
              aria-current={t === tab ? 'page' : undefined}
              className={`code-map-tab${t === tab ? ' active' : ''}`}
              onClick={() => setTab(t)}
            >
              {TAB_LABELS[t]}
            </button>
          ))}
          <button
            type="button"
            className="code-map-regen-button"
            style={{ marginLeft: 'auto' }}
            onClick={handleRegen}
            disabled={isRunning}
            data-testid="code-map-regen-button"
          >
            {isRunning ? '生成中…' : '重新生成'}
          </button>
          <button
            type="button"
            className="code-map-regen-button code-map-regen-button--repull"
            style={{ marginLeft: 8 }}
            onClick={handleRepullRegen}
            disabled={isRunning}
            data-testid="code-map-repull-button"
          >
            {isRunning && isRepull ? '重拉中…' : '重拉+重生'}
          </button>
        </div>

        {idxLoading && <div className="code-map-empty">加载中…</div>}

        {!idxLoading && tab === 'map' && (
          <div className="code-map-tab-body">
            <ScopePicker
              scopes={Object.keys(idx?.scopes ?? {}).filter(s => (idx?.scopes[s].module_count ?? 0) > 0)}
              active={activeScope}
              onChange={setActiveScope}
            />
            <div className="code-map-map-layout">
              <div className="code-map-map-left">
                {scopeLoading ? <div className="code-map-empty">加载中…</div> : (
                  <ModuleTree
                    modules={scopeData?.modules ?? []}
                    activeId={activeModule?.id ?? null}
                    onSelect={setActiveModule}
                  />
                )}
              </div>
              <div className="code-map-map-right">
                {activeModule ? <ModuleCard m={activeModule} /> : (
                  <div className="code-map-empty">← 选择左侧模块查看详情</div>
                )}
              </div>
            </div>
          </div>
        )}

        {!idxLoading && tab === 'diff' && (
          <div className="code-map-tab-body">
            {activeScope && (
              <div className="code-map-diff-controls">
                <span>scope: <code>{activeScope}</code></span>
                <span>from:</span>
                <input type="number" min={1} value={diffFrom} onChange={e => setDiffFrom(Number(e.target.value))} />
                <span>to:</span>
                <input type="number" min={1} value={diffTo} onChange={e => setDiffTo(Number(e.target.value))} />
              </div>
            )}
            {diffData ? <ScopeDiff diff={diffData} /> : <div className="code-map-empty">无 diff 数据</div>}
          </div>
        )}

        {!idxLoading && tab === 'changes' && (
          <div className="code-map-tab-body">
            {changesData ? (
              <ChangeList commits={changesData.commits} files={changesData.files} />
            ) : <div className="code-map-empty">加载中…</div>}
          </div>
        )}
      </div>
    </>
  )
}

function describeFailure(job: RegenJob): string {
  if (job.pull_result && !job.pull_result.ok) {
    const e = job.pull_result.error ?? 'unknown'
    return `git pull 失败：${e.slice(0, 120)}`
  }
  if (job.scopes_failed.length > 0) {
    const first = job.scopes_failed[0]
    return `重新生成失败：${first.scope}: ${first.error.slice(0, 120)}`
  }
  return job.error ? `重新生成失败：${job.error.slice(0, 120)}` : '重新生成失败'
}
