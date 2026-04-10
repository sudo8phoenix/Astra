import { useState, useEffect } from 'react'
import AppShell from './components/AppShell'
import LandingPage from './pages/LandingPage'
import { ASSISTANT_NAME } from './lib/branding'
import { FeedbackProvider } from './lib/feedback.jsx'

export default function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [isCheckingAuth, setIsCheckingAuth] = useState(true)
  const [oauthError, setOauthError] = useState('')
  const [route, setRoute] = useState(window.location.pathname || '/')

  useEffect(() => {
    checkAuthentication()
  }, [])

  useEffect(() => {
    const onPopState = () => {
      setRoute(window.location.pathname || '/')
    }

    window.addEventListener('popstate', onPopState)
    return () => {
      window.removeEventListener('popstate', onPopState)
    }
  }, [])

  const navigate = (path) => {
    if (!path || path === route) {
      return
    }
    window.history.pushState({}, '', path)
    setRoute(path)
  }

  const checkAuthentication = () => {
    const params = new URLSearchParams(window.location.search)
    const tokenFromCallback = params.get('token')
    const oauthErrorFromCallback = params.get('oauth_error')

    if (tokenFromCallback) {
      window.localStorage.setItem('ai_assistant_token', tokenFromCallback)
      window.history.replaceState({}, document.title, window.location.pathname)
    }

    if (oauthErrorFromCallback) {
      setOauthError(oauthErrorFromCallback)
      window.history.replaceState({}, document.title, window.location.pathname)
    }

    const token = window.localStorage.getItem('ai_assistant_token')
    setIsAuthenticated(!!token)
    setIsCheckingAuth(false)
  }

  const handleLoginSuccess = () => {
    setOauthError('')
    setIsAuthenticated(true)
  }

  const handleLogout = () => {
    window.localStorage.removeItem('ai_assistant_token')
    setIsAuthenticated(false)
  }

  if (isCheckingAuth) {
    return (
      <div className="min-h-screen bg-background-DEFAULT flex items-center justify-center">
        <div className="text-center">
          <div className="h-12 w-12 mx-auto mb-4 rounded-xl gradient-primary flex items-center justify-center animate-pulse">
            <span className="text-2xl">🧠</span>
          </div>
          <p className="text-text-secondary">Loading {ASSISTANT_NAME}...</p>
        </div>
      </div>
    )
  }

  return (
    <FeedbackProvider>
      {!isAuthenticated ? (
        <LandingPage onLoginSuccess={handleLoginSuccess} initialError={oauthError} />
      ) : (
        <AppShell route={route} onLogout={handleLogout} onNavigate={navigate} />
      )}
    </FeedbackProvider>
  )
}

