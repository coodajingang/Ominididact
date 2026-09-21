/**
 * Global wheel scroll listener to fix Radix UI + react-remove-scroll inside Dialog modals:
 *
 * When a Dialog modal is open in Radix UI, react-remove-scroll attaches a 'wheel' listener
 * to the document object that calls event.preventDefault() on any wheel event whose target
 * is not inside the DialogContent container.
 * Because SelectContent and Combobox (PopoverContent) are portaled to document.body,
 * mouse wheel scrolling over the dropdown list items is blocked by react-remove-scroll,
 * while dragging the scrollbar thumb with the mouse still works.
 *
 * By intercepting 'wheel' events in the capture phase on window (which fires BEFORE document),
 * we check if the event target is inside a scrollable container or dropdown/popover/combobox/select.
 * If so, calling e.stopImmediatePropagation() prevents react-remove-scroll's document listener
 * from ever firing, allowing the browser's native wheel scrolling to execute smoothly.
 */

export function initWheelScrollFix() {
  if (typeof window === 'undefined') return

  const onWheelCapture = (e: WheelEvent) => {
    let target = e.target as HTMLElement | null
    while (target && target !== document.body && target !== document.documentElement) {
      const isDropdownOrList =
        target.hasAttribute('cmdk-list') ||
        target.hasAttribute('data-radix-select-viewport') ||
        Boolean(target.closest?.('[data-radix-popper-content-wrapper]')) ||
        Boolean(target.closest?.('[data-radix-select-content]')) ||
        Boolean(target.closest?.('[role="listbox"]')) ||
        Boolean(target.closest?.('[role="combobox"]'))

      const style = window.getComputedStyle(target)
      const isScrollable =
        (style.overflowY === 'auto' || style.overflowY === 'scroll') &&
        target.scrollHeight > target.clientHeight

      if (isScrollable || isDropdownOrList) {
        // Stop propagation in capture phase so react-remove-scroll on document never receives it
        e.stopPropagation()
        e.stopImmediatePropagation()
        return
      }

      target = target.parentElement
    }
  }

  window.addEventListener('wheel', onWheelCapture, { capture: true, passive: false })
}
