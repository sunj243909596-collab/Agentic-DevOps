import { type RunStatus, type TriggerType, type Severity, statusBadge, triggerBadge, severityLabel, sevClass } from '@/api/client'

interface BadgeProps { cls: string; label: string; dot?: boolean; spinner?: boolean }

export function Badge({ cls, label, dot, spinner }: BadgeProps) {
  return (
    <span className={`badge ${cls}`}>
      {dot && <span className="badge-dot" />}
      {spinner && <span className="spinner" />}
      {spinner && ' '}
      {label}
    </span>
  )
}

export function StatusBadge({ status }: { status: RunStatus }) {
  const { cls, label } = statusBadge(status)
  const isRunning = cls === 'badge-run'
  return (
    <Badge cls={cls} label={label}
      dot={!isRunning}
      spinner={isRunning}
    />
  )
}

export function TriggerBadge({ type }: { type: TriggerType }) {
  const { cls, label } = triggerBadge(type)
  return <Badge cls={cls} label={label} />
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span className={`finding-sev-badge ${sevClass(severity)}`}>
      {severityLabel(severity)}
    </span>
  )
}
