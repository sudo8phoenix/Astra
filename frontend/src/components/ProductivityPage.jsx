import { useEffect, useMemo, useState } from 'react'
import { apiRequest } from '../lib/apiClient'
import { normalizeEmailListResponse, normalizeTaskListResponse } from '../lib/apiResponse'

export default function ProductivityPage({ onBack }) {
  const [tasks, setTasks] = useState([])
  const [emails, setEmails] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true

    const load = async () => {
      setIsLoading(true)
      setError('')
      try {
        const [taskPayload, emailPayload] = await Promise.all([
          apiRequest('/api/v1/tasks?limit=100&skip=0'),
          apiRequest('/api/v1/emails/list?limit=100&offset=0'),
        ])

        if (!active) {
          return
        }

        setTasks(normalizeTaskListResponse(taskPayload))
        setEmails(normalizeEmailListResponse(emailPayload))
      } catch (requestError) {
        if (!active) {
          return
        }
        const message = requestError instanceof Error ? requestError.message : 'Failed to load productivity stats.'
        setError(message)
      } finally {
        if (active) {
          setIsLoading(false)
        }
      }
    }

    load()
    return () => {
      active = false
    }
  }, [])

  const data = useMemo(() => {
    const totalTasks = tasks.length
    const completedTasks = tasks.filter((task) => task.status === 'completed').length
    const inProgressTasks = tasks.filter((task) => task.status === 'in_progress').length
    const overdueTasks = tasks.filter((task) => task.status === 'overdue').length

    const totalEmails = emails.length
    const unreadEmails = emails.filter((email) => email.is_unread).length
    const urgentEmails = emails.filter((email) => email.is_urgent).length
    const processedEmails = Math.max(totalEmails - unreadEmails, 0)

    const taskScore = totalTasks > 0 ? (completedTasks / totalTasks) * 100 : 0
    const emailScore = totalEmails > 0 ? (processedEmails / totalEmails) * 100 : 0
    const penalty = Math.min(20, overdueTasks * 4)
    const productivityScore = Math.max(0, Math.min(100, Math.round((taskScore * 0.65) + (emailScore * 0.35) - penalty)))

    return {
      totalTasks,
      completedTasks,
      inProgressTasks,
      overdueTasks,
      totalEmails,
      unreadEmails,
      urgentEmails,
      processedEmails,
      productivityScore,
      taskCompletionRate: totalTasks > 0 ? Math.round((completedTasks / totalTasks) * 100) : 0,
      inboxClearRate: totalEmails > 0 ? Math.round((processedEmails / totalEmails) * 100) : 0,
    }
  }, [emails, tasks])

  return (
    <div className="relative min-h-screen bg-background-DEFAULT px-4 py-6 text-text-primary md:px-8 md:py-8">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,_rgba(16,185,129,0.2),_transparent_36%),radial-gradient(circle_at_bottom_right,_rgba(14,165,233,0.18),_transparent_44%)]"
      />

      <div className="relative z-10 mx-auto max-w-5xl space-y-6">
        <header className="glass rounded-xl border border-white/10 px-5 py-4 md:px-6 md:py-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-[0.14em] text-text-secondary">Performance</p>
              <h1 className="text-xl font-bold md:text-2xl">Productivity insights</h1>
              <p className="mt-1 text-sm text-text-secondary">Real-time activity health from your tasks and email workflow.</p>
            </div>
            <button
              type="button"
              onClick={onBack}
              className="touch-target rounded-lg border border-white/20 bg-white/5 px-4 py-2 text-sm font-semibold text-text-primary hover:bg-white/10"
            >
              Back to dashboard
            </button>
          </div>
        </header>

        {error && (
          <div className="rounded-lg border border-red-300/20 bg-red-500/10 px-4 py-3 text-sm text-red-100" role="alert">
            {error}
          </div>
        )}

        {isLoading ? (
          <section className="glass rounded-xl border border-white/10 px-5 py-10 text-center">
            <p className="text-sm text-text-secondary">Loading productivity data...</p>
          </section>
        ) : (
          <>
            <section className="grid gap-4 md:grid-cols-3">
              <article className="glass rounded-xl border border-white/10 p-5">
                <p className="text-xs uppercase tracking-[0.14em] text-text-secondary">Overall score</p>
                <p className="mt-3 text-4xl font-black text-secondary">{data.productivityScore}</p>
                <p className="mt-1 text-xs text-text-secondary">Balanced by task throughput, inbox clearance, and overdue penalties.</p>
              </article>

              <article className="glass rounded-xl border border-white/10 p-5">
                <p className="text-xs uppercase tracking-[0.14em] text-text-secondary">Task completion</p>
                <p className="mt-3 text-4xl font-black text-emerald-300">{data.taskCompletionRate}%</p>
                <p className="mt-1 text-xs text-text-secondary">{data.completedTasks}/{Math.max(data.totalTasks, 1)} tasks completed.</p>
              </article>

              <article className="glass rounded-xl border border-white/10 p-5">
                <p className="text-xs uppercase tracking-[0.14em] text-text-secondary">Inbox clear rate</p>
                <p className="mt-3 text-4xl font-black text-sky-300">{data.inboxClearRate}%</p>
                <p className="mt-1 text-xs text-text-secondary">{data.processedEmails}/{Math.max(data.totalEmails, 1)} emails processed.</p>
              </article>
            </section>

            <section className="grid gap-4 md:grid-cols-2">
              <article className="glass rounded-xl border border-white/10 p-5">
                <h2 className="text-sm font-semibold">Task pipeline</h2>
                <div className="mt-4 space-y-3 text-sm text-text-secondary">
                  <p>Open tasks: <span className="font-semibold text-text-primary">{data.totalTasks}</span></p>
                  <p>Completed: <span className="font-semibold text-text-primary">{data.completedTasks}</span></p>
                  <p>In progress: <span className="font-semibold text-text-primary">{data.inProgressTasks}</span></p>
                  <p>Overdue: <span className="font-semibold text-red-200">{data.overdueTasks}</span></p>
                </div>
              </article>

              <article className="glass rounded-xl border border-white/10 p-5">
                <h2 className="text-sm font-semibold">Inbox load</h2>
                <div className="mt-4 space-y-3 text-sm text-text-secondary">
                  <p>Total emails: <span className="font-semibold text-text-primary">{data.totalEmails}</span></p>
                  <p>Unread: <span className="font-semibold text-yellow-200">{data.unreadEmails}</span></p>
                  <p>Urgent: <span className="font-semibold text-red-200">{data.urgentEmails}</span></p>
                  <p>Processed: <span className="font-semibold text-text-primary">{data.processedEmails}</span></p>
                </div>
              </article>
            </section>
          </>
        )}
      </div>
    </div>
  )
}
