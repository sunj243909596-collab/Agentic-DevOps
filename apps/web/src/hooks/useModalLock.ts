import { useEffect } from 'react'

/**
 * Lock the body scroll + install ESC handler while a modal is open.
 * Use in every modal component.
 */
export function useModalLock(isOpen: boolean, onEscape: () => void) {
  useEffect(() => {
    if (!isOpen) return

    // Lock body scroll
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    document.body.classList.add('modal-open')

    // ESC handler
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onEscape()
      }
    }
    document.addEventListener('keydown', onKey, true)

    return () => {
      document.body.style.overflow = prev
      document.body.classList.remove('modal-open')
      document.removeEventListener('keydown', onKey, true)
    }
  }, [isOpen, onEscape])
}
