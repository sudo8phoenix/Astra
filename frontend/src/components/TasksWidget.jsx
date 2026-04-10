import { useEffect, useMemo, useState } from 'react'
import { apiRequest } from '../lib/apiClient'
import ConfirmationModal from './ConfirmationModal'

/**
 * Tasks Widget Component
 * Features: checklist view, priority tags, toggle completion
 * Accessibility: semantic list, checkboxes with labels, keyboard navigation
 * Responsive: adapts to container width
 */
export default function TasksWidget() {
  const [tasks, setTasks] = useState([])
  const [showCompleted, setShowCompleted] = useState(true)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')
  const [updatingId, setUpdatingId] = useState(null)
  const [successMessage, setSuccessMessage] = useState('')
  const [deleteConfirmationOpen, setDeleteConfirmationOpen] = useState(false)
  const [taskToDelete, setTaskToDelete] = useState(null)
  const [isDeleting, setIsDeleting] = useState(false)

  useEffect(() => {
    let isMounted = true

    const loadTasks = async () => {
      setIsLoading(true)
      setError('')

      try {
        const payload = await apiRequest('/api/v1/tasks?limit=50&skip=0')
        const apiTasks = Array.isArray(payload?.tasks) ? payload.tasks : []

        if (!isMounted) {
          return
        }

        setTasks(
          apiTasks.map((task) => ({
            id: task.id,
            title: task.title,
            description: task.description || '',
            priority: task.priority || 'medium',
            status: task.status || 'todo',
            completed: task.status === 'completed',
            due_date: task.due_date,
          })),
        )
      } catch (loadError) {
        if (!isMounted) {
          return
        }

        const message = loadError instanceof Error ? loadError.message : 'Unable to load tasks.'
        setError(message)
      } finally {
        if (isMounted) {
          setIsLoading(false)
        }
      }
    }

    loadTasks()

    const onAssistantDataUpdated = (event) => {
      const tools = event?.detail?.tools || []
      if (tools.includes('create_task') || tools.includes('update_task') || tools.includes('delete_task') || tools.includes('list_tasks')) {
        loadTasks()
      }
    }

    window.addEventListener('assistant:data-updated', onAssistantDataUpdated)

    return () => {
      isMounted = false
      window.removeEventListener('assistant:data-updated', onAssistantDataUpdated)
    }
  }, [])

  const toggleTask = async (id) => {
    const task = tasks.find(t => t.id === id)
    if (!task) return

    setUpdatingId(id)
    setError('')

    try {
      const newStatus = task.completed ? 'todo' : 'completed'
      await apiRequest(`/api/v1/tasks/${id}`, {
        method: 'PUT',
        body: JSON.stringify({ status: newStatus }),
      })

      setTasks(prev =>
        prev.map(t =>
          t.id === id ? { ...t, completed: !t.completed, status: newStatus } : t
        )
      )
      setSuccessMessage(`Task "${task.title}" ${newStatus === 'completed' ? 'completed' : 'reopened'}!`)
      setTimeout(() => setSuccessMessage(''), 3000)
    } catch (updateError) {
      const message = updateError instanceof Error ? updateError.message : 'Failed to update task'
      setError(message)
    } finally {
      setUpdatingId(null)
    }
  }

  const openDeleteConfirmation = (id) => {
    const task = tasks.find(t => t.id === id)
    if (task) {
      setTaskToDelete(task)
      setDeleteConfirmationOpen(true)
    }
  }

  const confirmDelete = async () => {
    if (!taskToDelete) return

    setIsDeleting(true)
    setError('')

    try {
      await apiRequest(`/api/v1/tasks/${taskToDelete.id}`, { method: 'DELETE' })
      setTasks(prev => prev.filter(t => t.id !== taskToDelete.id))
      setSuccessMessage(`Task "${taskToDelete.title}" deleted`)
      setTimeout(() => setSuccessMessage(''), 3000)
      setDeleteConfirmationOpen(false)
      setTaskToDelete(null)
    } catch (deleteError) {
      const message = deleteError instanceof Error ? deleteError.message : 'Failed to delete task'
      setError(message)
    } finally {
      setIsDeleting(false)
    }
  }

  const cancelDelete = () => {
    setDeleteConfirmationOpen(false)
    setTaskToDelete(null)
  }

  const getPriorityColor = (priority) => {
    switch (priority) {
      case 'high':
        return 'bg-red-500/20 text-red-300'
      case 'medium':
        return 'bg-yellow-500/20 text-yellow-300'
      case 'low':
        return 'bg-green-500/20 text-green-300'
      default:
        return 'bg-gray-500/20 text-gray-300'
    }
  }

  const completedCount = tasks.filter(t => t.completed).length
  const completionPercent = tasks.length > 0 ? Math.round((completedCount / tasks.length) * 100) : 0
  const visibleTasks = useMemo(
    () => tasks.filter(task => showCompleted || !task.completed),
    [tasks, showCompleted],
  )
  const pendingCount = tasks.length - completedCount

  return (
    <article className="glass flex h-full min-h-0 flex-col overflow-hidden rounded-2xl p-4">
      {/* Header */}
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h3 className="font-display text-base font-semibold text-[#f6efe1]">Tasks</h3>
          <p className="text-xs text-[#a8bac9]">{pendingCount} open actions for today</p>
        </div>
        <span className="rounded-full border border-white/15 bg-white/[0.03] px-2.5 py-1 text-xs font-semibold text-[#9eb2c3]">
          {completedCount}/{tasks.length}
        </span>
      </div>

      {/* Progress Bar */}
      <div className="mb-4 h-2 overflow-hidden rounded-full bg-white/[0.06]" aria-hidden="true">
        <div
          className="h-full gradient-primary transition-all duration-300"
          style={{ width: `${completionPercent}%` }}
          role="progressbar"
          aria-valuenow={completionPercent}
          aria-valuemin="0"
          aria-valuemax="100"
          aria-label="Task completion progress"
        />
      </div>

      <div className="mb-3 flex items-center justify-between">
        <p className="text-xs text-[#9eb2c3]">Completion: {completionPercent}%</p>
        <button
          type="button"
          onClick={() => setShowCompleted(prev => !prev)}
          className="touch-target rounded-md border border-white/15 bg-white/[0.03] px-2.5 py-1.5 text-xs text-[#c7d3dd] hover:border-white/30 hover:bg-white/[0.06]"
          aria-pressed={showCompleted}
          aria-label={showCompleted ? 'Hide completed tasks' : 'Show completed tasks'}
        >
          {showCompleted ? 'Hide completed' : 'Show completed'}
        </button>
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

      {/* Task List */}
      {isLoading ? (
        <div className="rounded-lg border border-white/15 bg-white/[0.03] px-4 py-5 text-center animate-fade-in">
          <p className="text-sm font-semibold text-text-primary">Loading tasks...</p>
        </div>
      ) : visibleTasks.length === 0 ? (
        <div className="rounded-lg border border-dashed border-white/20 bg-white/[0.03] px-4 py-5 text-center animate-fade-in">
          <p className="text-sm font-semibold text-text-primary">No tasks to show</p>
          <p className="mt-1 text-xs text-text-secondary">
            All items are complete. Great momentum.
          </p>
        </div>
      ) : (
        <ul className="space-y-2" role="list">
          {visibleTasks.map(task => (
            <li key={task.id} className="group flex min-h-11 items-center gap-3 rounded-lg p-2 transition-all hover:bg-white/[0.05]">
              <input
                type="checkbox"
                id={`task-${task.id}`}
                checked={task.completed}
                onChange={() => toggleTask(task.id)}
                disabled={updatingId === task.id}
                className="
                  h-4 w-4 rounded accent-secondary
                  cursor-pointer focus-visible:ring-2 focus-visible:ring-secondary disabled:opacity-50
                "
                aria-label={`Toggle task: ${task.title}`}
              />
              <label
                htmlFor={`task-${task.id}`}
                className={`
                  flex-1 cursor-pointer text-sm transition-all
                  ${task.completed ? 'text-[#7f93a4] line-through' : 'text-[#e1eaf2]'}
                `}
              >
                {task.title}
              </label>
              <span className={`rounded px-2 py-1 text-xs ${getPriorityColor(task.priority)}`}>
                {task.priority}
              </span>
              <button
                type="button"
                onClick={() => openDeleteConfirmation(task.id)}
                disabled={updatingId === task.id}
                className="
                  opacity-0 group-hover:opacity-100 rounded px-2 py-1 text-xs
                  border border-red-300/30 text-red-200 bg-red-500/10 hover:bg-red-500/20
                  disabled:opacity-50 transition-all focus-visible:opacity-100
                  focus-visible:ring-2 focus-visible:ring-red-400
                "
                aria-label={`Delete task: ${task.title}`}
              >
                {updatingId === task.id ? '...' : '✕'}
              </button>
            </li>
          ))}
        </ul>
      )}

      {/* View All Link */}
      <button
        type="button"
        className="
          touch-target mt-4 w-full text-center text-sm text-[#9fe1ef] hover:text-[#b8edf8]
          py-2 rounded transition-colors focus-visible:outline-none
          focus-visible:ring-2 focus-visible:ring-secondary
        "
        aria-label="View all tasks"
      >
        View all tasks →
      </button>

      {/* Delete Confirmation Modal */}
      <ConfirmationModal
        isOpen={deleteConfirmationOpen}
        onConfirm={confirmDelete}
        onCancel={cancelDelete}
        title="Delete Task?"
        message={taskToDelete ? `Are you sure you want to delete "${taskToDelete.title}"? This action cannot be undone.` : ''}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        isLoading={isDeleting}
        isDangerous={true}
      />
    </article>
  )
}
