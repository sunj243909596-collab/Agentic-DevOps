import { useEffect, useState } from 'react'

interface Toast {
  id: number
  kind: 'error' | 'info'
  text: string
}

let _push: ((t: Omit<Toast, 'id'>) => void) | null = null

export function pushToast(t: Omit<Toast, 'id'>) {
  _push?.(t)
}

export function ToastHost() {
  const [items, setItems] = useState<Toast[]>([])

  useEffect(() => {
    _push = (t) => {
      const id = Date.now() + Math.random()
      setItems(prev => [...prev, { ...t, id }])
      setTimeout(() => setItems(prev => prev.filter(x => x.id !== id)), 5000)
    }
    return () => {
      _push = null
    }
  }, [])

  return (
    <div className="toast-host">
      {items.map(t => (
        <div key={t.id} className={`toast toast-${t.kind}`}>
          <span className="toast-dot" />
          <span>{t.text}</span>
        </div>
      ))}
    </div>
  )
}
