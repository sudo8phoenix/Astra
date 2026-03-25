import { useState, useRef, useEffect } from 'react'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''
const ENV_API_TOKEN = import.meta.env.VITE_API_TOKEN || ''
const DEV_TOKEN_ENDPOINT = `${API_BASE_URL}/api/v1/health/dev/token`

function createMessage(type, text) {
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    type,
    text,
    timestamp: new Date(),
    isComplete: true,
  }
}

/**
 * Chat Panel Component
 * Features: chat bubbles (user/AI), typing animation, suggested prompts
 * Accessibility: auto-scroll, aria-live for AI responses, semantic message structure
 * Responsive: adapts to mobile/tablet/desktop
 */
export default function ChatPanel() {
  const [messages, setMessages] = useState([
    createMessage('ai', 'Good morning! I\'ve analyzed your inbox and calendar. Ready for your daily briefing?'),
  ])
  const [input, setInput] = useState('')
  const [isTyping, setIsTyping] = useState(false)
  const [liveAnnouncement, setLiveAnnouncement] = useState('')
  const messagesEndRef = useRef(null)
  const scrollContainerRef = useRef(null)
  const conversationIdRef = useRef(crypto.randomUUID())

  const suggestedPrompts = [
    'Summarize emails',
    'Plan my day',
    'Show urgent tasks',
    'Check calendar',
  ]

  // Auto-scroll to latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Announce newly received AI messages without re-reading the full chat history.
  useEffect(() => {
    const latestMessage = messages[messages.length - 1]
    if (latestMessage?.type === 'ai') {
      setLiveAnnouncement(`Assistant response: ${latestMessage.text}`)
    }
  }, [messages])

  const getAuthToken = async () => {
    const localToken = window.localStorage.getItem('ai_assistant_token')
    if (localToken) {
      return localToken
    }

    if (ENV_API_TOKEN) {
      return ENV_API_TOKEN
    }

    try {
      const response = await fetch(DEV_TOKEN_ENDPOINT, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      })

      if (!response.ok) {
        return ''
      }

      const payload = await response.json()
      const issuedToken = payload?.data?.token || payload?.token || ''

      if (issuedToken) {
        window.localStorage.setItem('ai_assistant_token', issuedToken)
      }

      return issuedToken
    } catch {
      return ''
    }
  }

  const handleSendMessage = async () => {
    const trimmedInput = input.trim()
    if (!trimmedInput || isTyping) return

    setMessages(prev => [...prev, createMessage('user', trimmedInput)])
    setInput('')
    setIsTyping(true)

    try {
      const token = await getAuthToken()
      const headers = {
        'Content-Type': 'application/json',
      }

      if (token) {
        headers.Authorization = `Bearer ${token}`
      }

      const response = await fetch(`${API_BASE_URL}/api/v1/chat/messages`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          message: trimmedInput,
          conversation_id: conversationIdRef.current,
        }),
      })

      if (!response.ok) {
        let errorMessage = `Chat request failed (${response.status})`
        try {
          const errorData = await response.json()
          errorMessage = errorData.message || errorData.detail || errorData.error || errorMessage
        } catch {
          // Keep fallback message when response body is not JSON.
        }

        if (response.status === 401 || response.status === 403) {
          errorMessage = 'Authentication required. The UI could not obtain a token automatically. Set localStorage key "ai_assistant_token" with a valid JWT or configure VITE_API_TOKEN.'
        }

        throw new Error(errorMessage)
      }

      const data = await response.json()
      let assistantText = data.message || data.response?.message || 'Request completed.'

      if (data.approval_required && data.approval_id) {
        assistantText += `\n\nApproval requested: ${data.approval_id}`
      }

      setMessages(prev => [...prev, createMessage('ai', assistantText)])
    } catch (error) {
      const errorText = error instanceof Error ? error.message : 'Failed to reach backend chat service.'
      setMessages(prev => [...prev, createMessage('ai', `I could not reach the backend: ${errorText}`)])
    } finally {
      setIsTyping(false)
    }
  }

  const handleSuggestedPrompt = (prompt) => {
    setInput(prompt)
  }

  return (
    <section
      className="flex flex-col flex-1 h-1/2 md:h-auto p-4 md:p-6 gap-4 overflow-hidden"
      aria-label="Chat panel"
    >
      <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">
        {liveAnnouncement}
      </p>

      {/* Chat Container with Messages */}
      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto flex flex-col gap-4 mb-4 chat-container"
        role="log"
        aria-label="Chat messages"
        aria-live="off"
        aria-atomic="false"
        aria-relevant="additions text"
      >
        {messages.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center gap-4 text-center">
            <div className="text-6xl animate-scale-pop">🧠</div>
            <h2 className="text-2xl font-bold text-text-primary">Welcome to Astra</h2>
            <p className="text-text-secondary max-w-xs">
              Your intelligent assistant for managing emails, calendar, and tasks.
            </p>
          </div>
        ) : (
          <>
            {messages.map((message) => (
              <ChatBubble key={message.id} message={message} />
            ))}
            {isTyping && <TypingIndicator />}
          </>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Suggested Prompts (shown when input is empty) */}
      {input === '' && messages.length <= 1 && (
        <div className="flex flex-col gap-2 mb-4 animate-fade-in">
          <p className="text-xs text-text-secondary font-medium">SUGGESTED</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {suggestedPrompts.map((prompt) => (
              <button
                key={prompt}
                onClick={() => handleSuggestedPrompt(prompt)}
                className="
                  touch-target px-4 py-2 rounded-lg text-sm font-medium
                  glass hover:bg-white/10 hover:shadow-glow hover:scale-105
                  text-text-secondary hover:text-secondary
                  transition-all duration-200
                  focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-secondary
                "
              >
                {prompt}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input Bar */}
      <div className="flex gap-3 items-center">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSendMessage()}
          placeholder="Ask me anything..."
          className="
            flex-1 px-4 py-3 rounded-lg glass
            text-text-primary placeholder-text-tertiary
            focus:outline-none focus:ring-2 focus:ring-secondary focus:ring-offset-2
            focus:ring-offset-background-DEFAULT
            transition-all duration-200
          "
          aria-label="Chat input"
        />
        <button
          onClick={() => handleSendMessage()}
          disabled={!input.trim()}
          className="
            touch-target p-3 rounded-lg gradient-primary hover:glow-lg hover:scale-110
            text-white font-medium transition-all duration-200 active:scale-95
            disabled:opacity-50 disabled:cursor-not-allowed disabled:scale-100
            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-secondary
          "
          aria-label="Send message"
        >
          →
        </button>
        <button
          className="
            touch-target p-3 rounded-lg glass hover:bg-white/10 hover:scale-110 transition-all duration-200 active:scale-95
            text-text-secondary hover:text-secondary
            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-secondary
          "
          aria-label="Send voice message"
        >
          🎤
        </button>
      </div>
    </section>
  )
}

/**
 * Chat Bubble Component
 * Features: differentiates user/AI messages with styling and animation
 * Accessibility: aria-label indicates message sender
 */
function ChatBubble({ message }) {
  const isAI = message.type === 'ai'

  return (
    <div
      className={`flex gap-3 animate-fade-in ${isAI ? 'justify-start' : 'justify-end'}`}
      role="article"
      aria-label={`${isAI ? 'AI' : 'User'} message`}
    >
      {isAI && (
        <div className="w-8 h-8 rounded-full bg-gradient-primary flex-shrink-0 flex items-center justify-center">
          <span className="text-sm glow">🧠</span>
        </div>
      )}
      <div
        className={`
          max-w-xs md:max-w-md px-4 py-3 rounded-lg
          ${
            isAI
              ? 'glass bg-white/5 border border-secondary/20 text-text-primary'
              : 'gradient-primary text-white'
          }
        `}
      >
        <p className="text-sm break-words">{message.text}</p>
        <span className="text-xs opacity-70 mt-1 block">
          {message.timestamp.toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit',
          })}
        </span>
      </div>
    </div>
  )
}

/**
 * Typing Indicator Component
 * Shows animated dots to indicate AI is processing
 * Accessibility: aria-live region announces typing state
 */
function TypingIndicator() {
  return (
    <div
      className="flex gap-3 animate-fade-in"
      role="status"
      aria-label="AI is typing"
      aria-live="polite"
    >
      <div className="w-8 h-8 rounded-full bg-gradient-primary flex-shrink-0 flex items-center justify-center">
        <span className="text-sm glow">🧠</span>
      </div>
      <div className="glass bg-white/5 border border-secondary/20 text-text-primary max-w-xs md:max-w-md px-4 py-3 rounded-lg">
        <div className="typing-indicator">
          <span aria-hidden="true" />
          <span aria-hidden="true" />
          <span aria-hidden="true" />
        </div>
      </div>
    </div>
  )
}
