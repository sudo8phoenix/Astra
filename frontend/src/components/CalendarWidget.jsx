import { useState, useMemo } from 'react'

/**
 * Calendar Widget Component
 * Features: daily schedule view, highlight current time, color-coded events
 * Accessibility: semantic time elements, aria-labels for events
 * Responsive: adapts to widget container
 */
export default function CalendarWidget() {
  const [events, setEvents] = useState([
    {
      id: 1,
      title: 'Team Standup',
      start: '09:00',
      end: '09:30',
      color: 'purple',
    },
    {
      id: 2,
      title: 'Client Call',
      start: '11:00',
      end: '12:00',
      color: 'blue',
    },
    {
      id: 3,
      title: 'Lunch Break',
      start: '13:00',
      end: '14:00',
      color: 'green',
    },
    {
      id: 4,
      title: 'Design Review',
      start: '15:00',
      end: '16:00',
      color: 'indigo',
    },
  ])

  const now = new Date()
  const currentTime = now.getHours() * 60 + now.getMinutes()

  const timeSlots = useMemo(() => {
    const slots = []
    for (let hour = 8; hour < 18; hour++) {
      slots.push({
        time: `${String(hour).padStart(2, '0')}:00`,
        hour,
      })
    }
    return slots
  }, [])

  const getEventColor = (color) => {
    const colors = {
      purple: 'bg-purple-500/20 border-purple-500 text-purple-300',
      blue: 'bg-blue-500/20 border-blue-500 text-blue-300',
      green: 'bg-green-500/20 border-green-500 text-green-300',
      indigo: 'bg-indigo-500/20 border-indigo-500 text-indigo-300',
    }
    return colors[color] || colors.purple
  }

  return (
    <article className="glass rounded-lg p-6 border border-white/10">
      {/* Header */}
      <h2 className="text-lg font-bold text-text-primary mb-4">Today's Schedule</h2>

      {/* Current time indicator */}
      <div className="text-xs text-text-secondary mb-3">
        {now.toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' })}
      </div>

      {/* Compact Schedule View */}
      <div className="space-y-1" role="list" aria-label="Today's events">
        {events.map((event) => {
          const [startHour, startMin] = event.start.split(':').map(Number)
          const eventMinutes = startHour * 60 + startMin
          const isCurrentEvent = currentTime >= eventMinutes && currentTime < (startHour * 60 + (startMin + 60))

          return (
            <div
              key={event.id}
              className={`
                min-h-11 flex items-center gap-2 px-3 py-2 rounded text-sm
                transition-all ${getEventColor(event.color)} border
                ${isCurrentEvent ? 'ring-2 ring-secondary/50 glow' : ''}
              `}
              role="listitem"
              aria-label={`${event.title} from ${event.start} to ${event.end}`}
            >
              <time className="font-mono font-semibold flex-shrink-0 w-12">
                {event.start}
              </time>
              <span className="flex-1 truncate">{event.title}</span>
              {isCurrentEvent && (
                <span className="text-xs font-bold animate-pulse">●</span>
              )}
            </div>
          )
        })}
      </div>

      {/* View full calendar link */}
      <button
        className="
          touch-target mt-4 w-full text-center text-sm text-secondary hover:text-secondary/80
          py-2 rounded transition-colors focus-visible:outline-none
          focus-visible:ring-2 focus-visible:ring-secondary
        "
        aria-label="View full calendar"
      >
        View calendar →
      </button>
    </article>
  )
}
