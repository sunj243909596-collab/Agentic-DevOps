import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, relativeTime } from '@/api/client'
import Topbar from '@/components/Topbar'
import type { AuditEvent } from '@/api/client'

function eventTypeLabel(t: string): string {
  return t.replace(/[._]/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function EventRow({ ev }: { ev: AuditEvent }) {
  const [open, setOpen] = useState(false)
  const meta = ev.event_metadata && Object.keys(ev.event_metadata).length > 0
  return (
    <tr className="row-clickable" onClick={() => meta && setOpen(o => !o)}>
      <td style={{ fontFamily: 'monospace', fontSize: 11, color: 'var(--subtle)' }}>
        {relativeTime(ev.event_timestamp)}
      </td>
      <td style={{ fontSize: 12 }}>{ev.actor}</td>
      <td>
        <span className="badge badge-manual" style={{ fontSize: 10 }}>{eventTypeLabel(ev.event_type)}</span>
      </td>
      <td style={{ fontSize: 12, color: 'var(--mid)' }}>{ev.tool ?? '—'}</td>
      <td style={{ fontFamily: 'monospace', fontSize: 11, color: 'var(--subtle)' }}>
        {ev.workflow_id ? ev.workflow_id.slice(0, 8) : <span style={{ color: 'var(--subtle)' }}>—</span>}
      </td>
      <td style={{ fontSize: 12, color: 'var(--mid)' }}>
        {ev.policy_decision ?? '—'}
        {open && meta && (
          <pre style={{ marginTop: 6, padding: 8, background: 'var(--surface)', borderRadius: 3, fontSize: 10, color: 'var(--text)', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
            {JSON.stringify(ev.event_metadata, null, 2)}
          </pre>
        )}
      </td>
    </tr>
  )
}

export default function Audit() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['audit-events'],
    queryFn: () => api.getAuditEvents(200),
    refetchInterval: 30_000,
  })

  const events = data?.items ?? []

  return (
    <>
      <Topbar
        title="审计日志"
        subtitle={`共 ${events.length} 条`}
      />
      <div className="content">
        <div className="card">
          {isLoading && <div className="empty-state">加载中…</div>}
          {error && <div className="error-msg">{(error as Error).message}</div>}
          {!isLoading && !error && events.length === 0 && (
            <div className="empty-state">暂无审计事件</div>
          )}
          {!isLoading && !error && events.length > 0 && (
            <>
              <table>
                <thead>
                  <tr>
                    <th style={{ width: '14%' }}>时间</th>
                    <th style={{ width: '10%' }}>操作者</th>
                    <th style={{ width: '18%' }}>事件类型</th>
                    <th style={{ width: '12%' }}>工具</th>
                    <th style={{ width: '14%' }}>工作流</th>
                    <th>策略决策 / 元数据</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map(ev => <EventRow key={ev.event_id} ev={ev} />)}
                </tbody>
              </table>
              <div className="table-footer">
                <span className="table-footer-text">显示最新 {events.length} 条记录</span>
              </div>
            </>
          )}
        </div>
      </div>
    </>
  )
}
