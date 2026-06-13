import { useRef, type MouseEvent, type TouchEvent } from 'react'

/**
 * Returns event handlers for a backdrop that dismisses only on a CLEAN CLICK
 * (mousedown and mouseup within a small pixel radius) AND on the backdrop
 * element itself (not on inner modal content).
 *
 * Drag / scroll gestures across the backdrop will NOT close the modal.
 *
 * Use as:
 *   const backdrop = useBackdropDismiss(onClose)
 *   <div className="modal-bg" {...backdrop}>
 */
export function useBackdropDismiss(onDismiss: () => void) {
  const startPos = useRef<{ x: number; y: number } | null>(null)
  const startOnBackdrop = useRef(false)
  const THRESHOLD = 5 // pixels

  const handleMouseDown = (e: MouseEvent) => {
    startPos.current = { x: e.clientX, y: e.clientY }
    startOnBackdrop.current = e.target === e.currentTarget
  }
  const handleMouseUp = (e: MouseEvent) => {
    if (!startPos.current || !startOnBackdrop.current) {
      startPos.current = null
      startOnBackdrop.current = false
      return
    }
    const dx = Math.abs(e.clientX - startPos.current.x)
    const dy = Math.abs(e.clientY - startPos.current.y)
    if (dx <= THRESHOLD && dy <= THRESHOLD) {
      onDismiss()
    }
    startPos.current = null
    startOnBackdrop.current = false
  }
  const handleTouchStart = (e: TouchEvent) => {
    const t = e.touches[0]
    if (t) startPos.current = { x: t.clientX, y: t.clientY }
    startOnBackdrop.current = e.target === e.currentTarget
  }
  const handleTouchEnd = (e: TouchEvent) => {
    if (!startPos.current || !startOnBackdrop.current) {
      startPos.current = null
      startOnBackdrop.current = false
      return
    }
    const t = e.changedTouches[0]
    if (!t) { startPos.current = null; startOnBackdrop.current = false; return }
    const dx = Math.abs(t.clientX - startPos.current.x)
    const dy = Math.abs(t.clientY - startPos.current.y)
    if (dx <= THRESHOLD && dy <= THRESHOLD) {
      onDismiss()
    }
    startPos.current = null
    startOnBackdrop.current = false
  }

  return {
    onMouseDown: handleMouseDown,
    onMouseUp: handleMouseUp,
    onTouchStart: handleTouchStart,
    onTouchEnd: handleTouchEnd,
  }
}
