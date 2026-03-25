import { useState } from 'react'

/**
 * Sidebar Navigation Component
 * Semantic: nav element with logo, navigation items, and user profile
 * Features: active state with gradient glow, responsive mobile toggle
 * Accessibility: ARIA labels, semantic list structure, keyboard navigation
 */
export default function Sidebar() {
  const [isOpen, setIsOpen] = useState(true)
  const [activeNav, setActiveNav] = useState('dashboard')

  const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: '📊' },
    { id: 'messages', label: 'Messages', icon: '💬' },
    { id: 'tasks', label: 'Tasks', icon: '✓' },
    { id: 'calendar', label: 'Calendar', icon: '📅' },
  ]

  return (
    <aside
      className={`
        glass flex flex-col gap-8 px-6 py-8 transition-all duration-300
        ${isOpen ? 'w-64' : 'w-20'}
        md:relative fixed left-0 top-0 h-screen z-50 md:z-0
        border-r border-white/10
      `}
      role="navigation"
      aria-label="Main navigation"
    >
      {/* Logo Section */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 gradient-primary rounded-lg flex items-center justify-center">
          <span className="text-white font-bold text-lg glow">🧠</span>
        </div>
        {isOpen && (
          <div className="flex-1">
            <h1 className="text-lg font-bold text-text-primary">Astra</h1>
            <p className="text-xs text-text-secondary">AI Assistant</p>
          </div>
        )}
      </div>

      {/* Navigation Items */}
      <nav className="flex-1 flex flex-col gap-2">
        <p className={`text-xs font-semibold text-text-secondary mb-2 ${!isOpen && 'hidden'}`}>
          MENU
        </p>
        <ul className="space-y-2">
          {navItems.map((item) => (
            <li key={item.id}>
              <button
                onClick={() => setActiveNav(item.id)}
                className={`
                  touch-target w-full flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium
                  transition-all duration-200 group
                  ${
                    activeNav === item.id
                      ? 'glass glow-lg bg-white/10 text-secondary gradient-glow'
                      : 'text-text-secondary hover:text-text-primary hover:bg-white/5'
                  }
                `}
                aria-label={item.label}
                aria-current={activeNav === item.id ? 'page' : undefined}
              >
                <span className="text-xl">{item.icon}</span>
                {isOpen && <span className="flex-1 text-left">{item.label}</span>}
              </button>
            </li>
          ))}
        </ul>
      </nav>

      {/* User Profile Section */}
      <div className="pt-4 border-t border-white/10">
        <button
          className="
            touch-target w-full flex items-center gap-3 px-4 py-3 rounded-lg
            text-text-secondary hover:text-text-primary hover:bg-white/5
            transition-all duration-200
          "
          aria-label="User profile"
        >
          <div className="w-8 h-8 rounded-full bg-gradient-primary glow flex-shrink-0" />
          {isOpen && (
            <div className="flex-1 text-left">
              <p className="text-sm font-medium text-text-primary">User</p>
              <p className="text-xs text-text-secondary">Profile</p>
            </div>
          )}
        </button>
      </div>

      {/* Toggle Button - Mobile */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="
          absolute top-8 right-4 md:hidden
          touch-target p-2 rounded-lg bg-white/5 hover:bg-white/10 transition-all
          text-text-secondary hover:text-text-primary
        "
        aria-label={isOpen ? 'Close sidebar' : 'Open sidebar'}
        aria-expanded={isOpen}
      >
        {isOpen ? '✕' : '☰'}
      </button>
    </aside>
  )
}
