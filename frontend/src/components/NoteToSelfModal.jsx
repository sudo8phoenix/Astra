import { useEffect, useState } from 'react'
import { apiRequest } from '../lib/apiClient'
import Modal from './Modal'

/**
 * Note to Self Modal Component
 * Features: create, view, and manage personal notes
 * Accessibility: textarea labels, focus management
 */
export default function NoteToSelfModal({ isOpen, onClose }) {
  const [notes, setNotes] = useState([])
  const [newNote, setNewNote] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  useEffect(() => {
    if (!isOpen) return

    const loadNotes = async () => {
      setLoading(true)
      setError('')
      try {
        const data = await apiRequest('/api/v1/notes', { method: 'GET' }).catch(() => [])
        setNotes(Array.isArray(data) ? data : [])
      } catch (err) {
        setError('Unable to load notes')
      } finally {
        setLoading(false)
      }
    }

    loadNotes()
  }, [isOpen])

  const handleAddNote = async () => {
    if (!newNote.trim()) return

    try {
      setError('')
      setSuccess('')
      setLoading(true)

      const note = await apiRequest('/api/v1/notes', {
        method: 'POST',
        body: JSON.stringify({
          title: 'Quick Note',
          content: newNote,
          created_at: new Date().toISOString(),
        }),
      })

      setNotes([note, ...notes])
      setNewNote('')
      setSuccess('Note added successfully!')
      setTimeout(() => setSuccess(''), 3000)
    } catch (err) {
      setError('Failed to add note')
    } finally {
      setLoading(false)
    }
  }

  const handleDeleteNote = async (noteId) => {
    try {
      await apiRequest(`/api/v1/notes/${noteId}`, { method: 'DELETE' })
      setNotes(notes.filter(n => n.id !== noteId))
      setSuccess('Note deleted')
      setTimeout(() => setSuccess(''), 2000)
    } catch (err) {
      setError('Failed to delete note')
    }
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="💬 Notes to Self">
      <div className="space-y-6">
        {/* Add Note Section */}
        <div className="space-y-3">
          <label htmlFor="note-input" className="block text-sm font-semibold text-text-secondary">
            CREATE A NOTE
          </label>
          <textarea
            id="note-input"
            value={newNote}
            onChange={(e) => setNewNote(e.target.value)}
            placeholder="What's on your mind? Add a quick reminder or note..."
            className="
              w-full rounded-lg border border-white/15 bg-white/5 px-4 py-3
              text-text-primary placeholder:text-text-secondary
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-secondary
              resize-none
            "
            rows={3}
            disabled={loading}
          />
          <button
            type="button"
            onClick={handleAddNote}
            disabled={!newNote.trim() || loading}
            className="
              w-full py-2.5 px-4 rounded-lg text-sm font-semibold
              border border-secondary/40 bg-secondary/10 text-secondary
              hover:bg-secondary/20 disabled:opacity-50 disabled:cursor-not-allowed
              transition-all duration-200
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-secondary
            "
          >
            {loading ? 'Saving...' : '+ Add Note'}
          </button>
        </div>

        {/* Status Messages */}
        {error && (
          <div className="rounded-lg border border-red-300/30 bg-red-500/10 p-3">
            <p className="text-sm text-red-200">{error}</p>
          </div>
        )}
        {success && (
          <div className="rounded-lg border border-green-300/30 bg-green-500/10 p-3">
            <p className="text-sm text-green-200">{success}</p>
          </div>
        )}

        {/* Notes List */}
        <div className="space-y-3">
          <h3 className="text-sm font-semibold text-text-secondary">
            YOUR NOTES ({notes.length})
          </h3>
          {notes.length === 0 ? (
            <p className="text-center py-8 text-text-secondary text-sm">
              No notes yet. Create one above to get started!
            </p>
          ) : (
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {notes.map((note) => (
                <div
                  key={note.id}
                  className="rounded-lg border border-white/10 bg-white/5 p-3 space-y-2"
                >
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-sm text-text-primary flex-1">{note.content}</p>
                    <button
                      type="button"
                      onClick={() => handleDeleteNote(note.id)}
                      className="
                        touch-target p-1 text-text-secondary hover:text-red-300
                        transition-colors focus-visible:outline-none focus-visible:ring-1
                        focus-visible:ring-red-400
                      "
                      aria-label={`Delete note: ${note.content.substring(0, 20)}`}
                    >
                      ✕
                    </button>
                  </div>
                  <p className="text-xs text-text-secondary">
                    {new Date(note.created_at).toLocaleDateString()}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </Modal>
  )
}
