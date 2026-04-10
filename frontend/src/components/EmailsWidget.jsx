import { useEffect, useState } from 'react'
import { apiRequest } from '../lib/apiClient'
import { extractText, normalizeEmailListResponse, normalizeSummaryResponse, normalizeUrgentEmailResponse } from '../lib/apiResponse'

function formatTime(value) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return '--:--'
  }

  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export default function EmailsWidget() {
  const [emails, setEmails] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')
  const [urgentEmails, setUrgentEmails] = useState([])
  const [showUrgent, setShowUrgent] = useState(false)
  const [loadingUrgent, setLoadingUrgent] = useState(false)
  const [successMessage, setSuccessMessage] = useState('')
  const [summary, setSummary] = useState(null)
  const [showSummary, setShowSummary] = useState(false)
  const [loadingSummary, setLoadingSummary] = useState(false)
  const [actingEmailId, setActingEmailId] = useState(null)
  const [expandedActionMenu, setExpandedActionMenu] = useState(null)
  const loadEmails = async () => {
    setIsLoading(true)
    setError('')

    try {
      const payload = await apiRequest('/api/v1/emails/list?limit=8&offset=0')
      setEmails(normalizeEmailListResponse(payload))
    } catch (loadError) {
      const message = loadError instanceof Error ? loadError.message : 'Unable to load emails.'
      setError(message)
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadEmails()
  }, [])

  const loadUrgentEmails = async () => {
    setLoadingUrgent(true)
    setError('')

    try {
      const payload = await apiRequest('/api/v1/emails/urgent')
      const urgent = normalizeUrgentEmailResponse(payload)
      setUrgentEmails(urgent)
      setShowUrgent(true)
      
      if (urgent.length === 0) {
        setSuccessMessage('No urgent emails at the moment')
        setTimeout(() => setSuccessMessage(''), 3000)
      }
    } catch (urgentError) {
      const message = urgentError instanceof Error ? urgentError.message : 'Failed to load urgent emails'
      setError(message)
    } finally {
      setLoadingUrgent(false)
    }
  }

  const loadSummary = async () => {
    setLoadingSummary(true)
    setError('')

    try {
      const payload = await apiRequest('/api/v1/emails/summarize', {
        method: 'POST',
        body: JSON.stringify({ limit: 10, include_urgent_only: false }),
      })
      const summaryText = normalizeSummaryResponse(payload) || extractText(payload, [], '')
      setSummary(summaryText)
      setShowSummary(true)
      
      // Send summary to chat for LLM analysis
      const chatMessage = `Please analyze my email inbox summary and provide insights:\n\n${summaryText}`
      
      try {
        await apiRequest('/api/v1/chat/messages', {
          method: 'POST',
          body: JSON.stringify({
            message: chatMessage,
            conversation_id: crypto.randomUUID(),
          }),
        })
      } catch (chatError) {
        // Chat submission error is not critical, just log it
        console.error('Failed to send summary to chat:', chatError)
      }
      
      setSuccessMessage('Inbox summary generated and sent to chat')
      setTimeout(() => setSuccessMessage(''), 3000)
    } catch (summaryError) {
      const message = summaryError instanceof Error ? summaryError.message : 'Failed to generate summary'
      setError(message)
    } finally {
      setLoadingSummary(false)
    }
  }

  const markAsRead = async (emailId) => {
    setActingEmailId(emailId)
    setError('')

    try {
      await apiRequest(`/api/v1/emails/${emailId}/mark-as-read`, {
        method: 'POST',
      })
      
      // Update email in list
      setEmails(emails.map(e => e.id === emailId ? { ...e, is_unread: false } : e))
      setSuccessMessage('Email marked as read')
      setTimeout(() => setSuccessMessage(''), 2000)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to mark as read'
      setError(message)
    } finally {
      setActingEmailId(null)
      setExpandedActionMenu(null)
    }
  }

  const archiveEmail = async (emailId) => {
    setActingEmailId(emailId)
    setError('')

    try {
      await apiRequest(`/api/v1/emails/${emailId}/archive`, {
        method: 'POST',
      })
      
      // Remove email from list
      setEmails(emails.filter(e => e.id !== emailId))
      setSuccessMessage('Email archived')
      setTimeout(() => setSuccessMessage(''), 2000)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to archive email'
      setError(message)
    } finally {
      setActingEmailId(null)
      setExpandedActionMenu(null)
    }
  }

  const deleteEmail = async (emailId) => {
    setActingEmailId(emailId)
    setError('')

    try {
      await apiRequest(`/api/v1/emails/${emailId}/delete`, {
        method: 'POST',
      })
      
      // Remove email from list
      setEmails(emails.filter(e => e.id !== emailId))
      setSuccessMessage('Email deleted')
      setTimeout(() => setSuccessMessage(''), 2000)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to delete email'
      setError(message)
    } finally {
      setActingEmailId(null)
      setExpandedActionMenu(null)
    }
  }

  const snoozeEmail = async (emailId, hours) => {
    setActingEmailId(emailId)
    setError('')

    try {
      await apiRequest(`/api/v1/emails/${emailId}/snooze?hours=${hours}`, {
        method: 'POST',
      })
      
      // Remove email from list
      setEmails(emails.filter(e => e.id !== emailId))
      setSuccessMessage(`Email snoozed for ${hours} hour${hours > 1 ? 's' : ''}`)
      setTimeout(() => setSuccessMessage(''), 2000)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to snooze email'
      setError(message)
    } finally {
      setActingEmailId(null)
      setExpandedActionMenu(null)
    }
  }

  const openGmailInbox = () => {
    window.open('https://mail.google.com/mail/u/0/#inbox', '_blank')
  }

  return (
    <article className="glass flex h-full min-h-0 flex-col overflow-hidden rounded-2xl p-4">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h3 className="font-display text-base font-semibold text-[#f6efe1]">Latest emails</h3>
          <p className="text-xs text-[#a8bac9]">Live inbox snapshot from Gmail integration.</p>
        </div>
        <span className="rounded-full border border-white/15 bg-white/[0.03] px-2.5 py-1 text-xs font-semibold text-[#9eb2c3]">
          {emails.length}
        </span>
      </div>

      {error && (
        <p className="mb-3 rounded-lg border border-red-300/20 bg-red-500/10 px-3 py-2 text-xs text-red-100" role="alert">
          {error}
        </p>
      )}

      {successMessage && (
        <p className="mb-3 rounded-lg border border-green-300/20 bg-green-500/10 px-3 py-2 text-xs text-green-100" role="status">
          ✓ {successMessage}
        </p>
      )}

      {isLoading ? (
        <div className="rounded-lg border border-white/15 bg-white/[0.03] px-4 py-5 text-center animate-fade-in">
          <p className="text-sm font-semibold text-text-primary">Loading emails...</p>
        </div>
      ) : emails.length === 0 ? (
        <div className="rounded-lg border border-dashed border-white/20 bg-white/[0.03] px-4 py-5 text-center animate-fade-in">
          <p className="text-sm font-semibold text-text-primary">No recent emails</p>
          <p className="mt-1 text-xs text-text-secondary">
            Connect Gmail or refresh later to see inbox items.
          </p>
        </div>
      ) : (
        <ul className="space-y-2" role="list" aria-label="Latest inbox messages">
          {emails.map((email) => (
            <li key={email.id} className="rounded-lg border border-white/15 bg-white/[0.03] px-3 py-2 group hover:bg-white/[0.06] transition-colors">
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="truncate text-sm font-semibold text-text-primary">{email.subject || '(no subject)'}</p>
                    {email.is_unread && (
                      <span className="rounded-full border border-[#36b5ce]/35 bg-[#36b5ce]/12 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[#a6e7f4] whitespace-nowrap">
                        New
                      </span>
                    )}
                  </div>
                  <p className="mt-1 truncate text-xs text-text-secondary">{email.from_name || email.from_address}</p>
                  <p className="mt-1 line-clamp-1 text-xs text-text-tertiary">{email.snippet || 'No preview available.'}</p>
                </div>
                <div className="flex items-center gap-1 ml-2">
                  <time className="text-xs text-text-secondary whitespace-nowrap">{formatTime(email.timestamp)}</time>
                  <div className="relative">
                    <button
                      type="button"
                      onClick={() => setExpandedActionMenu(expandedActionMenu === email.id ? null : email.id)}
                      disabled={actingEmailId === email.id}
                      className="
                        p-1 rounded text-text-secondary hover:bg-white/10 
                        opacity-0 group-hover:opacity-100 transition-opacity
                        disabled:opacity-50
                      "
                      aria-label="Email actions"
                    >
                      ⋮
                    </button>
                    
                    {expandedActionMenu === email.id && (
                      <div className="absolute right-0 top-full mt-1 rounded-lg border border-white/15 bg-[#0b1324] shadow-lg z-10 min-w-40 p-1">
                        <button
                          type="button"
                          onClick={() => markAsRead(email.id)}
                          disabled={actingEmailId === email.id}
                          className="w-full text-left px-3 py-1.5 text-xs hover:bg-white/10 rounded transition-colors disabled:opacity-50"
                        >
                          {actingEmailId === email.id ? '...' : '✓ Mark as Read'}
                        </button>
                        <button
                          type="button"
                          onClick={() => archiveEmail(email.id)}
                          disabled={actingEmailId === email.id}
                          className="w-full text-left px-3 py-1.5 text-xs hover:bg-white/10 rounded transition-colors disabled:opacity-50"
                        >
                          {actingEmailId === email.id ? '...' : '📦 Archive'}
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            const hours = prompt('Snooze for how many hours? (1-168)', '1')
                            if (hours && parseInt(hours) > 0 && parseInt(hours) <= 168) {
                              snoozeEmail(email.id, parseInt(hours))
                            }
                          }}
                          disabled={actingEmailId === email.id}
                          className="w-full text-left px-3 py-1.5 text-xs hover:bg-white/10 rounded transition-colors disabled:opacity-50"
                        >
                          {actingEmailId === email.id ? '...' : '⏰ Snooze'}
                        </button>
                        <button
                          type="button"
                          onClick={() => deleteEmail(email.id)}
                          disabled={actingEmailId === email.id}
                          className="w-full text-left px-3 py-1.5 text-xs text-red-300 hover:bg-red-500/10 rounded transition-colors disabled:opacity-50"
                        >
                          {actingEmailId === email.id ? '...' : '🗑 Delete'}
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}

      {/* Urgent Emails Section */}
      {showUrgent && urgentEmails.length > 0 && (
        <div className="mt-4 pt-4 border-t border-white/10 space-y-2">
          <p className="text-xs font-semibold text-red-300">⚠ Urgent ({urgentEmails.length}):</p>
          {urgentEmails.slice(0, 2).map((email) => (
            <div key={email.id} className="rounded border border-red-300/20 bg-red-500/5 px-2 py-1.5">
              <p className="truncate text-xs font-semibold text-red-200">{email.subject}</p>
              <p className="truncate text-xs text-red-100/70">{email.from_name || email.from_address || email.from}</p>
            </div>
          ))}
        </div>
      )}

      {/* Summary Section */}
      {showSummary && summary && (
        <div className="mt-4 pt-4 border-t border-white/10 space-y-2">
          <p className="text-xs font-semibold text-text-primary">📋 Summary:</p>
          <div className="rounded border border-white/15 bg-white/[0.03] px-2 py-1.5">
            <p className="text-xs text-text-secondary line-clamp-3">
              {typeof summary === 'string' ? summary : summary.summary || 'Summary generated'}
            </p>
          </div>
        </div>
      )}

      {/* Action Buttons */}
      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={loadEmails}
          disabled={isLoading}
          className="
            touch-target flex-1 min-w-20 text-center text-xs font-semibold
            rounded border border-white/15 bg-white/[0.03] text-[#dbe4ec]
            hover:bg-white/[0.06] disabled:opacity-50 transition-colors
            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green-400
          "
          aria-label="Refresh emails"
          title="Reload emails from Gmail"
        >
          {isLoading ? '...' : '🔄 Refresh'}
        </button>
        <button
          type="button"
          onClick={loadUrgentEmails}
          disabled={loadingUrgent}
          className="
            touch-target flex-1 min-w-24 text-center text-xs font-semibold
            rounded border border-[#f66635]/35 bg-[#f66635]/10 text-[#ffcdb9]
            hover:bg-[#f66635]/18 disabled:opacity-50 transition-colors
            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400
          "
          aria-label="Check urgent emails"
        >
          {loadingUrgent ? '...' : '⚠ Urgent'}
        </button>
        <button
          type="button"
          onClick={loadSummary}
          disabled={loadingSummary}
          className="
            touch-target flex-1 min-w-24 text-center text-xs font-semibold
            rounded border border-[#36b5ce]/35 bg-[#36b5ce]/10 text-[#9fe1ef]
            hover:bg-[#36b5ce]/18 disabled:opacity-50 transition-colors
            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400
          "
          aria-label="Generate inbox summary"
        >
          {loadingSummary ? '...' : '📋 Summary'}
        </button>
        <button
          type="button"
          onClick={openGmailInbox}
          className="
            touch-target flex-1 min-w-24 text-center text-xs font-semibold
            rounded border border-white/15 bg-white/[0.03] text-[#dbe4ec]
            hover:bg-white/[0.06] transition-colors
            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-secondary
          "
          aria-label="View all emails in Gmail"
          title="Open Gmail inbox in a new window"
        >
          📧 Inbox →
        </button>
      </div>
    </article>
  )
}

