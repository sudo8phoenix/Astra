import { useEffect, useMemo, useState } from 'react'
import { apiRequest } from '../lib/apiClient'
import { createPortal } from 'react-dom'

/**
 * Calendar Widget Component
 * Features: daily schedule view, highlight current time, color-coded events
 * Accessibility: semantic time elements, aria-labels for events
 * Responsive: adapts to widget container
 */
export default function CalendarWidget() {
  const startDate = new Date()
  startDate.setDate(startDate.getDate() + 2)  // Default to March 30th
  startDate.setHours(0, 0, 0, 0)
  
  const now = new Date()
  const [displayDate, setDisplayDate] = useState(startDate)
  const [events, setEvents] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')
  const [freeSlots, setFreeSlots] = useState([])
  const [showFreeSlots, setShowFreeSlots] = useState(false)
  const [loadingSlots, setLoadingSlots] = useState(false)
  const [successMessage, setSuccessMessage] = useState('')
  const [showEventModal, setShowEventModal] = useState(false)
  const [eventForm, setEventForm] = useState({ title: '', startTime: '', duration: 30 })
  const [isCreatingEvent, setIsCreatingEvent] = useState(false)

  useEffect(() => {
    let isMounted = true

    const loadSchedule = async () => {
      setIsLoading(true)
      setError('')

      const dateStr = displayDate.toISOString().slice(0, 10)
      const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'

      try {
        const payload = await apiRequest('/api/v1/calendar/daily-schedule', {
          method: 'POST',
          body: JSON.stringify({ date: dateStr, timezone }),
        })

        const apiEvents = Array.isArray(payload?.events)
          ? payload.events
          : Array.isArray(payload?.data?.events)
            ? payload.data.events
            : []

        if (!isMounted) {
          return
        }

        setEvents(apiEvents)
      } catch (loadError) {
        if (!isMounted) {
          return
        }

        const message = loadError instanceof Error ? loadError.message : 'Unable to load calendar events.'
        setError(message)
      } finally {
        if (isMounted) {
          setIsLoading(false)
        }
      }
    }

    loadSchedule()

    const onAssistantDataUpdated = (event) => {
      const tools = event?.detail?.tools || []
      if (tools.includes('list_free_slots') || tools.includes('get_daily_schedule') || tools.includes('create_event') || tools.includes('update_event')) {
        loadSchedule()
      }
    }

    window.addEventListener('assistant:data-updated', onAssistantDataUpdated)

    return () => {
      isMounted = false
      window.removeEventListener('assistant:data-updated', onAssistantDataUpdated)
    }
  }, [displayDate])

  const loadFreeSlots = async () => {
    setLoadingSlots(true)
    setError('')

    try {
      const dateStr = displayDate.toISOString().slice(0, 10)
      const payload = await apiRequest('/api/v1/calendar/free-slots', {
        method: 'POST',
        body: JSON.stringify({ date: dateStr, min_duration_minutes: 30 }),
      })

      const slots = Array.isArray(payload?.free_slots) ? payload.free_slots : []
      setFreeSlots(slots)
      setShowFreeSlots(true)
      if (slots.length === 0) {
        setSuccessMessage('No free slots available for this day')
        setTimeout(() => setSuccessMessage(''), 3000)
      }
    } catch (slotError) {
      const message = slotError instanceof Error ? slotError.message : 'Failed to load free slots'
      setError(message)
    } finally {
      setLoadingSlots(false)
    }
  }

  const refreshSchedule = async () => {
    setIsLoading(true)
    setError('')
    setFreeSlots([])
    setShowFreeSlots(false)

    const dateStr = displayDate.toISOString().slice(0, 10)
    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'

    try {
      const payload = await apiRequest('/api/v1/calendar/daily-schedule', {
        method: 'POST',
        body: JSON.stringify({ date: dateStr, timezone }),
      })

      const apiEvents = Array.isArray(payload?.events)
        ? payload.events
        : Array.isArray(payload?.data?.events)
          ? payload.data.events
          : []

      setEvents(apiEvents)
      setSuccessMessage('Schedule refreshed')
      setTimeout(() => setSuccessMessage(''), 2000)
    } catch (loadError) {
      const message = loadError instanceof Error ? loadError.message : 'Failed to refresh schedule'
      setError(message)
    } finally {
      setIsLoading(false)
    }
  }

  const goToPreviousDay = () => {
    const prev = new Date(displayDate)
    prev.setDate(prev.getDate() - 1)
    setDisplayDate(prev)
    setShowFreeSlots(false)
  }

  const goToNextDay = () => {
    const next = new Date(displayDate)
    next.setDate(next.getDate() + 1)
    setDisplayDate(next)
    setShowFreeSlots(false)
  }

  const goToToday = () => {
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    setDisplayDate(today)
    setShowFreeSlots(false)
  }

  const createEvent = async () => {
    if (!eventForm.title.trim() || !eventForm.startTime) {
      setError('Please fill in event title and start time')
      return
    }

    setIsCreatingEvent(true)
    setError('')

    try {
      const [hours, minutes] = eventForm.startTime.split(':').map(Number)
      const startDate = new Date(displayDate)
      startDate.setHours(hours, minutes, 0, 0)

      const endDate = new Date(startDate)
      endDate.setMinutes(endDate.getMinutes() + parseInt(eventForm.duration, 10))

      const payload = await apiRequest('/api/v1/calendar/events', {
        method: 'POST',
        body: JSON.stringify({
          title: eventForm.title,
          start_time: startDate.toISOString(),
          end_time: endDate.toISOString(),
          description: 'Created from widget',
        }),
      })

      setSuccessMessage(`Event "${eventForm.title}" created successfully`)
      setEventForm({ title: '', startTime: '', duration: 30 })
      setShowEventModal(false)
      setTimeout(() => setSuccessMessage(''), 3000)
      
      // Refresh schedule
      const dateStr = displayDate.toISOString().slice(0, 10)
      const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
      const refreshPayload = await apiRequest('/api/v1/calendar/daily-schedule', {
        method: 'POST',
        body: JSON.stringify({ date: dateStr, timezone }),
      })
      const apiEvents = Array.isArray(refreshPayload?.events) ? refreshPayload.events : []
      setEvents(apiEvents)
    } catch (createError) {
      const message = createError instanceof Error ? createError.message : 'Failed to create event'
      setError(message)
    } finally {
      setIsCreatingEvent(false)
    }
  }

  const isToday = displayDate.toDateString() === new Date().toDateString()

  const currentTime = now.getHours() * 60 + now.getMinutes()

  const createEventModal = showEventModal && typeof document !== 'undefined'
    ? createPortal(
      <div className="fixed inset-0 z-[999] isolate flex items-center justify-center bg-black px-4">
        <div className="relative mx-4 w-full max-w-sm overflow-hidden rounded-2xl border border-secondary/30 bg-slate-950 p-6 shadow-[0_24px_80px_rgba(2,6,23,0.95)] animate-scale-pop">
          <div className="pointer-events-none absolute -top-16 -right-14 h-40 w-40 rounded-full bg-secondary/20 blur-3xl" />
          <div className="pointer-events-none absolute -bottom-20 -left-16 h-44 w-44 rounded-full bg-green-400/15 blur-3xl" />

          <div className="relative z-10">
            <h4 className="mb-4 text-base font-semibold text-text-primary">Create Event</h4>

            {error && (
              <p className="mb-3 rounded-lg border border-red-300/40 bg-red-900 px-3 py-2 text-xs text-red-100">
                {error}
              </p>
            )}

            <div className="space-y-3 rounded-xl border border-white/20 bg-slate-950 p-3">
              <div>
                <label className="mb-1 block text-xs font-semibold text-text-primary">
                  Event title
                </label>
                <input
                  type="text"
                  value={eventForm.title}
                  onChange={(e) => setEventForm({ ...eventForm, title: e.target.value })}
                  placeholder="e.g., Team meeting"
                  className="
                    w-full rounded-lg border border-white/25 bg-slate-900 px-3 py-2
                    text-sm text-text-primary placeholder:text-text-tertiary
                    focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-secondary
                  "
                />
              </div>

              <div>
                <label className="mb-1 block text-xs font-semibold text-text-primary">
                  Start time
                </label>
                <input
                  type="time"
                  value={eventForm.startTime}
                  onChange={(e) => setEventForm({ ...eventForm, startTime: e.target.value })}
                  className="
                    w-full rounded-lg border border-white/25 bg-slate-900 px-3 py-2
                    text-sm text-text-primary
                    focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-secondary
                  "
                />
              </div>

              <div>
                <label className="mb-1 block text-xs font-semibold text-text-primary">
                  Duration (minutes)
                </label>
                <select
                  value={eventForm.duration}
                  onChange={(e) => setEventForm({ ...eventForm, duration: e.target.value })}
                  className="
                    w-full rounded-lg border border-white/25 bg-slate-900 px-3 py-2
                    text-sm text-text-primary
                    focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-secondary
                  "
                >
                  <option value="15">15 minutes</option>
                  <option value="30">30 minutes</option>
                  <option value="60">1 hour</option>
                  <option value="90">1.5 hours</option>
                  <option value="120">2 hours</option>
                </select>
              </div>
            </div>

            <div className="mt-4 flex gap-2">
              <button
                type="button"
                onClick={() => setShowEventModal(false)}
                className="
                  flex-1 rounded-lg border border-white/25 bg-slate-900 px-3 py-2
                  text-xs font-semibold text-text-secondary hover:bg-slate-800
                  transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-secondary
                "
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={createEvent}
                disabled={isCreatingEvent}
                className="
                  flex-1 rounded-lg border border-green-300/40 bg-green-600/30 px-3 py-2
                  text-xs font-semibold text-green-100 hover:bg-green-500/40
                  disabled:opacity-50 transition-colors
                  focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green-400
                "
              >
                {isCreatingEvent ? '...' : 'Create'}
              </button>
            </div>
          </div>
        </div>
      </div>,
      document.body,
    )
    : null

  const displayEvents = useMemo(
    () => events.map((event, index) => {
      const startDate = new Date(event.start_time)
      const endDate = new Date(event.end_time)

      return {
        id: event.id || `${index}-${event.title}`,
        title: event.title || 'Untitled event',
        start: startDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        end: endDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        startMinutes: (startDate.getHours() * 60) + startDate.getMinutes(),
        endMinutes: (endDate.getHours() * 60) + endDate.getMinutes(),
      }
    }),
    [events],
  )

  return (
    <article className="glass rounded-xl border border-white/10 p-5">
      {/* Header with Navigation */}
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold text-text-primary">
            {isToday ? "Today's schedule" : 'Schedule'}
          </h3>
          <p className="text-xs text-text-secondary">Focus on the next confirmed blocks.</p>
        </div>
        <button
          type="button"
          onClick={refreshSchedule}
          disabled={isLoading}
          className="rounded p-1.5 hover:bg-white/5 transition-colors"
          aria-label="Refresh schedule"
          title="Refresh schedule"
        >
          {isLoading ? '⟳' : '↻'}
        </button>
      </div>

      {/* Date Navigation */}
      <div className="mb-3 flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={goToPreviousDay}
          className="
            touch-target rounded px-2 py-1 text-xs border border-white/15 bg-white/5
            hover:bg-white/10 transition-colors
          "
          aria-label="Previous day"
        >
          ← Prev
        </button>
        <div className="text-xs text-text-secondary">
          {displayDate.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}
        </div>
        <div className="flex gap-2">
          {!isToday && (
            <button
              type="button"
              onClick={goToToday}
              className="
                touch-target rounded px-2 py-1 text-xs border border-white/15 bg-white/5
                hover:bg-white/10 transition-colors
              "
              aria-label="Go to today"
            >
              Today
            </button>
          )}
          <button
            type="button"
            onClick={goToNextDay}
            className="
              touch-target rounded px-2 py-1 text-xs border border-white/15 bg-white/5
              hover:bg-white/10 transition-colors
            "
            aria-label="Next day"
          >
            Next →
          </button>
        </div>
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

      {/* Compact Schedule View */}
      {isLoading ? (
        <div className="rounded-lg border border-white/10 bg-white/5 px-4 py-5 text-center animate-fade-in">
          <p className="text-sm font-semibold text-text-primary">Loading schedule...</p>
        </div>
      ) : displayEvents.length === 0 ? (
        <div className="rounded-lg border border-dashed border-white/20 bg-white/5 px-4 py-5 text-center animate-fade-in">
          <p className="text-sm font-semibold text-text-primary">No meetings scheduled</p>
          <p className="mt-1 text-xs text-text-secondary">
            You have a clear calendar window right now.
          </p>
        </div>
      ) : (
        <div className="space-y-1" role="list" aria-label={`Events for ${displayDate.toDateString()}`}>
          {displayEvents.map((event) => {
            const isCurrentEvent = isToday && currentTime >= event.startMinutes && currentTime < event.endMinutes

            return (
              <div
                key={event.id}
                className={`
                  min-h-11 flex items-center gap-2 rounded border px-3 py-2 text-sm
                  transition-all bg-blue-500/15 border-blue-400/40 text-blue-100
                  ${isCurrentEvent ? 'ring-2 ring-secondary/50 glow' : ''}
                `}
                role="listitem"
                aria-label={`${event.title} from ${event.start} to ${event.end}`}
              >
                <time className="w-12 flex-shrink-0 font-mono font-semibold">
                  {event.start}
                </time>
                <span className="flex-1 truncate">{event.title}</span>
                {isCurrentEvent && (
                  <span className="text-xs font-bold animate-pulse">Now</span>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Free Slots Section */}
      {showFreeSlots && (
        <div className="mt-4 pt-4 border-t border-white/10 space-y-2">
          <p className="text-xs font-semibold text-text-primary">Available slots:</p>
          {loadingSlots ? (
            <p className="text-xs text-text-secondary">Loading...</p>
          ) : freeSlots.length === 0 ? (
            <p className="text-xs text-text-tertiary">No free slots available</p>
          ) : (
            <div className="space-y-1">
              {freeSlots.slice(0, 3).map((slot, idx) => (
                <p key={idx} className="text-xs text-text-secondary">
                  {slot.start_time && new Date(slot.start_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} - 
                  {slot.end_time && new Date(slot.end_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </p>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Action Buttons */}
      <div className="mt-4 flex flex-col gap-2">
        <div className="flex gap-2">
          <button
            type="button"
            onClick={loadFreeSlots}
            disabled={loadingSlots}
            className="
              touch-target flex-1 text-center text-xs font-semibold
              rounded border border-secondary/30 bg-secondary/10 text-secondary
              hover:bg-secondary/20 disabled:opacity-50 transition-colors
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-secondary
            "
            aria-label="Find free slots"
          >
            {loadingSlots ? '...' : '🔍 Free slots'}
          </button>
          <button
            type="button"
            onClick={() => setShowEventModal(true)}
            className="
              touch-target flex-1 text-center text-xs font-semibold
              rounded border border-green-300/30 bg-green-500/10 text-green-200
              hover:bg-green-500/20 transition-colors
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green-400
            "
            aria-label="Create new event"
          >
            ➕ New event
          </button>
        </div>
        <button
          type="button"
          onClick={() => setShowEventModal(true)}
          className="
            touch-target w-full text-center text-xs font-semibold
            rounded border border-green-300/30 bg-green-500/10 text-green-200
            hover:bg-green-500/20 transition-colors
            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green-400
          "
          aria-label="Add new event"
        >
          ➕ Add event
        </button>
      </div>

      {/* Create Event Modal */}
      {createEventModal}
    </article>
  )
}
