import { useState, useEffect } from 'react'
import Layout from './components/Layout'
import Login from './components/Login'

export default function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [isCheckingAuth, setIsCheckingAuth] = useState(true)
  const [oauthError, setOauthError] = useState('')

  useEffect(() => {
    checkAuthentication()
  }, [])

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
          <p className="text-text-secondary">Loading Astra...</p>
        </div>
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Login onLoginSuccess={handleLoginSuccess} initialError={oauthError} />
  }

  return <Layout onLogout={handleLogout} />
}

