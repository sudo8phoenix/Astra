import { useEffect, useState } from 'react'
import { useModal } from '../lib/ModalContext'
import { apiRequest } from '../lib/apiClient'
import { ASSISTANT_NAME } from '../lib/branding'
import { normalizeProfileResponse } from '../lib/apiResponse'

/**
 * Top Navigation Bar Component
 * Features: logo, navigation buttons, user profile, logout
 * Accessibility: ARIA labels, semantic nav structure
 * Responsive: horizontal layout
 */
export default function TopNav({ onLogout, onNavigate }) {
  const { openModal } = useModal()
  const [profile, setProfile] = useState({
    name: 'User',
    role: '',
    organization: '',
  })

  useEffect(() => {
    let mounted = true

    const loadProfileSummary = async () => {
      try {
        const response = await apiRequest('/api/v1/users/profile', { method: 'GET' })
        const data = normalizeProfileResponse(response)
        if (!mounted) {
          return
        }

        setProfile(data)
      } catch {
        // Keep defaults if profile endpoint is unavailable.
      }
    }

    loadProfileSummary()

    const handleProfileUpdated = () => {
      loadProfileSummary()
    }

    window.addEventListener('assistant:profile-updated', handleProfileUpdated)
    return () => {
      mounted = false
      window.removeEventListener('assistant:profile-updated', handleProfileUpdated)
    }
  }, [])

  const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: '📊', type: 'modal' },
    { id: 'messages', label: 'Notes', icon: '💬', type: 'modal' },
    { id: 'productivity', label: 'Productivity', icon: '⚡', type: 'route', path: '/productivity' },
  ]

  const handleNavigation = (item) => {
    if (item.type === 'route') {
      onNavigate?.(item.path)
      return
    }
    openModal(item.id)
  }

  const handleLogout = () => {
    onLogout?.()
  }

  return (
    <nav className="sticky top-0 z-20 border-b border-white/10 bg-[#0b1324]/78 backdrop-blur-xl">
      <div className="max-w-full px-4 py-3 md:px-6">
        <div className="flex items-center justify-between gap-4">
          {/* Logo */}
          <div className="flex items-center gap-3 min-w-fit">
            <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-2xl border border-white/15 gradient-primary shadow-[0_12px_32px_rgba(2,6,23,0.35)]">
              <span className="text-white font-bold text-base glow">🧠</span>
            </div>
            <div className="hidden sm:block">
              <h1 className="text-sm font-bold text-[#f6efe1]">{ASSISTANT_NAME}</h1>
              <p className="text-xs text-[#9eb2c3]">AI Assistant</p>
            </div>
          </div>

          {/* Navigation Buttons */}
          <div className="flex flex-1 items-center justify-center gap-2 overflow-x-auto px-2 max-w-2xl">
            {navItems.map((item) => (
              <button
                key={item.id}
                onClick={() => handleNavigation(item)}
                className="
                  touch-target flex-shrink-0 flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-3 py-2 text-xs font-medium
                  text-[#b5c5d3] hover:border-white/20 hover:bg-white/[0.06] hover:text-[#f6efe1]
                  transition-all duration-200 whitespace-nowrap
                  focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-secondary
                "
                aria-label={item.label}
              >
                <span className="text-lg md:text-xl leading-none">{item.icon}</span>
                <span className="hidden md:inline">{item.label}</span>
              </button>
            ))}
          </div>

          {/* User Profile & Logout */}
          <div className="flex items-center gap-2 flex-shrink-0">
            <button
              type="button"
              onClick={() => openModal('profile')}
              className="
                touch-target hidden items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-3 py-2 text-text-secondary hover:border-white/20 hover:bg-white/[0.06] hover:text-text-primary sm:flex
                transition-all duration-200
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-secondary
              "
              aria-label="User profile"
            >
              <div className="h-6 w-6 flex-shrink-0 rounded-full bg-gradient-primary glow" />
              <div className="text-left">
                <p className="text-xs font-medium text-[#f6efe1]">{profile.name}</p>
                <p className="text-xs text-[#9eb2c3]">
                  {profile.role || profile.organization || 'Set profile'}
                </p>
              </div>
            </button>

            <button
              type="button"
              onClick={handleLogout}
              className="
                touch-target px-3 py-2 rounded-lg text-xs font-semibold
                border border-white/15 bg-white/[0.03] text-[#f2c6b7]
                hover:border-[#f66635]/45 hover:bg-[#f66635]/12 hover:text-[#ffd9cc]
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
