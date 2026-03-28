import { useEffect, useState } from 'react'
import { apiRequest } from '../lib/apiClient'
import Modal from './Modal'

/**
 * Calendar Modal Component
 * Features: view events, create new events, time slot management
 * Accessibility: semantic time elements, aria-labels for events
 */
export default function CalendarModal({ isOpen, onClose }) {
  const [events, setEvents] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0])
  const [newEvent, setNewEvent] = useState({
    title: '',
    start_time: '09:00',
    end_time: '10:00',
  })
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!isOpen) return

    const loadEvents = async () => {
      setLoading(true)
      setError('')
      try {
        const data = await apiRequest('/api/v1/calendar/events', { method: 'GET' }).catch(() => [])
        setEvents(Array.isArray(data) ? data : [])
      } catch (err) {
        setError('Unable to load calendar events')
      } finally {
        setLoading(false)
      }
    }

    loadEvents()
  }, [isOpen])

  const handleCreateEvent = async () => {
    if (!newEvent.title.trim()) {
      setError('Please enter an event title')
      return
    }

    try {
      setError('')
      setSubmitting(true)

      const event = await apiRequest('/api/v1/calendar/events', {
        method: 'POST',
        body: JSON.stringify({
          title: newEvent.title,
          start_time: `${selectedDate}T${newEvent.start_time}:00`,
          end_time: `${selectedDate}T${newEvent.end_time}:00`,
          description: '',
        }),
      })

      setEvents([event, ...events])
      setNewEvent({
        title: '',
        start_time: '09:00',
        end_time: '10:00',
      })
    } catch (err) {
      setError('Failed to create event')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDeleteEvent = async (eventId) => {
    try {
      setError('')
      await apiRequest(`/api/v1/calendar/events/${eventId}`, { method: 'DELETE' })
      setEvents(events.filter(e => e.id !== eventId))
    } catch (err) {
      setError('Failed to delete event')
    }
  }

  const todaysEvents = events.filter(e => {
    const eventDate = new Date(e.start_time).toISOString().split('T')[0]
    return eventDate === selectedDate
  }).sort((a, b) => new Date(a.start_time) - new Date(b.start_time))

  const allEvents = events.sort((a, b) => new Date(b.start_time) - new Date(a.start_time))

  const formatTime = (dateStr) => {
    return new Date(dateStr).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }

  const formatDate = (dateStr) => {
    return new Date(dateStr).toLocaleDateString([], { month: 'short', day: 'numeric' })
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="📅 Calendar & Events">
      <div className="space-y-6">
        {/* Create Event */}
        <div className="space-y-3 rounded-lg border border-white/10 bg-white/5 p-4">
          <h3 className="text-sm font-semibold text-text-secondary">CREATE NEW EVENT</h3>
          
          <div className="space-y-3">
            <div>
              <label htmlFor="date-input" className="block text-xs font-medium text-text-secondary mb-2">
                Date
              </label>
              <input
                id="date-input"
                type="date"
                value={selectedDate}
                onChange={(e) => setSelectedDate(e.target.value)}
                className="
                  w-full rounded-lg border border-white/15 bg-white/5 px-3 py-2
                  text-text-primary focus-visible:outline-none focus-visible:ring-2
                  focus-visible:ring-secondary
                "
                disabled={submitting}
              />
            </div>

            <div>
              <label htmlFor="event-title" className="block text-xs font-medium text-text-secondary mb-2">
                Event Title
              </label>
              <input
                id="event-title"
                type="text"
                value={newEvent.title}
                onChange={(e) => setNewEvent({ ...newEvent, title: e.target.value })}
                placeholder="Meeting, Appointment, etc."
                className="
                  w-full rounded-lg border border-white/15 bg-white/5 px-3 py-2
                  text-text-primary placeholder:text-text-secondary
                  focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-secondary
                "
                disabled={submitting}
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label htmlFor="start-time" className="block text-xs font-medium text-text-secondary mb-2">
                  Start Time
                </label>
                <input
                  id="start-time"
                  type="time"
                  value={newEvent.start_time}
                  onChange={(e) => setNewEvent({ ...newEvent, start_time: e.target.value })}
                  className="
                    w-full rounded-lg border border-white/15 bg-white/5 px-3 py-2
                    text-text-primary focus-visible:outline-none focus-visible:ring-2
                    focus-visible:ring-secondary
                  "
                  disabled={submitting}
                />
              </div>
              <div>
                <label htmlFor="end-time" className="block text-xs font-medium text-text-secondary mb-2">
                  End Time
                </label>
                <input
                  id="end-time"
                  type="time"
                  value={newEvent.end_time}
                  onChange={(e) => setNewEvent({ ...newEvent, end_time: e.target.value })}
                  className="
                    w-full rounded-lg border border-white/15 bg-white/5 px-3 py-2
                    text-text-primary focus-visible:outline-none focus-visible:ring-2
                    focus-visible:ring-secondary
                  "
                  disabled={submitting}
                />
              </div>
            </div>

            <button
              type="button"
              onClick={handleCreateEvent}
              disabled={!newEvent.title.trim() || submitting}
              className="
                w-full py-2.5 px-4 rounded-lg text-sm font-semibold
                border border-secondary/40 bg-secondary/10 text-secondary
                hover:bg-secondary/20 disabled:opacity-50 disabled:cursor-not-allowed
                transition-all duration-200 focus-visible:outline-none focus-visible:ring-2
                focus-visible:ring-secondary
              "
            >
              {submitting ? 'Creating...' : '+ Create Event'}
            </button>
          </div>
        </div>

        {/* Error Message */}
        {error && (
          <div className="rounded-lg border border-red-300/30 bg-red-500/10 p-3">
            <p className="text-sm text-red-200">{error}</p>
          </div>
        )}

        {/* Today's Events */}
        <div className="space-y-3">
          <h3 className="text-sm font-semibold text-text-secondary">
            TODAY'S SCHEDULE
          </h3>
          {loading ? (
            <p className="text-text-secondary text-center py-4">Loading events...</p>
          ) : todaysEvents.length === 0 ? (
            <p className="text-text-secondary text-center py-4 text-sm">No events scheduled for today</p>
          ) : (
            <ul className="space-y-2">
              {todaysEvents.map((event) => (
                <li key={event.id} className="rounded-lg border border-purple-300/30 bg-purple-500/10 p-3">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="text-sm font-medium text-text-primary">{event.title}</p>
                      <time className="text-xs text-text-secondary mt-1">
                        {formatTime(event.start_time)} - {formatTime(event.end_time)}
                      </time>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleDeleteEvent(event.id)}
                      className="
                        touch-target p-1 text-text-secondary hover:text-red-300
                        transition-colors focus-visible:outline-none focus-visible:ring-1
                        focus-visible:ring-red-400
                      "
                      aria-label={`Delete event: ${event.title}`}
                    >
                      ✕
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* All Upcoming Events */}
        {allEvents.length > 0 && (
          <div className="space-y-3">
            <h3 className="text-sm font-semibold text-text-secondary">
              ALL EVENTS ({allEvents.length})
            </h3>
            <ul className="space-y-2 max-h-48 overflow-y-auto">
              {allEvents.map((event) => (
                <li key={event.id} className="rounded-lg border border-white/10 bg-white/5 p-2">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-medium text-text-primary truncate">{event.title}</p>
                      <p className="text-xs text-text-secondary">
                        {formatDate(event.start_time)} {formatTime(event.start_time)}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleDeleteEvent(event.id)}
                      className="
                        touch-target p-1 text-text-secondary hover:text-red-300
                        transition-colors focus-visible:outline-none focus-visible:ring-1
                        focus-visible:ring-red-400
                      "
                      aria-label={`Delete event: ${event.title}`}
                    >
                      ✕
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Modal>
  )
}
