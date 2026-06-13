import { useState } from 'react'
import Topbar from '@/components/Topbar'

interface Endpoint {
  method: 'GET' | 'POST' | 'PATCH' | 'DELETE'
  path: string
  summary: string
  details?: string
  body?: string
  response?: string
}

const SECTIONS: { group: string; endpoints: Endpoint[] }[] = [
  {
    group: '运行 (Analysis Runs)',
    endpoints: [
      {
        method: 'GET', path: '/v1/analysis-runs?limit=50&offset=0',
        summary: '列出最近运行记录',
        details: '返回 AnalysisRun 列表，按 started_at 倒序。',
        response: '{ items: AnalysisRun[] }',
      },
      {
        method: 'POST', path: '/v1/analysis-runs',
        summary: '手动触发一次运行',
        details: '如果仓库不存在则自动创建。如果仓库已存 PAT 则可省略 access_token。',
        body: '{ "repository": "org/repo", "target_branch": "main", "clone_url"?: "https://...", "target_sha"?: "abc...", "access_token"?: "glpat-..." }',
        response: 'AnalysisRun (202 Accepted)',
      },
      {
        method: 'GET', path: '/v1/analysis-runs/{run_id}',
        summary: '获取运行详情',
        details: '包含 status / target_sha / merge_base_sha / failure_reason 等。',
        response: 'AnalysisRun',
      },
      {
        method: 'DELETE', path: '/v1/analysis-runs/{run_id}',
        summary: '删除运行（级联清理）',
        details: '同时删除 change_units / findings / scores / reports；audit_events 保留只置空 workflow_id。',
        response: '204 No Content',
      },
      {
        method: 'GET', path: '/v1/analysis-runs/{run_id}/change-units',
        summary: '列出本次运行产生的所有变更文件',
        response: '{ items: ChangeUnit[] }',
      },
      {
        method: 'GET', path: '/v1/analysis-runs/{run_id}/findings?severity=critical&status=open',
        summary: '列出所有问题 (Findings)',
        response: '{ items: Finding[] }',
      },
      {
        method: 'GET', path: '/v1/analysis-runs/{run_id}/score',
        summary: '获取评分 (Score)',
        response: 'Score',
      },
      {
        method: 'GET', path: '/v1/analysis-runs/{run_id}/report',
        summary: '获取报告元数据 (JSON)',
        response: 'Report',
      },
      {
        method: 'GET', path: '/v1/analysis-runs/{run_id}/report/content',
        summary: '获取完整报告 (text/markdown)',
        response: 'text/markdown',
      },
    ],
  },
  {
    group: '仓库 (Repositories)',
    endpoints: [
      {
        method: 'GET', path: '/v1/repositories',
        summary: '列出所有活跃仓库',
        response: '{ items: Repository[] }',
      },
      {
        method: 'GET', path: '/v1/repositories/{id}',
        summary: '获取仓库详情',
        response: 'Repository',
      },
      {
        method: 'PATCH', path: '/v1/repositories/{id}',
        summary: '编辑仓库（改 URL / 令牌 / 状态 / 默认分支）',
        details: '任意字段可选；用 clear_clone_url / clear_access_token 显式置空。',
        body: '{ "clone_url"?: "https://...", "access_token"?: "glpat-...", "clear_access_token"?: false, "default_branch"?: "main", "status"?: "active|disabled|archived" }',
        response: 'Repository',
      },
      {
        method: 'DELETE', path: '/v1/repositories/{id}',
        summary: '删除仓库（无历史运行时可删）',
        details: '有 run/baseline/trigger 依赖时返回 409。建议先 PATCH status=archived。',
        response: '204 No Content / 409 Conflict',
      },
    ],
  },
  {
    group: 'Finding 状态',
    endpoints: [
      {
        method: 'PATCH', path: '/v1/findings/{finding_id}/status',
        summary: '变更问题状态（接受/拒绝/异议/解决）',
        body: '{ "status": "accepted|rejected|disputed|resolved", "reason": "必填 ≥1 字符" }',
        response: 'Finding',
      },
    ],
  },
  {
    group: '审计日志 (Audit Events)',
    endpoints: [
      {
        method: 'GET', path: '/v1/audit-events?workflow_id=&event_type=&limit=200',
        summary: '查询审计事件',
        details: '按 event_timestamp 倒序。可按 workflow_id / event_type 过滤。',
        response: '{ items: AuditEvent[] }',
      },
    ],
  },
  {
    group: 'Webhooks (入站)',
    endpoints: [
      {
        method: 'POST', path: '/v1/webhooks/gitlab',
        summary: 'GitLab Webhook 接收端点',
        details: '支持 Push Hook / Merge Request Hook。需在 GitLab Webhook 设置中配置 X-Gitlab-Token 与环境变量 GITLAB_WEBHOOK_SECRET 一致。',
      },
      {
        method: 'POST', path: '/v1/webhooks/gitlab/test',
        summary: '模拟一次 GitLab Push Hook（自测用）',
        response: '{ run_id, status: "queued (test event)" }',
      },
    ],
  },
  {
    group: '变更内容 (Change Units)',
    endpoints: [
      {
        method: 'GET', path: '/v1/change-units/{change_unit_id}/hunk',
        summary: '获取某个文件的 diff 文本',
        response: 'text/plain (unified diff)',
      },
    ],
  },
  {
    group: '健康检查',
    endpoints: [
      {
        method: 'GET', path: '/health',
        summary: '后端健康检查',
        response: '{ status: "ok", version: "0.1.0" }',
      },
    ],
  },
]

const METHOD_COLOR: Record<Endpoint['method'], string> = {
  GET: 'badge-done',
  POST: 'badge-push',
  PATCH: 'badge-pr',
  DELETE: 'badge-fail',
}

function EndpointRow({ ep }: { ep: Endpoint }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="endpoint-row">
      <div className="endpoint-head" onClick={() => setOpen(o => !o)}>
        <span className={`endpoint-method ${METHOD_COLOR[ep.method]}`}>{ep.method}</span>
        <code className="endpoint-path">{ep.path}</code>
        <span style={{ flex: 1, fontSize: 12, color: 'var(--mid)' }}>{ep.summary}</span>
        <svg className={`chevron ${open ? 'open' : ''}`} width="12" height="12" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </div>
      {open && (
        <div className="endpoint-body">
          {ep.details && <p style={{ fontSize: 12, color: 'var(--mid)', lineHeight: 1.6, marginBottom: 10 }}>{ep.details}</p>}
          {ep.body && (
            <div style={{ marginBottom: 8 }}>
              <div style={{ fontSize: 10, color: 'var(--subtle)', marginBottom: 4 }}>请求体</div>
              <pre className="code-block">{ep.body}</pre>
            </div>
          )}
          {ep.response && (
            <div>
              <div style={{ fontSize: 10, color: 'var(--subtle)', marginBottom: 4 }}>响应</div>
              <pre className="code-block">{ep.response}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function ApiDocs() {
  return (
    <>
      <Topbar
        title="API 文档"
        actions={
          <>
            <a
              href="/api-backend/openapi.json"
              target="_blank"
              rel="noreferrer"
              className="btn-sec"
              style={{ display: 'inline-flex', alignItems: 'center', textDecoration: 'none' }}
            >
              OpenAPI JSON
            </a>
            <a
              href="/api-backend/docs"
              target="_blank"
              rel="noreferrer"
              className="btn-sec"
              style={{ display: 'inline-flex', alignItems: 'center', textDecoration: 'none' }}
            >
              Swagger UI
            </a>
          </>
        }
      />
      <div className="content">
        <div className="card" style={{ padding: 20, marginBottom: 20 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>关于此文档</div>
          <div style={{ fontSize: 12, color: 'var(--mid)', lineHeight: 1.7 }}>
            DevManager 公开 REST API。所有 <code>/v1/*</code> 端点需要 <code>Authorization: Bearer &lt;API_SECRET_KEY&gt;</code> 头（开发环境可省略）。
            本页是按业务场景整理的常用端点清单，完整 schema 见右上角 <strong>OpenAPI JSON</strong> 或 <strong>Swagger UI</strong>。
          </div>
        </div>

        {SECTIONS.map(sec => (
          <div key={sec.group} className="card" style={{ padding: 0, marginBottom: 16, overflow: 'hidden' }}>
            <div className="card-header" style={{ padding: '14px 20px' }}>
              <span className="card-title">{sec.group}</span>
              <span style={{ fontSize: 11, color: 'var(--subtle)' }}>{sec.endpoints.length} 端点</span>
            </div>
            {sec.endpoints.map((ep, i) => <EndpointRow key={i} ep={ep} />)}
          </div>
        ))}
      </div>
    </>
  )
}
