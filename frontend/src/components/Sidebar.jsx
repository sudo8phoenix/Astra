import { useState } from 'react'
import { useModal } from '../lib/ModalContext'

/**
 * Sidebar Navigation Component
 * Semantic: nav element with logo, navigation items, and user profile
 * Features: active state with gradient glow, responsive mobile toggle
 * Accessibility: ARIA labels, semantic list structure, keyboard navigation
 */
export default function Sidebar({ mobileOpen = false, onToggleMobile, onCloseMobile, onLogout }) {
  const [activeNav, setActiveNav] = useState('dashboard')
  const { openModal } = useModal()

  const handleNavClick = (itemId) => {
    setActiveNav(itemId)
    openModal(itemId)
    onCloseMobile?.()
  }

  const handleLogout = () => {
    onCloseMobile?.()
    onLogout?.()
  }

  const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: '📊' },
    { id: 'messages', label: 'Messages', icon: '💬' },
    { id: 'tasks', label: 'Tasks', icon: '✓' },
    { id: 'calendar', label: 'Calendar', icon: '📅' },
  ]

  return (
    <aside
      className={`
        fixed left-0 top-0 z-40 flex h-screen w-64 flex-col gap-7 border-r border-white/10
        bg-background-DEFAULT/92 px-5 py-6 shadow-xl backdrop-blur-xl transition-transform duration-300
        ${mobileOpen ? 'translate-x-0' : '-translate-x-full'}
        md:translate-x-0
      `}
      role="navigation"
      aria-label="Main navigation"
    >
      {/* Logo Section */}
      <div className="flex items-center gap-3">
        <div className="h-10 w-10 rounded-xl gradient-primary flex items-center justify-center shadow-glow">
          <span className="text-white font-bold text-lg glow">🧠</span>
        </div>
        <div className="flex-1">
          <h1 className="text-lg font-bold text-text-primary">Astra</h1>
          <p className="text-xs text-text-secondary">AI Assistant</p>
        </div>

        <button
          type="button"
          onClick={onCloseMobile}
          className="touch-target rounded-lg p-2 text-text-secondary hover:bg-white/10 hover:text-text-primary md:hidden"
          aria-label="Close navigation"
        >
          ✕
        </button>
      </div>

      <p className="rounded-md border border-secondary/20 bg-secondary/10 px-3 py-2 text-xs text-text-secondary">
        Live workspace: chat, tasks, calendar, and activity insights.
      </p>

      {/* Navigation Items */}
      <nav className="flex-1 flex flex-col gap-2">
        <p className="mb-2 text-xs font-semibold tracking-[0.16em] text-text-secondary">
          MENU
        </p>
        <ul className="space-y-2">
          {navItems.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                onClick={() => handleNavClick(item.id)}
                className={`
                  touch-target w-full flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium
                  transition-all duration-200 group
                  ${
                    activeNav === item.id
                      ? 'bg-secondary/20 text-secondary border border-secondary/40 glow'
                      : 'text-text-secondary hover:text-text-primary hover:bg-white/5'
                  }
                `}
                aria-current={activeNav === item.id ? 'page' : undefined}
              >
                <span className="text-xl">{item.icon}</span>
                <span className="flex-1 text-left">{item.label}</span>
              </button>
            </li>
          ))}
        </ul>
      </nav>

      {/* User Profile Section */}
      <div className="space-y-3 pt-4 border-t border-white/10">
        <button
          type="button"
          className="
            touch-target w-full flex items-center gap-3 px-4 py-3 rounded-lg
            text-text-secondary hover:text-text-primary hover:bg-white/5
            transition-all duration-200
            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-secondary
          "
          aria-label="User profile"
        >
          <div className="w-8 h-8 rounded-full bg-gradient-primary glow flex-shrink-0" />
          <div className="flex-1 text-left">
            <p className="text-sm font-medium text-text-primary">User</p>
            <p className="text-xs text-text-secondary">Active</p>
          </div>
        </button>

        <button
          type="button"
          onClick={handleLogout}
          className="
            touch-target w-full text-center py-2.5 px-4 rounded-lg text-sm font-semibold
            border border-red-300/30 bg-red-500/10 text-red-200
            hover:bg-red-500/20 hover:text-red-100
            transition-all duration-200
            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400
          "
          aria-label="Sign out"
        >
          Sign out
        </button>
      </div>
    </aside>
  )
}
