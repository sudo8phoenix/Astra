import { useEffect } from 'react'

/**
 * Modal Overlay Component
 * Features: backdrop, fade-in animation, close on escape
 * Accessibility: focus management, ARIA attributes
 */
export default function Modal({ isOpen, onClose, title, children }) {
  useEffect(() => {
    if (!isOpen) return

    const handleEscape = (e) => {
      if (e.key === 'Escape') {
        onClose()
      }
    }

    window.addEventListener('keydown', handleEscape)
    document.body.style.overflow = 'hidden'

    return () => {
      window.removeEventListener('keydown', handleEscape)
      document.body.style.overflow = 'unset'
    }
  }, [isOpen, onClose])

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-slate-950/60 backdrop-blur-md animate-fade-in"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Modal Content */}
      <div className="relative z-10 w-full max-w-2xl mx-4 max-h-[90vh] overflow-y-auto">
        <div className="rounded-xl border border-white/10 bg-background-DEFAULT shadow-2xl">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-white/10 px-6 py-4">
            <h2 className="text-xl font-bold text-text-primary">{title}</h2>
            <button
              type="button"
              onClick={onClose}
              className="
                touch-target rounded-lg p-2 text-text-secondary hover:bg-white/10
                hover:text-text-primary transition-all duration-200
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-secondary
              "
              aria-label="Close modal"
            >
              ✕
            </button>
          </div>

          {/* Body */}
          <div className="p-6">
            {children}
          </div>
        </div>
      </div>
    </div>
  )
}
