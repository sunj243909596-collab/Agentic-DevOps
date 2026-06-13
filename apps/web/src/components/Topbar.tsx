import { useNavigate } from 'react-router-dom'

interface TopbarProps {
  title: string
  subtitle?: string
  showBack?: boolean
  actions?: React.ReactNode
}

export default function Topbar({ title, subtitle, showBack, actions }: TopbarProps) {
  const navigate = useNavigate()

  return (
    <div className="topbar">
      <div className="topbar-left">
        {showBack && (
          <button className="back-btn" onClick={() => navigate(-1)}>
            <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <polyline points="15 18 9 12 15 6" />
            </svg>
            返回
          </button>
        )}
        <span className="page-title">{title}</span>
        {subtitle && <span className="page-subtitle">{subtitle}</span>}
      </div>
      <div className="topbar-right">
        {actions}
      </div>
    </div>
  )
}
