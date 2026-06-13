import { type AnalysisRun, type RunStatus, shortSha, duration } from '@/api/client'

const STEPS: { key: RunStatus; label: string }[] = [
  { key: 'ingestion_completed',     label: 'Git 摄取' },
  { key: 'agent_review_completed',  label: 'Agent 审查' },
  { key: 'scoring_completed',       label: '评分计算' },
  { key: 'completed',               label: '报告生成' },
]

const ORDER: RunStatus[] = [
  'trigger_received', 'ingestion_started', 'ingestion_completed',
  'agent_review_started', 'agent_review_completed',
  'scoring_started', 'scoring_completed',
  'report_generation_started', 'completed',
]

function stepState(stepKey: RunStatus, runStatus: RunStatus): 'done' | 'active' | 'pending' | 'fail' {
  if (runStatus === 'failed') return 'fail'
  const runIdx  = ORDER.indexOf(runStatus)
  const stepIdx = ORDER.indexOf(stepKey)
  if (stepIdx < 0) return 'pending'
  if (runIdx >= stepIdx) return 'done'
  if (runIdx === stepIdx - 1) return 'active'
  return 'pending'
}

const CheckIcon = () => (
  <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="var(--olive)" strokeWidth={2.5}>
    <polyline points="20 6 9 17 4 12" strokeLinecap="round" />
  </svg>
)
const SpinnerEl = () => <span className="spinner" style={{ color: 'var(--clay)', width: 10, height: 10 }} />
const XIcon = () => (
  <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="var(--red)" strokeWidth={2.5}>
    <line x1="18" y1="6" x2="6" y2="18" strokeLinecap="round" />
    <line x1="6" y1="6" x2="18" y2="18" strokeLinecap="round" />
  </svg>
)

interface PipelineProps { run: AnalysisRun }

export default function Pipeline({ run }: PipelineProps) {
  return (
    <div className="pipeline-card">
      <div className="pipeline-title">流水线状态</div>
      <div className="pipeline-steps">
        {STEPS.map((step, i) => {
          const state = stepState(step.key, run.status)
          return (
            <div key={step.key} style={{ display: 'flex', alignItems: 'flex-start', flex: 1 }}>
              <div className="pipeline-step" style={{ flex: 1 }}>
                <div className={`step-circle ${state === 'done' ? 'done' : state === 'active' ? 'active' : state === 'fail' ? 'fail' : ''}`}>
                  {state === 'done'   && <CheckIcon />}
                  {state === 'active' && <SpinnerEl />}
                  {state === 'fail'   && <XIcon />}
                </div>
                <div className="step-name">{step.label}</div>
                <div className="step-time" style={{ color: 'var(--subtle)', fontSize: 10 }}>—</div>
              </div>
              {i < STEPS.length - 1 && (
                <div className={`step-line ${state === 'done' ? 'done' : ''}`} style={{ flex: 1 }} />
              )}
            </div>
          )
        })}
      </div>

      <div className="pipeline-meta">
        <div>
          <div className="meta-label">基准提交</div>
          <div className="meta-value">{shortSha(run.baseline_sha)}</div>
        </div>
        <div>
          <div className="meta-label">目标提交</div>
          <div className="meta-value">{shortSha(run.target_sha)}</div>
        </div>
        <div>
          <div className="meta-label">耗时</div>
          <div className="meta-value" style={{ fontFamily: 'sans-serif' }}>
            {duration(run.started_at, run.completed_at)}
          </div>
        </div>
      </div>
    </div>
  )
}
