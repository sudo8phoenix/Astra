import { useState, useEffect } from 'react'
import { apiRequest } from '../lib/apiClient'

export default function Login({ onLoginSuccess, initialError = '' }) {
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [oauthUrl, setOauthUrl] = useState(null)

  useEffect(() => {
    loadOAuthUrl()
  }, [])

  useEffect(() => {
    if (initialError) {
      setError(initialError)
    }
  }, [initialError])

  const loadOAuthUrl = async () => {
    try {
      const response = await apiRequest('/api/v1/auth/google/login')
      if (response?.oauth_url) {
        setOauthUrl(response.oauth_url)
      } else {
        setError('Failed to generate login URL. Try refreshing.')
      }
    } catch (err) {
      setError('Failed to load OAuth options. Try refreshing.')
    }
  }

  const handleGoogleLogin = () => {
    if (oauthUrl) {
      window.location.href = oauthUrl
    }
  }

  return (
    <div className="min-h-screen bg-background-DEFAULT flex items-center justify-center p-4">
      {/* Gradient background */}
      <div
        aria-hidden="true"
        className="pointer-events-none fixed inset-0 bg-[radial-gradient(circle_at_top_left,_rgba(0,212,255,0.16),_transparent_42%),radial-gradient(circle_at_bottom_right,_rgba(108,99,255,0.24),_transparent_42%)]"
      />

      <article className="glass relative z-10 rounded-2xl border border-white/10 p-8 md:p-12 w-full max-w-md shadow-2xl">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="h-16 w-16 mx-auto mb-4 rounded-2xl gradient-primary flex items-center justify-center shadow-glow">
            <span className="text-4xl font-bold text-white glow">🧠</span>
          </div>
          <h1 className="text-3xl font-bold text-text-primary mb-2">Astra</h1>
          <p className="text-sm text-text-secondary">Your AI Assistant for Email, Calendar & Tasks</p>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="mb-6 rounded-lg border border-red-300/20 bg-red-500/10 p-4">
            <p className="text-sm text-red-100">{error}</p>
          </div>
        )}

        {/* Login Section */}
        <div className="space-y-4 mb-6">
          <button
            type="button"
            onClick={handleGoogleLogin}
            disabled={!oauthUrl || isLoading}
            className="
              w-full py-3 px-4 rounded-lg font-semibold text-white
              gradient-primary hover:glow-lg hover:scale-105
              disabled:opacity-50 disabled:scale-100
              transition-all duration-200
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-secondary
            "
            aria-label="Sign in with Google"
          >
            {isLoading ? 'Signing in...' : '🔐 Sign in with Google'}
          </button>

          <p className="text-xs text-center text-text-tertiary">
            Sign in with Google to connect your Gmail, Calendar, and get full AI assistance.
          </p>
        </div>

        {/* Info Text */}
        <div className="rounded-lg border border-blue-300/20 bg-blue-500/10 p-4 text-center">
          <p className="text-xs text-blue-100 leading-relaxed">
            💡 <span className="font-semibold">One-click login:</span> Sign in with Google to automatically connect your Gmail and Calendar for the best experience.
          </p>
        </div>
      </article>
    </div>
  )
}
