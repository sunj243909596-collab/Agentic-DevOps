import { type Score, scoreClass, gradeClass } from '@/api/client'

interface ScoreRingProps { score: Score }

const SEV_LABELS = ['严重', '高危', '中危', '低危'] as const
const SEV_COLORS = ['var(--red)', 'var(--clay)', 'var(--amber)', 'var(--blue)'] as const
const SEV_KEYS = ['critical', 'high', 'medium', 'low'] as const

export default function ScoreRing({ score }: ScoreRingProps) {
  const value = score.final_score ?? 0
  const grade = score.grade ?? '—'
  const r = 48
  const circ = 2 * Math.PI * r
  const filled = (value / 100) * circ
  const hasCap = score.caps.length > 0

  const counts = SEV_KEYS.map(sev =>
    score.deductions.filter(d => d.severity === sev).reduce((s, d) => s + d.count, 0)
  )
  const maxCount = Math.max(...counts, 1)

  return (
    <div className="score-card">
      <div className="score-ring-wrap" style={{ position: 'relative', width: 120, height: 120 }}>
        <svg width="120" height="120" viewBox="0 0 120 120">
          <circle cx="60" cy="60" r={r} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="8" />
          <circle
            cx="60" cy="60" r={r} fill="none"
            stroke="var(--clay)" strokeWidth="8"
            strokeDasharray={`${filled} ${circ}`}
            strokeLinecap="round"
            transform="rotate(-90 60 60)"
          />
        </svg>
        <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
          <span className={`score-number ${scoreClass(value)}`} style={{ color: 'var(--surface2)' }}>{Math.round(value)}</span>
          <span className={`score-grade ${gradeClass(grade)}`}>{grade} 级</span>
        </div>
      </div>

      <div className="sev-bars">
        {SEV_LABELS.map((label, i) => (
          <div className="sev-row" key={label}>
            <span className="sev-label" style={{ color: SEV_COLORS[i] }}>{label}</span>
            <div className="sev-track">
              <div className="sev-fill" style={{ width: `${(counts[i] / maxCount) * 100}%`, background: SEV_COLORS[i] }} />
            </div>
            <span className="sev-count" style={{ color: SEV_COLORS[i] }}>{counts[i]}</span>
          </div>
        ))}
      </div>

      {hasCap && (
        <div className="sev-cap-note">⚠ {score.caps.join('；')}</div>
      )}
    </div>
  )
}
