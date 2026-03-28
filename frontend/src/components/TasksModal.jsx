import { useEffect, useState } from 'react'
import { apiRequest } from '../lib/apiClient'
import Modal from './Modal'

/**
 * Tasks Modal Component
 * Features: view tasks, mark complete, manage priorities, create new tasks
 * Accessibility: checkbox labels, semantic list
 */
export default function TasksModal({ isOpen, onClose }) {
  const [tasks, setTasks] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [newTask, setNewTask] = useState('')
  const [priority, setPriority] = useState('medium')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!isOpen) return

    const loadTasks = async () => {
      setLoading(true)
      setError('')
      try {
        const data = await apiRequest('/api/v1/tasks', { method: 'GET' }).catch(() => [])
        setTasks(Array.isArray(data) ? data : [])
      } catch (err) {
        setError('Unable to load tasks')
      } finally {
        setLoading(false)
      }
    }

    loadTasks()
  }, [isOpen])

  const handleAddTask = async () => {
    if (!newTask.trim()) return

    try {
      setError('')
      setSubmitting(true)

      const task = await apiRequest('/api/v1/tasks', {
        method: 'POST',
        body: JSON.stringify({
          title: newTask,
          description: '',
          priority,
          status: 'todo',
          due_date: new Date().toISOString().split('T')[0],
        }),
      })

      setTasks([task, ...tasks])
      setNewTask('')
      setPriority('medium')
    } catch (err) {
      setError('Failed to create task')
    } finally {
      setSubmitting(false)
    }
  }

  const handleToggleComplete = async (task) => {
    try {
      setError('')
      const updatedStatus = task.status === 'completed' ? 'todo' : 'completed'
      
      await apiRequest(`/api/v1/tasks/${task.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ status: updatedStatus }),
      })

      setTasks(tasks.map(t => 
        t.id === task.id ? { ...t, status: updatedStatus } : t
      ))
    } catch (err) {
      setError('Failed to update task')
    }
  }

  const handleDeleteTask = async (taskId) => {
    try {
      setError('')
      await apiRequest(`/api/v1/tasks/${taskId}`, { method: 'DELETE' })
      setTasks(tasks.filter(t => t.id !== taskId))
    } catch (err) {
      setError('Failed to delete task')
    }
  }

  const activeTasks = tasks.filter(t => t.status !== 'completed')
  const completedTasks = tasks.filter(t => t.status === 'completed')

  const priorityColors = {
    high: 'border-red-300/30 bg-red-500/10 text-red-200',
    medium: 'border-amber-300/30 bg-amber-500/10 text-amber-200',
    low: 'border-green-300/30 bg-green-500/10 text-green-200',
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="✓ Task Manager">
      <div className="space-y-6">
        {/* Create Task */}
        <div className="space-y-3 rounded-lg border border-white/10 bg-white/5 p-4">
          <label htmlFor="task-input" className="block text-sm font-semibold text-text-secondary">
            CREATE NEW TASK
          </label>
          <div className="flex gap-2">
            <input
              id="task-input"
              type="text"
              value={newTask}
              onChange={(e) => setNewTask(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleAddTask()}
              placeholder="What needs to be done?"
              className="
                flex-1 rounded-lg border border-white/15 bg-white/5 px-3 py-2
                text-text-primary placeholder:text-text-secondary
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-secondary
              "
              disabled={submitting}
            />
            <select
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
              className="
                rounded-lg border border-white/15 bg-white/5 px-3 py-2
                text-text-secondary focus-visible:outline-none focus-visible:ring-2
                focus-visible:ring-secondary
              "
              disabled={submitting}
            >
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
            </select>
            <button
              type="button"
              onClick={handleAddTask}
              disabled={!newTask.trim() || submitting}
              className="
                px-4 py-2 rounded-lg text-sm font-semibold
                border border-secondary/40 bg-secondary/10 text-secondary
                hover:bg-secondary/20 disabled:opacity-50 disabled:cursor-not-allowed
                transition-all duration-200 focus-visible:outline-none focus-visible:ring-2
                focus-visible:ring-secondary
              "
            >
              {submitting ? '...' : 'Add'}
            </button>
          </div>
        </div>

        {/* Error Message */}
        {error && (
          <div className="rounded-lg border border-red-300/30 bg-red-500/10 p-3">
            <p className="text-sm text-red-200">{error}</p>
          </div>
        )}

        {/* Active Tasks */}
        <div className="space-y-3">
          <h3 className="text-sm font-semibold text-text-secondary">
            ACTIVE TASKS ({activeTasks.length})
          </h3>
          {loading ? (
            <p className="text-text-secondary text-center py-4">Loading tasks...</p>
          ) : activeTasks.length === 0 ? (
            <p className="text-text-secondary text-center py-4 text-sm">No active tasks</p>
          ) : (
            <ul className="space-y-2 max-h-64 overflow-y-auto">
              {activeTasks.map((task) => (
                <li key={task.id} className="flex items-center gap-3 rounded-lg border border-white/10 bg-white/5 p-3">
                  <input
                    type="checkbox"
                    checked={task.status === 'completed'}
                    onChange={() => handleToggleComplete(task)}
                    className="w-4 h-4 cursor-pointer"
                    aria-label={`Complete task: ${task.title}`}
                  />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-text-primary truncate">{task.title}</p>
                    <span className={`text-xs font-semibold inline-block mt-1 px-2 py-1 rounded ${priorityColors[task.priority]}`}>
                      {task.priority}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleDeleteTask(task.id)}
                    className="
                      touch-target p-1 text-text-secondary hover:text-red-300
                      transition-colors focus-visible:outline-none focus-visible:ring-1
                      focus-visible:ring-red-400
                    "
                    aria-label={`Delete task: ${task.title}`}
                  >
                    ✕
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Completed Tasks */}
        {completedTasks.length > 0 && (
          <div className="space-y-3">
            <h3 className="text-sm font-semibold text-text-secondary">
              COMPLETED ({completedTasks.length})
            </h3>
            <ul className="space-y-2 max-h-40 overflow-y-auto">
              {completedTasks.map((task) => (
                <li key={task.id} className="flex items-center gap-3 rounded-lg border border-green-300/30 bg-green-500/10 p-3">
                  <input
                    type="checkbox"
                    checked={true}
                    onChange={() => handleToggleComplete(task)}
                    className="w-4 h-4 cursor-pointer"
                    aria-label={`Mark incomplete: ${task.title}`}
                  />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-green-200 line-through truncate">{task.title}</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleDeleteTask(task.id)}
                    className="
                      touch-target p-1 text-green-300 hover:text-red-300
                      transition-colors focus-visible:outline-none focus-visible:ring-1
                      focus-visible:ring-red-400
                    "
                    aria-label={`Delete task: ${task.title}`}
                  >
                    ✕
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Modal>
  )
}
