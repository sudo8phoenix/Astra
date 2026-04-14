import { useState } from 'react'
import { apiRequest } from '../../lib/apiClient'
import { formatToolResultPreview } from './chatUtils'

export default function ChatBubble({ message }) {
  const isAI = message.type === 'ai'
  const [actionResult, setActionResult] = useState(null)
  const [isExecuting, setIsExecuting] = useState(null)
  const [actionResolved, setActionResolved] = useState(false)

  const hasActionCards = message.actionCards && message.actionCards.length > 0
  const toolResults = message.toolResults || []
  const timestampLabel = message.timestamp.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  })

  const formatToolName = (name) => {
    if (!name) {
      return 'Tool'
    }
    return name
      .split('_')
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(' ')
  }

  const serializePayload = (result) => {
    try {
      return JSON.stringify(result?.result || {}, null, 2)
    } catch {
      return '{}'
    }
  }

  const handleActionClick = async (action) => {
    setIsExecuting(action.id)
    try {
      if (action.action === 'approve' && action.payload) {
        const response = await apiRequest(`/api/v1/approvals/${action.payload.approval_id}/decide?decision=approve`, {
          method: 'POST',
          body: JSON.stringify({}),
        })
        const executionResult = response?.execution_result || {}
        const messageId = executionResult?.message_id
        const eventTitle = executionResult?.title
        const eventLink = executionResult?.google_event_link
        const actionType = executionResult?.action_type

        if (actionType === 'create_event') {
          window.dispatchEvent(
            new CustomEvent('assistant:data-updated', {
              detail: { tools: ['create_event'] },
            }),
          )
        } else if (actionType === 'send_email') {
          window.dispatchEvent(
            new CustomEvent('assistant:data-updated', {
              detail: { tools: ['send_new_email'] },
            }),
          )
        }

        if (eventTitle && eventLink) {
          setActionResult(`✓ Approved and created event '${eventTitle}' (${eventLink})`)
        } else if (eventTitle) {
          setActionResult(`✓ Approved and created event '${eventTitle}'`)
        } else if (messageId) {
          setActionResult(`✓ Approved and sent (message: ${messageId})`)
        } else {
          setActionResult('✓ Approved successfully')
        }
        setActionResolved(true)
      } else if (action.action === 'reject' && action.payload) {
        await apiRequest(`/api/v1/approvals/${action.payload.approval_id}/decide?decision=reject&reason=User+rejected+through+chat`, {
          method: 'POST',
          body: JSON.stringify({}),
        })
        setActionResult('✗ Rejected')
        setActionResolved(true)
      }
    } catch (error) {
      setActionResult(`Action failed: ${error.message}`)
    } finally {
      setIsExecuting(null)
    }
  }

  return (
    <div
      className={`flex gap-2.5 animate-fade-in ${isAI ? 'justify-start' : 'justify-end'}`}
      role="article"
      aria-label={`${isAI ? 'Astra' : 'User'} message`}
    >
      {isAI && (
        <div className="mt-0.5 flex h-7 min-w-11 flex-shrink-0 items-center justify-center rounded-full border border-white/20 bg-white/[0.03] px-2">
          <span className="text-[8px] font-semibold uppercase tracking-[0.08em] text-[#8E969F]">Astra</span>
        </div>
      )}
      <div className={`flex flex-1 flex-col gap-2 ${isAI ? 'items-start' : 'items-end'}`}>
        <div
          className={`
            max-w-[92%] rounded-xl px-3.5 py-3 shadow-[0_6px_18px_rgba(2,6,23,0.18)] md:max-w-[84%]
            ${isAI ? 'border border-white/15 bg-white/[0.03] text-[#C5C6C7]' : 'border border-[#66FCF1]/35 bg-[linear-gradient(135deg,rgba(69,162,158,0.3),rgba(102,252,241,0.28))] text-[#0B0C10]'}
          `}
        >
          <div className={`mb-2 flex items-center justify-between gap-2 text-[10px] uppercase tracking-[0.12em] ${isAI ? 'text-[#8E969F]' : 'text-[#8E969F]'}`}>
            <span>{isAI ? 'Assistant' : 'You'}</span>
            <span>{timestampLabel}</span>
          </div>
          <p className="break-words whitespace-pre-wrap text-sm">{message.text}</p>

          {toolResults.length > 0 && (
            <p className={`mt-3 text-xs font-medium ${isAI ? 'text-[#66FCF1]' : 'text-[#C5C6C7]'}`}>
              {toolResults.length} tool result{toolResults.length === 1 ? '' : 's'}
            </p>
          )}

          {hasActionCards && (
            <p className={`mt-1 text-xs font-medium ${isAI ? 'text-[#66FCF1]' : 'text-[#C5C6C7]'}`}>
              Action required: {message.actionCards.length} option{message.actionCards.length === 1 ? '' : 's'}
            </p>
          )}
        </div>

        {toolResults.length > 0 && (
          <div className="w-full max-w-[92%] space-y-2 md:max-w-[84%]">
            {toolResults.map((result, index) => (
              <div
                key={index}
                className={`rounded-xl border px-3 py-3 text-xs ${
                  result.success
                    ? 'border-[#45A29E]/30 bg-[#45A29E]/12 text-[#9FD6D2]'
                    : 'border-[#45A29E]/30 bg-[#45A29E]/12 text-[#B8FFFA]'
                }`}
              >
                <div className="flex items-center justify-between gap-3">
                  <p className="font-semibold">{formatToolName(result.tool_name)}</p>
                  <span className="rounded-full border border-white/25 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.14em]">
                    {result.success ? 'Success' : 'Failed'}
                  </span>
                </div>

                {result.success && <p className="mt-2 break-words opacity-90">{formatToolResultPreview(result)}</p>}
                {!result.success && result.error && <p className="mt-2 opacity-90">{result.error}</p>}

                <details className="mt-2 rounded-lg border border-white/15 bg-black/20 px-2 py-1.5 text-[11px]">
                  <summary className="cursor-pointer select-none font-medium opacity-85">View raw payload</summary>
                  <pre className="mt-2 max-h-44 overflow-auto whitespace-pre-wrap break-words rounded bg-black/30 p-2 font-mono text-[10px] leading-relaxed">
                    {serializePayload(result)}
                  </pre>
                </details>
              </div>
            ))}
          </div>
        )}

        {hasActionCards && (
          <div className="grid w-full max-w-[92%] grid-cols-1 gap-2 md:max-w-[84%] md:grid-cols-2">
            {message.actionCards.map((card) => (
              <button
                key={card.id}
                type="button"
                onClick={() => handleActionClick(card)}
                disabled={actionResolved || isExecuting === card.id}
                className={`w-full rounded-lg border px-3 py-2 text-left font-semibold transition-all disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 ${
                  card.action === 'reject'
                    ? 'border-[#45A29E]/45 bg-[#45A29E]/12 text-[#B8FFFA] hover:bg-[#45A29E]/20 focus-visible:ring-[#45A29E]'
                    : 'border-[#66FCF1]/45 bg-[#66FCF1]/12 text-[#66FCF1] hover:bg-[#66FCF1]/20 focus-visible:ring-[#66FCF1]'
                }`}
              >
                {isExecuting === card.id ? 'Processing...' : card.label}
              </button>
            ))}
          </div>
        )}

        {actionResult && (
          <div className={`w-full max-w-[92%] rounded-lg border px-3 py-2 text-xs md:max-w-[84%] ${actionResult.startsWith('Action failed') ? 'border-[#45A29E]/35 bg-[#45A29E]/12 text-[#B8FFFA]' : 'border-[#45A29E]/30 bg-[#45A29E]/12 text-[#9FD6D2]'}`}>
            {actionResult}
          </div>
        )}
      </div>
    </div>
  )
}
