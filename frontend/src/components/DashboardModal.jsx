import { useEffect, useState } from 'react'
import { apiRequest } from '../lib/apiClient'
import {
  extractArray,
  normalizeCalendarEventResponse,
  normalizeEmailListResponse,
  normalizeTaskListResponse,
} from '../lib/apiResponse'
import Modal from './Modal'

/**
 * Dashboard Modal Component
 * Features: overview of system status, quick stats, metrics
 * Accessibility: semantic headings, aria-labels
 */
export default function DashboardModal({ isOpen, onClose }) {
  const [stats, setStats] = useState({
    totalMessages: 0,
    totalTasks: 0,
    totalEvents: 0,
    pendingApprovals: 0,
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!isOpen) return

    const loadStats = async () => {
      setLoading(true)
      setError('')
      try {
        // Pull from canonical backend endpoints and normalize each payload shape.
        const [messagesRes, tasksRes, calendarRes, approvalsRes] = await Promise.allSettled([
          apiRequest('/api/v1/emails/list?limit=100&offset=0', { method: 'GET' }).catch(() => []),
          apiRequest('/api/v1/tasks?limit=100&skip=0', { method: 'GET' }).catch(() => []),
          apiRequest('/api/v1/calendar/events?limit=100&skip=0', { method: 'GET' }).catch(() => []),
          apiRequest('/api/v1/approvals/pending?limit=100&offset=0', { method: 'GET' }).catch(() => []),
        ])

        const messages = messagesRes.status === 'fulfilled' ? normalizeEmailListResponse(messagesRes.value) : []
        const tasks = tasksRes.status === 'fulfilled' ? normalizeTaskListResponse(tasksRes.value) : []
        const events = calendarRes.status === 'fulfilled' ? normalizeCalendarEventResponse(calendarRes.value) : []
        const approvals = approvalsRes.status === 'fulfilled'
          ? extractArray(approvalsRes.value, ['approvals', 'data.approvals'])
          : []

        setStats({
          totalMessages: messages.length,
          totalTasks: tasks.filter(t => t.status !== 'completed').length,
          totalEvents: events.length,
          pendingApprovals: approvals.filter(a => a.status === 'pending').length,
        })
      } catch (err) {
        setError('Unable to load dashboard stats')
      } finally {
        setLoading(false)
      }
    }

    loadStats()
  }, [isOpen])

  const statCards = [
    { label: 'Emails', value: stats.totalMessages, icon: '✉️', color: 'blue' },
    { label: 'Active Tasks', value: stats.totalTasks, icon: '✓', color: 'green' },
    { label: 'Scheduled Events', value: stats.totalEvents, icon: '📅', color: 'purple' },
    { label: 'Pending Approvals', value: stats.pendingApprovals, icon: '👁️', color: 'amber' },
  ]

  const colorClasses = {
    blue: 'border-blue-300/30 bg-blue-500/10 text-blue-200',
    green: 'border-green-300/30 bg-green-500/10 text-green-200',
    purple: 'border-purple-300/30 bg-purple-500/10 text-purple-200',
    amber: 'border-amber-300/30 bg-amber-500/10 text-amber-200',
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="📊 Dashboard Overview">
      <div className="space-y-6">
        {/* System Status */}
        <div>
          <h3 className="text-sm font-semibold text-text-secondary mb-4">SYSTEM STATUS</h3>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-emerald-400 animate-pulse" />
            <p className="text-sm text-text-primary font-medium">All systems operational</p>
          </div>
        </div>

        {/* Stats Grid */}
        <div>
          <h3 className="text-sm font-semibold text-text-secondary mb-4">QUICK STATS</h3>
          {loading ? (
            <div className="text-center py-8">
              <p className="text-text-secondary">Loading stats...</p>
            </div>
          ) : error ? (
            <div className="rounded-lg border border-red-300/30 bg-red-500/10 p-4">
              <p className="text-sm text-red-200">{error}</p>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-3">
              {statCards.map((card) => (
                <div
                  key={card.label}
                  className={`rounded-lg border p-4 ${colorClasses[card.color]}`}
                >
                  <p className="text-2xl font-bold">{card.value}</p>
                  <p className="text-xs font-medium mt-1">{card.icon} {card.label}</p>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Recent Activity */}
        <div>
          <h3 className="text-sm font-semibold text-text-secondary mb-4">RECENT ACTIVITY</h3>
          <div className="space-y-2">
            <p className="text-sm text-text-secondary text-center py-6">
              Activity logs will appear here
            </p>
          </div>
        </div>
      </div>
    </Modal>
  )
}
