import { useModal } from '../lib/ModalContext'

/**
 * Top Navigation Bar Component
 * Features: logo, navigation buttons, user profile, logout
 * Accessibility: ARIA labels, semantic nav structure
 * Responsive: horizontal layout
 */
export default function TopNav({ onLogout }) {
  const { openModal } = useModal()

  const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: '📊' },
    { id: 'messages', label: 'Notes', icon: '💬' },
    { id: 'tasks', label: 'Tasks', icon: '✓' },
    { id: 'calendar', label: 'Calendar', icon: '📅' },
  ]

  const handleLogout = () => {
    onLogout?.()
  }

  return (
    <nav className="sticky top-0 z-20 border-b border-white/10 bg-background-DEFAULT/80 backdrop-blur-md">
      <div className="max-w-full px-4 md:px-6 py-3">
        <div className="flex items-center justify-between gap-4">
          {/* Logo */}
          <div className="flex items-center gap-3 min-w-fit">
            <div className="h-9 w-9 rounded-lg gradient-primary flex items-center justify-center shadow-glow flex-shrink-0">
              <span className="text-white font-bold text-base glow">🧠</span>
            </div>
            <div className="hidden sm:block">
              <h1 className="text-sm font-bold text-text-primary">Astra</h1>
              <p className="text-xs text-text-secondary">AI Assistant</p>
            </div>
          </div>

          {/* Navigation Buttons */}
          <div className="flex items-center gap-2 flex-1 max-w-2xl overflow-x-auto px-2">
            {navItems.map((item) => (
              <button
                key={item.id}
                onClick={() => openModal(item.id)}
                className="
                  touch-target flex-shrink-0 flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium
                  text-text-secondary hover:text-text-primary hover:bg-white/5
                  transition-all duration-200 whitespace-nowrap
                  focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-secondary
                "
                aria-label={item.label}
              >
                <span className="text-sm">{item.icon}</span>
                <span className="hidden md:inline">{item.label}</span>
              </button>
            ))}
          </div>

          {/* User Profile & Logout */}
          <div className="flex items-center gap-2 flex-shrink-0">
            <button
              type="button"
              className="
                touch-target hidden sm:flex items-center gap-2 px-3 py-2 rounded-lg
                text-text-secondary hover:text-text-primary hover:bg-white/5
                transition-all duration-200
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-secondary
              "
              aria-label="User profile"
            >
              <div className="w-6 h-6 rounded-full bg-gradient-primary glow flex-shrink-0" />
              <div className="text-left">
                <p className="text-xs font-medium text-text-primary">User</p>
                <p className="text-xs text-text-secondary">Active</p>
              </div>
            </button>

            <button
              type="button"
              onClick={handleLogout}
              className="
                touch-target px-3 py-2 rounded-lg text-xs font-semibold
                border border-red-300/30 bg-red-500/10 text-red-200
                hover:bg-red-500/20 hover:text-red-100
                transition-all duration-200
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400
              "
              aria-label="Sign out"
            >
              Logout
            </button>
          </div>
        </div>
      </div>
    </nav>
  )
}
