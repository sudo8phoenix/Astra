import { useEffect, useRef, useState } from 'react'
import { apiRequest } from '../lib/apiClient'

function createMessage(type, text) {
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    type,
    text,
    timestamp: new Date(),
    isComplete: true,
  }
}

function formatProviderStatus(providerStatus) {
  if (!providerStatus || typeof providerStatus !== 'object') {
    return ''
  }

  const gmail = providerStatus.gmail?.status || 'unknown'
  const calendar = providerStatus.calendar?.status || 'unknown'
  return `Connection status: Gmail ${gmail}, Calendar ${calendar}.`
}

function formatToolResultPreview(result) {
  if (!result?.success) {
    return result?.error || 'Request failed.'
  }

  const payload = result?.result || {}

  if (result.tool_name === 'create_task') {
    const task = payload.task || {}
    return `Created task: ${task.title || 'Untitled'} (${task.priority || 'medium'}, ${task.status || 'todo'})`
  }

  if (result.tool_name === 'list_tasks') {
    const count = payload.count ?? 0
    const tasks = Array.isArray(payload.tasks) ? payload.tasks.slice(0, 3).map((t) => t.title).filter(Boolean) : []
    return tasks.length > 0
      ? `${count} task(s): ${tasks.join(', ')}${count > tasks.length ? '...' : ''}`
      : `${count} task(s) found.`
  }

  if (result.tool_name === 'list_free_slots') {
    const slots = Array.isArray(payload.free_slots) ? payload.free_slots : []
    if (slots.length === 0) return 'No free slots found.'
    const preview = slots.slice(0, 2).map((slot) => {
      const start = slot?.start_time ? new Date(slot.start_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '--:--'
      const end = slot?.end_time ? new Date(slot.end_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '--:--'
      return `${start}-${end}`
    })
    return `${slots.length} free slot(s): ${preview.join(', ')}${slots.length > 2 ? '...' : ''}`
  }

  if (result.tool_name === 'get_daily_schedule') {
    const events = Array.isArray(payload.events) ? payload.events : []
    return `Loaded ${events.length} calendar event(s).`
  }

  return JSON.stringify(payload).slice(0, 180)
}

const REQUEST_STATE = {
  IDLE: 'idle',
  LOADING: 'loading',
  SUCCESS: 'success',
  ERROR: 'error',
}

/**
 * Chat Panel Component
 * Features: chat bubbles (user/AI), typing animation, suggested prompts
 * Accessibility: auto-scroll, aria-live for AI responses, semantic message structure
 * Responsive: adapts to mobile/tablet/desktop
 */
export default function ChatPanel() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [requestState, setRequestState] = useState(REQUEST_STATE.IDLE)
  const [errorNotice, setErrorNotice] = useState('')
  const [liveAnnouncement, setLiveAnnouncement] = useState('')
  const [toastMessage, setToastMessage] = useState('')
  const messagesEndRef = useRef(null)
  const scrollContainerRef = useRef(null)
  const conversationIdRef = useRef(crypto.randomUUID())
  const toastTimerRef = useRef(null)

  const suggestedPrompts = [
    'Check my inbox highlights',
    'Plan my day',
    'Show urgent tasks',
    'Find free slots tomorrow morning',
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

  useEffect(() => {
    return () => {
      if (toastTimerRef.current) {
        window.clearTimeout(toastTimerRef.current)
      }
    }
  }, [])

  const isLoading = requestState === REQUEST_STATE.LOADING

  const handleSendMessage = async () => {
    const trimmedInput = input.trim()
    if (!trimmedInput || isLoading) return

    setMessages(prev => [...prev, createMessage('user', trimmedInput)])
    setInput('')
    setRequestState(REQUEST_STATE.LOADING)
    setErrorNotice('')
    setToastMessage('Sending request to assistant...')

    try {
      const data = await apiRequest('/api/v1/chat/messages', {
        method: 'POST',
        body: JSON.stringify({
          message: trimmedInput,
          conversation_id: conversationIdRef.current,
        }),
      })
      let assistantText = data.message || data.response?.message || 'Request completed.'

      const providerStatusText = formatProviderStatus(data.provider_status)
      if (providerStatusText) {
        assistantText += `\n\n${providerStatusText}`
      }

      // Build AI message with additional data
      const aiMessage = {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        type: 'ai',
        text: assistantText,
        timestamp: new Date(),
        isComplete: true,
        actionCards: data.response?.action_cards || [],
        toolResults: data.tool_results || [],
      }

      // Show approval request if needed
      if (data.approval_required && data.approval_id) {
        aiMessage.actionCards.push({
          id: `approval-${data.approval_id}`,
          label: '✓ Approve',
          action: 'approve',
          payload: { approval_id: data.approval_id },
        })
        aiMessage.actionCards.push({
          id: `reject-${data.approval_id}`,
          label: '✕ Reject',
          action: 'reject',
          payload: { approval_id: data.approval_id },
        })
      }

      setMessages(prev => [...prev, aiMessage])

      const executedTools = (aiMessage.toolResults || []).map((item) => item.tool_name).filter(Boolean)
      if (executedTools.length > 0) {
        window.dispatchEvent(
          new CustomEvent('assistant:data-updated', {
            detail: { tools: executedTools },
          }),
        )
      }

      setRequestState(REQUEST_STATE.SUCCESS)
      setToastMessage('Response received successfully.')

      if (toastTimerRef.current) {
        window.clearTimeout(toastTimerRef.current)
      }

      toastTimerRef.current = window.setTimeout(() => {
        setRequestState(REQUEST_STATE.IDLE)
        setToastMessage('')
      }, 1800)
    } catch (error) {
      const errorText = error instanceof Error ? error.message : 'Failed to reach backend chat service.'
      const assistantError = `I could not reach the backend: ${errorText}`

      setMessages(prev => [...prev, createMessage('ai', assistantError)])
      setRequestState(REQUEST_STATE.ERROR)
      setErrorNotice(assistantError)
      setToastMessage('Message failed. Review error details and retry.')
    }
  }

  const handleSuggestedPrompt = (prompt) => {
    setInput(prompt)
  }

  const clearConversation = () => {
    setMessages([])
    setErrorNotice('')
    setRequestState(REQUEST_STATE.IDLE)
    setToastMessage('Conversation cleared.')
    conversationIdRef.current = crypto.randomUUID()
  }

  const statusChipClasses = {
    [REQUEST_STATE.IDLE]: 'border-white/15 text-text-secondary bg-white/5',
    [REQUEST_STATE.LOADING]: 'border-sky-300/30 text-sky-200 bg-sky-500/10',
    [REQUEST_STATE.SUCCESS]: 'border-emerald-300/30 text-emerald-200 bg-emerald-500/10',
    [REQUEST_STATE.ERROR]: 'border-red-300/30 text-red-200 bg-red-500/10',
  }

  const statusText = {
    [REQUEST_STATE.IDLE]: 'Idle',
    [REQUEST_STATE.LOADING]: 'Loading',
    [REQUEST_STATE.SUCCESS]: 'Success',
    [REQUEST_STATE.ERROR]: 'Error',
  }

  return (
    <article
      className="glass flex h-full min-h-[24rem] flex-col gap-4 rounded-xl border border-white/10 p-4 md:p-5"
      aria-label="Chat panel"
    >
      <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">
        {liveAnnouncement}
      </p>

      <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">
        {toastMessage}
      </div>

      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-3">
        <div>
          <h2 className="text-base font-semibold md:text-lg">Assistant chat</h2>
          <p className="text-xs text-text-secondary md:text-sm">
            Ask for inbox summaries, planning help, and schedule checks.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${statusChipClasses[requestState]}`}
            role="status"
            aria-live="polite"
          >
            {statusText[requestState]}
          </span>
          <button
            type="button"
            onClick={clearConversation}
            className="touch-target rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-xs font-semibold text-text-secondary hover:bg-white/10 hover:text-text-primary"
            aria-label="Clear conversation"
          >
            Clear
          </button>
        </div>
      </header>

      {errorNotice && (
        <div className="rounded-lg border border-red-300/25 bg-red-500/10 px-3 py-2 text-xs text-red-100" role="alert">
          <p className="font-semibold">Connection issue</p>
          <p className="mt-1 leading-relaxed">{errorNotice}</p>
        </div>
      )}

      {/* Chat Container with Messages */}
      <div
        ref={scrollContainerRef}
        className="chat-container flex-1 overflow-y-auto"
        role="log"
        aria-label="Chat messages"
        aria-live="off"
        aria-atomic="false"
        aria-relevant="additions text"
      >
        {messages.length === 0 ? (
          <div className="flex h-full min-h-[14rem] flex-col items-center justify-center gap-4 rounded-lg border border-dashed border-white/20 bg-white/5 px-5 text-center animate-fade-in">
            <h3 className="text-lg font-semibold text-text-primary">Start your first prompt</h3>
            <p className="max-w-sm text-sm text-text-secondary">
              No messages yet. Use one of the starter prompts below or type your own request.
            </p>
            <div className="flex flex-wrap justify-center gap-2">
              {suggestedPrompts.map(prompt => (
                <button
                  type="button"
                  key={`empty-${prompt}`}
                  onClick={() => handleSuggestedPrompt(prompt)}
                  className="touch-target rounded-full border border-white/20 bg-white/5 px-3 py-2 text-xs text-text-secondary hover:border-secondary/50 hover:text-secondary"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            {messages.map((message) => (
              <ChatBubble key={message.id} message={message} />
            ))}
            {isLoading && <TypingIndicator />}
          </>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Suggested Prompts (shown when input is empty) */}
      {input === '' && messages.length > 0 && (
        <div className="flex flex-col gap-2 mb-4 animate-fade-in">
          <p className="text-xs text-text-secondary font-medium">SUGGESTED</p>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {suggestedPrompts.map((prompt) => (
              <button
                type="button"
                key={prompt}
                onClick={() => handleSuggestedPrompt(prompt)}
                className="
                  touch-target rounded-lg border border-white/15 bg-white/5 px-4 py-2 text-sm font-medium
                  text-text-secondary hover:border-secondary/40 hover:text-secondary
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
      <div className="flex flex-col gap-3 border-t border-white/10 pt-3 sm:flex-row sm:items-center">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSendMessage()}
          placeholder="Ask me to summarize mail, plan your day, or check your calendar..."
          className="
            flex-1 rounded-lg border border-white/15 bg-white/5 px-4 py-3
            text-text-primary placeholder-text-tertiary
            focus:outline-none focus:ring-2 focus:ring-secondary focus:ring-offset-2
            focus:ring-offset-background-DEFAULT
            transition-all duration-200
          "
          aria-label="Chat input"
        />
        <button
          type="button"
          onClick={() => handleSendMessage()}
          disabled={!input.trim() || isLoading}
          className="
            touch-target rounded-lg gradient-primary px-4 py-3 text-white font-medium transition-all duration-200
            hover:glow-lg
            disabled:opacity-50 disabled:cursor-not-allowed disabled:scale-100
            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-secondary
          "
          aria-label={isLoading ? 'Sending message' : 'Send message'}
        >
          {isLoading ? 'Sending...' : 'Send'}
        </button>
      </div>
    </article>
  )
}

/**
 * Chat Bubble Component
 * Features: differentiates user/AI messages with styling and animation, displays action cards
 * Accessibility: aria-label indicates message sender
 */
function ChatBubble({ message }) {
  const isAI = message.type === 'ai'
  const [actionResult, setActionResult] = useState(null)
  const [isExecuting, setIsExecuting] = useState(null)

  // Check if message contains action card data (from tool results)
  const hasActionCards = message.actionCards && message.actionCards.length > 0
  const toolResults = message.toolResults || []

  const handleActionClick = async (action) => {
    setIsExecuting(action.id)
    try {
      // Handle action execution (approve, reject, etc)
      if (action.action === 'approve' && action.payload) {
        await apiRequest(`/api/v1/approvals/${action.payload.approval_id}/approve`, {
          method: 'POST',
          body: JSON.stringify({}),
        })
        setActionResult('✓ Approved successfully')
      } else if (action.action === 'reject' && action.payload) {
        await apiRequest(`/api/v1/approvals/${action.payload.approval_id}/reject?reason=User+rejected+through+chat`, {
          method: 'POST',
          body: JSON.stringify({}),
        })
        setActionResult('✗ Rejected')
      }
    } catch (error) {
      setActionResult(`Action failed: ${error.message}`)
    } finally {
      setIsExecuting(null)
      setTimeout(() => setActionResult(null), 3000)
    }
  }

  return (
    <div
      className={`flex gap-3 animate-fade-in ${isAI ? 'justify-start' : 'justify-end'}`}
      role="article"
      aria-label={`${isAI ? 'AI' : 'User'} message`}
    >
      {isAI && (
        <div className="h-8 w-8 rounded-full bg-gradient-primary flex-shrink-0 flex items-center justify-center">
          <span className="text-xs font-bold text-white">AI</span>
        </div>
      )}
      <div className="flex-1 flex flex-col gap-2">
        <div
          className={`
            max-w-[84%] px-4 py-3 rounded-lg
            ${
              isAI
                ? 'glass bg-white/5 border border-secondary/20 text-text-primary'
                : 'gradient-primary text-white'
            }
          `}
        >
          <p className="text-sm break-words whitespace-pre-wrap">{message.text}</p>
          <span className="text-xs opacity-70 mt-1 block">
            {message.timestamp.toLocaleTimeString([], {
              hour: '2-digit',
              minute: '2-digit',
            })}
          </span>
        </div>

        {/* Tool Results Display */}
        {toolResults.length > 0 && (
          <div className="space-y-2 max-w-[84%]">
            {toolResults.map((result, idx) => (
              <div key={idx} className={`rounded-lg border px-3 py-2 text-xs ${
                result.success
                  ? 'border-green-300/20 bg-green-500/10 text-green-100'
                  : 'border-red-300/20 bg-red-500/10 text-red-100'
              }`}>
                <p className="font-semibold">{result.tool_name}</p>
                {result.success && (
                  <p className="mt-1 opacity-90 break-words">{formatToolResultPreview(result)}</p>
                )}
                {!result.success && result.error && (
                  <p className="mt-1 opacity-90">{result.error}</p>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Action Cards */}
        {hasActionCards && (
          <div className="space-y-2 max-w-[84%]">
            {message.actionCards.map((card) => (
              <button
                key={card.id}
                onClick={() => handleActionClick(card)}
                disabled={isExecuting === card.id}
                className="
                  w-full text-left rounded-lg border border-secondary/40 bg-secondary/10 px-3 py-2
                  font-semibold text-secondary hover:bg-secondary/20 disabled:opacity-50
                  transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-secondary
                "
              >
                {isExecuting === card.id ? 'Processing...' : card.label}
              </button>
            ))}
          </div>
        )}

        {actionResult && (
          <div className="max-w-[84%] rounded-lg border border-green-300/20 bg-green-500/10 px-3 py-2 text-xs text-green-100">
            {actionResult}
          </div>
        )}
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
      <div className="h-8 w-8 rounded-full bg-gradient-primary flex-shrink-0 flex items-center justify-center">
        <span className="text-xs font-bold text-white">AI</span>
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
