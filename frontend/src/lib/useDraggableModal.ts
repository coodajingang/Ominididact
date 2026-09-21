import React, { useState, useRef, useEffect } from 'react'

export function useDraggableModal(isOpen: boolean) {
  const [position, setPosition] = useState<{ x: number; y: number }>({ x: 0, y: 0 })
  const isDraggingRef = useRef(false)
  const dragStartRef = useRef<{ startX: number; startY: number; initX: number; initY: number }>({
    startX: 0,
    startY: 0,
    initX: 0,
    initY: 0,
  })

  // Reset position when opened
  useEffect(() => {
    if (isOpen) {
      setPosition({ x: 0, y: 0 })
    }
  }, [isOpen])

  const handleMouseDown = (e: React.MouseEvent) => {
    // Only drag from header container, ignore interactive controls
    if ((e.target as HTMLElement).closest('button, input, textarea, a, select')) return
    isDraggingRef.current = true
    dragStartRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      initX: position.x,
      initY: position.y,
    }

    const handleMouseMove = (moveEvent: MouseEvent) => {
      if (!isDraggingRef.current) return
      const dx = moveEvent.clientX - dragStartRef.current.startX
      const dy = moveEvent.clientY - dragStartRef.current.startY
      setPosition({
        x: dragStartRef.current.initX + dx,
        y: dragStartRef.current.initY + dy,
      })
    }

    const handleMouseUp = () => {
      isDraggingRef.current = false
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
    }

    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', handleMouseUp)
  }

  const toggleDockRight = () => {
    if (position.x > 80) {
      setPosition({ x: 0, y: 0 })
    } else {
      const offset = Math.min(window.innerWidth * 0.22, 340)
      setPosition({ x: offset, y: 0 })
    }
  }

  return {
    position,
    handleMouseDown,
    toggleDockRight,
    isDocked: position.x > 80,
  }
}
