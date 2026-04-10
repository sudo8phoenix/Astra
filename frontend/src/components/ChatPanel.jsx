import { useEffect, useRef, useState } from 'react'
import { apiRequest } from '../lib/apiClient'
import { normalizeChatResponse } from '../lib/apiResponse'
import { useFeedback } from '../lib/feedback.jsx'
import ChatBubble from './chat/ChatBubble'
import TypingIndicator from './chat/TypingIndicator'
import { createMessage, formatProviderStatus } from './chat/chatUtils'

const REQUEST_STATE = {
  IDLE: 'idle',
  LOADING: 'loading',
  SUCCESS: 'success',
  ERROR: 'error',
}

export default function ChatPanel() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [requestState, setRequestState] = useState(REQUEST_STATE.IDLE)
  const [errorNotice, setErrorNotice] = useState('')
  const [liveAnnouncement, setLiveAnnouncement] = useState('')
  const [loadingStep, setLoadingStep] = useState(0)
  const messagesEndRef = useRef(null)
  const textareaRef = useRef(null)
  const conversationIdRef = useRef(crypto.randomUUID())
  const { notify, notifySuccess, notifyError } = useFeedback()
  const maxInputChars = 1200

  const suggestedPrompts = [
    'Check my inbox highlights',
    'Plan my day',
    'Show urgent tasks',
    'Find free slots tomorrow morning',
    'Search Google for AI agent workflows',
    'Save this search as a note: AI agent workflows',
  ]

  const loadingSteps = [
    'Understanding your request...',
    'Planning tool calls and data fetches...',
    'Composing response for you...',
  ]
  const compactPrompts = suggestedPrompts.slice(0, 3)
  const isLoading = requestState === REQUEST_STATE.LOADING

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    const latestMessage = messages[messages.length - 1]
    if (latestMessage?.type === 'ai') {
      setLiveAnnouncement(`Assistant response: ${latestMessage.text}`)
    }
  }, [messages])

  useEffect(() => {
    const element = textareaRef.current
    if (!element) {
      return
    }

    element.style.height = '0px'
    const nextHeight = Math.min(element.scrollHeight, 160)
    element.style.height = `${nextHeight}px`
  }, [input])

  useEffect(() => {
    if (!isLoading) {
      setLoadingStep(0)
      return
    }

    const timer = window.setInterval(() => {
      setLoadingStep((prev) => (prev + 1) % loadingSteps.length)
    }, 1300)

    return () => window.clearInterval(timer)
  }, [isLoading, loadingSteps.length])

  const handleSendMessage = async (overrideMessage) => {
    const trimmedInput = (overrideMessage ?? input).trim()
    if (!trimmedInput || isLoading) {
      return
    }

    setMessages((prev) => [...prev, createMessage('user', trimmedInput)])
    setInput('')
    setRequestState(REQUEST_STATE.LOADING)
    setErrorNotice('')
    notify('Sending request to assistant...')

    try {
      const data = await apiRequest('/api/v1/chat/messages', {
        method: 'POST',
        body: JSON.stringify({
          message: trimmedInput,
          conversation_id: conversationIdRef.current,
          context: {
            ui: {
              surface: 'dashboard_chat_panel',
              locale: window.navigator.language || 'en-US',
              timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
            },
          },
        }),
      })

      const normalizedResponse = normalizeChatResponse(data)
      let assistantText = normalizedResponse.message

      const providerStatusText = formatProviderStatus(normalizedResponse.providerStatus)
      if (providerStatusText) {
        assistantText += `\n\n${providerStatusText}`
      }

      const aiMessage = {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        type: 'ai',
        text: assistantText,
        timestamp: new Date(),
        isComplete: true,
        actionCards: normalizedResponse.actionCards,
        toolResults: normalizedResponse.toolResults,
      }

      if (normalizedResponse.approvalRequired && normalizedResponse.approvalId) {
        aiMessage.actionCards.push({
          id: `approval-${normalizedResponse.approvalId}`,
          label: '✓ Approve',
          action: 'approve',
          payload: { approval_id: normalizedResponse.approvalId },
        })
        aiMessage.actionCards.push({
          id: `reject-${normalizedResponse.approvalId}`,
          label: '✕ Reject',
          action: 'reject',
          payload: { approval_id: normalizedResponse.approvalId },
        })
      }

      setMessages((prev) => [...prev, aiMessage])

      const executedTools = (aiMessage.toolResults || []).map((item) => item.tool_name).filter(Boolean)
      if (executedTools.length > 0) {
        window.dispatchEvent(
          new CustomEvent('assistant:data-updated', {
            detail: { tools: executedTools },
          }),
        )
      }

      setRequestState(REQUEST_STATE.SUCCESS)
      notifySuccess('Response received successfully.')

      window.setTimeout(() => {
        setRequestState(REQUEST_STATE.IDLE)
      }, 1800)
    } catch (error) {
      const errorText = error instanceof Error ? error.message : 'Failed to reach backend chat service.'
      const assistantError = `I could not reach the backend: ${errorText}`

      setMessages((prev) => [...prev, createMessage('ai', assistantError)])
      setRequestState(REQUEST_STATE.ERROR)
      setErrorNotice(assistantError)
      notifyError('Message failed. Review error details and retry.')
    }
  }

  const handleSuggestedPrompt = (prompt) => {
    setInput(prompt)
    textareaRef.current?.focus()
  }

  const handleQuickSendPrompt = (prompt) => {
    if (isLoading) {
      return
    }
    void handleSendMessage(prompt)
  }

  const handleComposerKeyDown = (event) => {
    if (event.key === 'Escape' && input) {
      event.preventDefault()
      setInput('')
      return
    }

    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
      event.preventDefault()
      void handleSendMessage()
      return
    }

    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void handleSendMessage()
    }
  }

  const clearConversation = () => {
    setMessages([])
    setErrorNotice('')
    setRequestState(REQUEST_STATE.IDLE)
    notify('Conversation cleared.')
    conversationIdRef.current = crypto.randomUUID()
  }

  const statusChipClasses = {
    [REQUEST_STATE.IDLE]: 'border-white/12 bg-white/[0.03] text-[#95a6b6]',
    [REQUEST_STATE.LOADING]: 'border-[#36b5ce]/28 bg-[#36b5ce]/10 text-[#9ddceb]',
    [REQUEST_STATE.SUCCESS]: 'border-[#67d39a]/28 bg-[#67d39a]/10 text-[#b9ebd0]',
    [REQUEST_STATE.ERROR]: 'border-[#f66635]/30 bg-[#f66635]/12 text-[#ffcdb9]',
  }

  const statusText = {
    [REQUEST_STATE.IDLE]: 'Idle',
    [REQUEST_STATE.LOADING]: 'Responding',
    [REQUEST_STATE.SUCCESS]: 'Success',
    [REQUEST_STATE.ERROR]: 'Error',
  }

  return (
    <article
      className="relative flex h-full min-h-0 flex-col gap-3 overflow-hidden rounded-2xl border border-white/15 bg-white/[0.045] p-4 shadow-[0_18px_50px_rgba(2,6,23,0.26)] backdrop-blur-sm md:p-5"
      aria-label="Chat panel"
    >
      <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">
        {liveAnnouncement}
      </p>

      <header className="relative z-10 flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-3">
        <div className="space-y-1">
          <h2 className="font-display text-lg font-semibold tracking-[-0.01em] text-[#eaf0f6] md:text-xl">Assistant chat</h2>
          <p className="text-sm text-[#9fb0bf]">Ask a question and get focused, actionable help.</p>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.1em] ${statusChipClasses[requestState]}`}
            role="status"
            aria-live="polite"
          >
            {statusText[requestState]}
          </span>
          <button
            type="button"
            onClick={clearConversation}
            className="touch-target rounded-xl border border-white/15 bg-white/[0.02] px-3 py-2 text-xs font-semibold text-[#9fb0bf] hover:border-white/30 hover:bg-white/[0.06] hover:text-[#e5edf4]"
            aria-label="Clear conversation"
          >
            Clear
          </button>
        </div>
      </header>

      {errorNotice && (
        <div className="relative z-10 rounded-xl border border-[#f66635]/30 bg-[#f66635]/10 px-3 py-2 text-xs text-[#ffd9cc]" role="alert">
          <p className="font-semibold">Connection issue</p>
          <p className="mt-1 leading-relaxed">{errorNotice}</p>
        </div>
      )}

      <div
        className="chat-container relative z-10 flex-1 min-h-0 overflow-y-auto rounded-2xl border border-white/15 bg-white/[0.03] px-3 py-4 pr-2"
        role="log"
        aria-label="Chat messages"
        aria-live="off"
        aria-atomic="false"
        aria-relevant="additions text"
      >
        {messages.length === 0 ? (
          <div className="relative z-10 flex h-full min-h-[12rem] flex-col items-center justify-center gap-4 rounded-2xl border border-dashed border-white/15 bg-white/[0.02] px-5 text-center animate-fade-in">
            <h3 className="font-display text-lg font-semibold text-[#eaf0f6]">Start a conversation</h3>
            <p className="max-w-sm text-sm text-[#9fb0bf]">
              Try one of these quick prompts or write your own message below.
            </p>
            <div className="flex flex-wrap justify-center gap-2">
              {compactPrompts.map((prompt) => (
                <button
                  key={`empty-${prompt}`}
                  type="button"
                  onClick={() => handleQuickSendPrompt(prompt)}
                  className="touch-target rounded-full border border-white/20 bg-transparent px-3 py-2 text-xs text-[#b9c7d4] hover:border-white/35 hover:text-[#e5edf4]"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="relative z-10 space-y-4">
            {messages.map((message) => <ChatBubble key={message.id} message={message} />)}
            {isLoading && <TypingIndicator phase={loadingSteps[loadingStep]} />}
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {input === '' && messages.length > 0 && (
        <div className="relative z-10 mb-1 flex flex-col gap-2 animate-fade-in">
          <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-[#8194a6]">Suggested</p>
          <div className="flex flex-wrap gap-2">
            {compactPrompts.map((prompt) => (
              <button
                key={prompt}
                type="button"
                onClick={() => handleSuggestedPrompt(prompt)}
                className="touch-target rounded-full border border-white/15 bg-transparent px-3 py-1.5 text-xs font-medium text-[#b8c7d4] transition-all duration-200 hover:border-white/30 hover:text-[#e5edf4] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#36b5ce]"
              >
                {prompt}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="relative z-10 mt-auto flex flex-col gap-2 border-t border-white/10 pt-3">
        <div className="flex items-center justify-between text-[11px] text-[#7f96ab]">
          <p>Enter to send</p>
          <p aria-live="polite">{input.length}/{maxInputChars}</p>
        </div>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value.slice(0, maxInputChars))}
            onKeyDown={handleComposerKeyDown}
            placeholder="Ask anything..."
            rows={1}
            className="max-h-40 min-h-[50px] flex-1 resize-none rounded-xl border border-white/15 bg-white/[0.03] px-4 py-3 text-sm text-[#e6edf5] placeholder-[#7f96ab] transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-[#36b5ce] focus:ring-offset-2 focus:ring-offset-transparent"
            aria-label="Chat input"
          />
          <button
            type="button"
            onClick={() => handleSendMessage()}
            disabled={!input.trim() || isLoading}
            className="touch-target rounded-xl border border-white/15 bg-[linear-gradient(135deg,#f66635,#36b5ce)] px-4 py-3 font-semibold text-[#fdf4ea] shadow-[0_10px_28px_rgba(12,22,35,0.3)] transition-all duration-200 hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50 disabled:scale-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#36b5ce] sm:min-w-[96px]"
            aria-label={isLoading ? 'Sending message' : 'Send message'}
            aria-keyshortcuts="Enter"
          >
            {isLoading ? 'Sending...' : 'Send'}
          </button>
        </div>
      </div>
    </article>
  )
}
