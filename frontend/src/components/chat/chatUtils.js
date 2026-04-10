export function createMessage(type, text) {
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    type,
    text,
    timestamp: new Date(),
    isComplete: true,
  }
}

export function formatProviderStatus(providerStatus) {
  if (!providerStatus || typeof providerStatus !== 'object') {
    return ''
  }

  const gmail = providerStatus.gmail?.status || 'unknown'
  const calendar = providerStatus.calendar?.status || 'unknown'
  return `Connection status: Gmail ${gmail}, Calendar ${calendar}.`
}

export function formatToolResultPreview(result) {
  if (!result?.success) {
    return result?.error || 'Request failed.'
  }

  const payload = result?.result || {}

  if (result.tool_name === 'create_task') {
    const task = payload.task || {}
    return `Created task: ${task.title || 'Untitled'} (${task.priority || 'medium'}, ${task.status || 'todo'})`
  }

  if (result.tool_name === 'list_tasks') {
    const count = payload.count ?? 0
    const tasks = Array.isArray(payload.tasks) ? payload.tasks.slice(0, 3).map((task) => task.title).filter(Boolean) : []
    return tasks.length > 0
      ? `${count} task(s): ${tasks.join(', ')}${count > tasks.length ? '...' : ''}`
      : `${count} task(s) found.`
  }

  if (result.tool_name === 'list_free_slots') {
    const slots = Array.isArray(payload.free_slots) ? payload.free_slots : []
    if (slots.length === 0) return 'No free slots found.'
    const preview = slots.slice(0, 2).map((slot) => {
      const start = slot?.start_time ? new Date(slot.start_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '--:--'
      const end = slot?.end_time ? new Date(slot.end_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '--:--'
      return `${start}-${end}`
    })
    return `${slots.length} free slot(s): ${preview.join(', ')}${slots.length > 2 ? '...' : ''}`
  }

  if (result.tool_name === 'get_daily_schedule') {
    const events = Array.isArray(payload.events) ? payload.events : []
    return `Loaded ${events.length} calendar event(s).`
  }

  if (result.tool_name === 'serp_search') {
    const count = payload.count ?? 0
    const items = Array.isArray(payload.results) ? payload.results.slice(0, 3) : []
    if (items.length === 0) {
      return `Google search returned ${count} result(s).`
    }
    const preview = items.map((item) => item?.title).filter(Boolean).join(', ')
    return `${count} web result(s): ${preview}${count > items.length ? '...' : ''}`
  }

  if (result.tool_name === 'save_search_note') {
    const note = payload.note || {}
    return `Saved search note for: ${note.query || 'Untitled query'}`
  }

  if (result.tool_name === 'list_search_notes') {
    const count = payload.count ?? 0
    const notes = Array.isArray(payload.notes) ? payload.notes.slice(0, 3) : []
    const preview = notes.map((note) => note?.query).filter(Boolean).join(', ')
    return preview ? `${count} saved search note(s): ${preview}${count > notes.length ? '...' : ''}` : `${count} saved search note(s).`
  }

  return JSON.stringify(payload).slice(0, 180)
}
