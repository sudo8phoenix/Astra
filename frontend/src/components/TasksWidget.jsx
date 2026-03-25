import { useState } from 'react'

/**
 * Tasks Widget Component
 * Features: checklist view, priority tags, toggle completion
 * Accessibility: semantic list, checkboxes with labels, keyboard navigation
 * Responsive: adapts to container width
 */
export default function TasksWidget() {
  const [tasks, setTasks] = useState([
    { id: 1, title: 'Review project proposal', priority: 'high', completed: false },
    { id: 2, title: 'Reply to client email', priority: 'high', completed: false },
    { id: 3, title: 'Update dashboard design', priority: 'medium', completed: true },
    { id: 4, title: 'Schedule team meeting', priority: 'medium', completed: false },
  ])

  const toggleTask = (id) => {
    setTasks(prev =>
      prev.map(task =>
        task.id === id ? { ...task, completed: !task.completed } : task
      )
    )
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
  const completionPercent = Math.round((completedCount / tasks.length) * 100)

  return (
    <article className="glass rounded-lg p-6 border border-white/10">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-bold text-text-primary">Tasks</h2>
        <span className="text-xs font-medium text-text-secondary">
          {completedCount}/{tasks.length}
        </span>
      </div>

      {/* Progress Bar */}
      <div className="mb-4 bg-white/5 rounded-full h-2 overflow-hidden">
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

      {/* Task List */}
      <ul className="space-y-2" role="list">
        {tasks.map(task => (
          <li key={task.id} className="min-h-11 flex items-center gap-3 group p-2 rounded hover:bg-white/5 transition-all">
            <input
              type="checkbox"
              id={`task-${task.id}`}
              checked={task.completed}
              onChange={() => toggleTask(task.id)}
              className="
                w-4 h-4 rounded accent-secondary
                cursor-pointer focus-visible:ring-2 focus-visible:ring-secondary
              "
              aria-label={`Toggle task: ${task.title}`}
            />
            <label
              htmlFor={`task-${task.id}`}
              className={`
                flex-1 text-sm cursor-pointer transition-all
                ${task.completed ? 'line-through text-text-tertiary' : 'text-text-primary'}
              `}
            >
              {task.title}
            </label>
            <span className={`text-xs px-2 py-1 rounded ${getPriorityColor(task.priority)}`}>
              {task.priority}
            </span>
          </li>
        ))}
      </ul>

      {/* View All Link */}
      <button
        className="
          touch-target mt-4 w-full text-center text-sm text-secondary hover:text-secondary/80
          py-2 rounded transition-colors focus-visible:outline-none
          focus-visible:ring-2 focus-visible:ring-secondary
        "
        aria-label="View all tasks"
      >
        View all tasks →
      </button>
    </article>
  )
}
