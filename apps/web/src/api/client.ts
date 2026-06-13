// All API types mirror the backend Pydantic schemas exactly.

import { pushToast } from '@/components/Toast'

export type RunStatus =
  | 'trigger_received'
  | 'ingestion_started'
  | 'ingestion_completed'
  | 'agent_review_started'
  | 'agent_review_completed'
  | 'scoring_started'
  | 'scoring_completed'
  | 'report_generation_started'
  | 'completed'
  | 'partial_analysis'
  | 'failed'
  | 'rejected'

export type TriggerType = 'manual' | 'github_push' | 'github_pull_request'
export type Severity = 'critical' | 'high' | 'medium' | 'low' | 'info'
export type FindingStatus = 'open' | 'accepted' | 'rejected' | 'disputed' | 'resolved'
export type ChangeType = 'added' | 'modified' | 'deleted' | 'renamed'

export interface AnalysisRun {
  run_id: string
  repository_id: string
  repository_full_name: string
  trigger_id: string | null
  trigger_type: TriggerType
  target_branch: string
  baseline_sha: string
  target_sha: string
  merge_base_sha: string | null
  history_rewrite_detected: boolean
  status: RunStatus
  policy_version: string
  scoring_version: string
  agent_versions: Record<string, string>
  failure_reason: string | null
  started_at: string
  completed_at: string | null
}

export interface ChangeUnit {
  change_unit_id: string
  run_id: string
  repository_full_name: string
  file_path: string
  previous_file_path: string | null
  change_type: ChangeType
  language: string
  owner: string | null
  added_lines: number
  deleted_lines: number
  is_binary: boolean
  is_generated: boolean
  is_vendor: boolean
  is_test_file: boolean
  risk_tags: string[]
  baseline_sha: string
  target_sha: string
  hunks_ref: string | null
}

export interface Finding {
  finding_id: string
  run_id: string
  category: string
  severity: Severity
  confidence: number
  repository_full_name: string
  commit_sha: string
  file_path: string
  start_line: number
  end_line: number
  observation: string
  impact: string
  recommendation: string
  verification: string
  evidence_refs: string[]
  related_knowledge_refs: string[]
  status: FindingStatus
  dedupe_key: string | null
}

export interface Score {
  score_id: string
  run_id: string
  scoring_version: string
  status: string
  final_score: number | null
  grade: string | null
  confidence: number | null
  deductions: Array<{ severity: Severity; count: number; delta: number; capped: boolean }>
  caps: string[]
  limitations: string[]
  created_at: string
}

export interface Report {
  report_id: string
  run_id: string
  status: string
  content_reference: string
  generated_at: string
}

export interface Repository {
  repository_id: string
  provider: string
  full_name: string
  clone_url: string | null
  status: string
  created_at: string
}

export interface AuditEvent {
  event_id: string
  actor: string
  workflow_id: string | null
  event_type: string
  tool: string | null
  input_ref: string | null
  output_ref: string | null
  model_version: string | null
  prompt_version: string | null
  policy_version: string | null
  policy_decision: string | null
  event_metadata: Record<string, unknown>
  event_timestamp: string
  inserted_at: string
}

export interface Setting {
  key: string
  value: string
  description: string | null
  updated_at: string
  updated_by: string | null
  is_secret: boolean
  is_set: boolean
}

// ── Code map types ──────────────────────────────────────────────────────────

export type ModuleKind = 'frontend-spa' | 'backend' | 'agent' | 'lib' | 'docs' | 'test'

export interface CodeMapModule {
  id: string
  path: string
  name: string
  kind: ModuleKind
  responsibility: string
  entry_points: string[]
  key_files: string[]
}

export interface CodeMapEdge {
  from: string
  to: string
  via: string | null
}

export interface CodeMapScope {
  scope: string
  version: number
  generated_at: string
  head_sha: string
  generator: string
  stale: boolean
  stale_reason: string | null
  modules: CodeMapModule[]
  edges: CodeMapEdge[]
}

export interface CodeMapIndex {
  last_pull_at: string | null
  last_error: string | null
  scopes: Record<string, {
    version: number
    head_sha: string
    stale: boolean
    stale_reason: string | null
    stale_streak: number
    module_count: number
  }>
}

export interface LineContext {
  module_id: string | null
  scope: string | null
  responsibility: string | null
  kind: ModuleKind | null
}

export interface CodeMapDiff {
  scope: string
  from_version: number
  to_version: number
  added_modules: CodeMapModule[]
  removed_modules: CodeMapModule[]
  changed_modules: Array<{
    id: string
    fields_changed: string[]
    from: CodeMapModule
    to: CodeMapModule
  }>
  added_edges: CodeMapEdge[]
  removed_edges: CodeMapEdge[]
}

export interface CodeMapChange {
  commit: string
  path: string
  status: string  // 'A' | 'M' | 'D' | ...
  module: LineContext | null
}

export interface RegenRequest {
  scope?: string
  force_full?: boolean
}

export interface PullResult {
  ok: boolean
  prev_head: string
  new_head: string
  error: string | null
}

export interface RegenJob {
  run_id: string
  status: 'queued' | 'running' | 'succeeded' | 'failed'
  phase: 'queued' | 'pulling' | 'regenerating' | 'done'
  scope: string | null
  force_full: boolean
  started_at: string | null
  finished_at: string | null
  scopes_processed: string[]
  scopes_failed: Array<{ scope: string; error: string }>
  error: string | null
  /** Non-null only for /repull-regen jobs; null for plain /regen jobs. */
  pull_result: PullResult | null
}

export interface CreateRunInput {
  repository: string
  target_branch: string
  clone_url?: string
  target_sha?: string
  access_token?: string
  provider?: 'github' | 'gitlab' | 'other'
}

export interface FindingStatusUpdate {
  status: 'accepted' | 'rejected' | 'disputed' | 'resolved'
  reason: string
}

// ── HTTP client ──────────────────────────────────────────────────────────────

const BASE   = import.meta.env.VITE_API_BASE_URL   ?? ''
const SECRET = import.meta.env.VITE_API_SECRET_KEY ?? ''

function authHeaders(): Record<string, string> {
  if (!SECRET) return {}
  return { Authorization: `Bearer ${SECRET}` }
}

async function requestText(path: string, opts: RequestInit = {}): Promise<string> {
  const res = await fetch(`${BASE}${path}`, {
    ...opts,
    headers: {
      ...authHeaders(),
      ...opts.headers,
    },
  })
  if (!res.ok) {
    let msg = res.statusText
    try {
      const body = await res.json()
      msg = (body && (body.detail || body.message)) || msg
    } catch {
      /* not JSON */
    }
    throw new Error(`${res.status} ${msg}`)
  }
  return res.text()
}

async function request<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(),
      ...opts.headers,
    },
  })
  if (!res.ok) {
    let msg = res.statusText
    try {
      const body = await res.json()
      msg = (body && (body.detail || body.message)) || msg
    } catch {
      /* not JSON — keep statusText */
    }
    if (res.status === 401 || res.status === 403) {
      pushToast({ kind: 'error', text: `鉴权失败 (${res.status})：${msg}` })
    } else if (res.status >= 500) {
      pushToast({ kind: 'error', text: `服务异常 (${res.status})：${msg}` })
    } else if (res.status >= 400) {
      // 4xx business errors: keep quiet (mutations can handle), but still throw
    }
    throw new Error(`${res.status} ${msg}`)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

// ── API methods ──────────────────────────────────────────────────────────────

export const api = {
  // Runs
  listRuns: (limit = 50, offset = 0) =>
    request<{ items: AnalysisRun[] }>(`/v1/analysis-runs?limit=${limit}&offset=${offset}`),

  getRun: (runId: string) =>
    request<AnalysisRun>(`/v1/analysis-runs/${runId}`),

  createRun: (body: CreateRunInput) =>
    request<AnalysisRun>('/v1/analysis-runs', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  deleteRun: (runId: string) =>
    request<void>(`/v1/analysis-runs/${runId}`, { method: 'DELETE' }),

  /** Retry a failed / partial_analysis / rejected run. Returns the NEW run. */
  retryRun: (runId: string) =>
    request<AnalysisRun>(`/v1/analysis-runs/${runId}/retry`, { method: 'POST' }),

  // Change units
  getChangeUnits: (runId: string) =>
    request<{ items: ChangeUnit[] }>(`/v1/analysis-runs/${runId}/change-units`),

  getHunk: (changeUnitId: string) =>
    request<string>(`/v1/change-units/${changeUnitId}/hunk`),

  // Findings
  getFindings: (runId: string, opts?: { severity?: Severity; status?: FindingStatus }) => {
    const p = new URLSearchParams()
    if (opts?.severity) p.set('severity', opts.severity)
    if (opts?.status) p.set('status', opts.status)
    const qs = p.toString() ? `?${p}` : ''
    return request<{ items: Finding[] }>(`/v1/analysis-runs/${runId}/findings${qs}`)
  },

  updateFindingStatus: (findingId: string, body: FindingStatusUpdate) =>
    request<Finding>(`/v1/findings/${findingId}/status`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),

  // Score
  getScore: (runId: string) =>
    request<Score>(`/v1/analysis-runs/${runId}/score`),

  // Report
  getReport: (runId: string) =>
    request<Report>(`/v1/analysis-runs/${runId}/report`),

  getReportText: (runId: string) =>
    requestText(`/v1/analysis-runs/${runId}/report/content`),

  // Repositories
  listRepositories: () =>
    request<{ items: Repository[] }>('/v1/repositories'),

  getRepository: (repositoryId: string) =>
    request<Repository>(`/v1/repositories/${repositoryId}`),

  updateRepository: (repositoryId: string, body: {
    clone_url?: string | null
    access_token?: string | null
    clear_clone_url?: boolean
    clear_access_token?: boolean
    status?: 'active' | 'disabled' | 'archived'
    default_branch?: string
    provider?: 'github' | 'gitlab' | 'other'
  }) =>
    request<Repository>(`/v1/repositories/${repositoryId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),

  deleteRepository: (repositoryId: string) =>
    request<void>(`/v1/repositories/${repositoryId}`, { method: 'DELETE' }),

  listRepositoryRefs: (repositoryId: string) =>
    request<{ items: { name: string; type: string; sha: string }[] }>(
      `/v1/repositories/${repositoryId}/refs`
    ),

  listRepositoryTree: (repositoryId: string, ref: string, path = '') =>
    request<{ ref: string; path: string; items: { name: string; path: string; type: string; size: number | null }[] }>(
      `/v1/repositories/${repositoryId}/tree?ref=${encodeURIComponent(ref)}&path=${encodeURIComponent(path)}`
    ),

  readRepositoryFile: (repositoryId: string, ref: string, path: string) =>
    request<{ ref: string; path: string; content: string | null; is_text: boolean; size: number; encoding: string }>(
      `/v1/repositories/${repositoryId}/file?ref=${encodeURIComponent(ref)}&path=${encodeURIComponent(path)}`
    ),

  // Health
  health: () => request<{ status: string; version: string }>('/health'),

  // Audit
  getAuditEvents: (limit = 200) =>
    request<{ items: AuditEvent[] }>(`/v1/audit-events?limit=${limit}`),

  // Webhook test
  testGitlabWebhook: () =>
    request<{ run_id: string; status: string }>('/v1/webhooks/gitlab/test', { method: 'POST' }),

  // Settings
  getSettings: () =>
    request<{ items: Setting[] }>('/v1/settings'),

  updateSettings: (items: Record<string, string>) =>
    request<{ items: Setting[]; migration: Array<{ key: string; from: string; to: string; migrated?: boolean; note?: string }> }>(
      '/v1/settings',
      { method: 'PUT', body: JSON.stringify({ items }) },
    ),

  // Code map
  getCodeMapIndex: () => request<CodeMapIndex>('/v1/code-map'),

  getCodeMapScope: (scope: string) =>
    request<CodeMapScope>(`/v1/code-map/${scope}`),

  getCodeMapDiff: (scope: string, from: number, to: number) =>
    request<CodeMapDiff>(`/v1/code-map/${scope}/diff?from=${from}&to=${to}`),

  getCodeMapModule: (scope: string, moduleId: string) =>
    request<CodeMapModule>(`/v1/code-map/${scope}/module/${encodeURIComponent(moduleId)}`),

  getLineContext: (file: string) =>
    request<LineContext>(`/v1/code-map/line-context?file=${encodeURIComponent(file)}`),

  getCodeMapChanges: (since: string) =>
    request<{ commits: Array<{ sha: string; subject: string }>; files: CodeMapChange[] }>(
      `/v1/code-map/changes?since=${since}`,
    ),

  // Regen (async)
  postRegen: (body: RegenRequest) =>
    request<{ run_id: string; status: string }>('/v1/code-map/regen', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  postRepullRegen: (body: RegenRequest) =>
    request<{ run_id: string; status: string }>('/v1/code-map/repull-regen', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  getRegenStatus: (runId: string) =>
    request<RegenJob>(`/v1/code-map/regen/${runId}`),
}

// ── Helpers ──────────────────────────────────────────────────────────────────

export const IN_PROGRESS_STATUSES: RunStatus[] = [
  'trigger_received',
  'ingestion_started',
  'ingestion_completed',
  'agent_review_started',
  'agent_review_completed',
  'scoring_started',
  'scoring_completed',
  'report_generation_started',
]

export function isInProgress(status: RunStatus): boolean {
  return IN_PROGRESS_STATUSES.includes(status)
}

export function gradeClass(grade: string | null): string {
  if (!grade) return ''
  const g = grade.toLowerCase()
  if (g === 'a') return 'grade-a'
  if (g === 'b') return 'grade-b'
  if (g === 'c') return 'grade-c'
  return 'grade-f'
}

export function scoreClass(score: number | null): string {
  if (score === null) return ''
  if (score >= 90) return 'score-a'
  if (score >= 75) return 'score-b'
  if (score >= 60) return 'score-c'
  return 'score-f'
}

export function sevClass(sev: Severity): string {
  const map: Record<Severity, string> = {
    critical: 'fsev-c', high: 'fsev-h', medium: 'fsev-m', low: 'fsev-l', info: 'fsev-l',
  }
  return map[sev] ?? ''
}

export function statusBadge(status: RunStatus): { cls: string; label: string } {
  if (status === 'completed') return { cls: 'badge-done', label: '已完成' }
  if (status === 'failed') return { cls: 'badge-fail', label: '运行失败' }
  if (status === 'rejected') return { cls: 'badge-fail', label: '已拒绝' }
  return { cls: 'badge-run', label: '运行中' }
}

export function triggerBadge(type: TriggerType): { cls: string; label: string } {
  if (type === 'github_push') return { cls: 'badge-push', label: '推送' }
  if (type === 'github_pull_request') return { cls: 'badge-pr', label: 'PR' }
  return { cls: 'badge-manual', label: '手动' }
}

export function severityLabel(sev: Severity): string {
  const map: Record<Severity, string> = {
    critical: '严重', high: '高危', medium: '中危', low: '低危', info: '信息',
  }
  return map[sev] ?? sev
}

export function categoryLabel(cat: string): string {
  const map: Record<string, string> = {
    security: '安全', correctness: '正确性', testing: '测试',
    performance: '性能', maintainability: '可维护性',
  }
  return map[cat.toLowerCase()] ?? cat
}

export function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60_000)
  if (mins < 1) return '刚刚'
  if (mins < 60) return `${mins} 分钟前`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours} 小时前`
  return `${Math.floor(hours / 24)} 天前`
}

export function duration(start: string, end: string | null): string {
  if (!end) return '进行中…'
  const ms = new Date(end).getTime() - new Date(start).getTime()
  const s = Math.floor(ms / 1000)
  return `${Math.floor(s / 60)}分${s % 60}秒`
}

export function shortSha(sha: string): string {
  return sha.slice(0, 7)
}
