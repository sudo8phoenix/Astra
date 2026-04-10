import { useState } from 'react'
import TopNav from './TopNav'
import ChatPanel from './ChatPanel'
import WidgetsRegion from './WidgetsRegion'
import { ModalProvider, useModal } from '../lib/ModalContext'
import DashboardModal from './DashboardModal'
import NoteToSelfModal from './NoteToSelfModal'
import TasksModal from './TasksModal'
import CalendarModal from './CalendarModal'
import UserProfileModal from './UserProfileModal'

/**
 * Main layout component
 * Semantic structure: nav + main (content)
 * Responsive: stacks vertically, top nav always visible
 */
function LayoutContent({ onLogout, onNavigate }) {
  const { modals, closeModal } = useModal()

  return (
    <div className="relative h-screen w-full overflow-hidden bg-background-DEFAULT text-text-primary">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_15%_5%,_rgba(246,102,53,0.22),_transparent_34%),radial-gradient(circle_at_90%_85%,_rgba(54,181,206,0.16),_transparent_44%)]"
      />

      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[80] focus:rounded-md focus:bg-background focus:px-3 focus:py-2 focus:text-text-primary"
      >
        Skip to main content
      </a>

      {/* Top Navigation */}
      <TopNav onLogout={onLogout} onNavigate={onNavigate} />

      {/* Main Content Region */}
      <main 
        id="main-content"
        className="relative z-10 flex h-[calc(100svh-73px)] min-h-0 flex-col overflow-hidden"
        role="main"
        aria-label="Dashboard"
      >
        <div className="grid h-full min-h-0 grid-cols-1 gap-4 px-4 py-4 md:gap-5 md:px-6 md:py-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(380px,0.82fr)]">
          <section className="min-h-0">
            <ChatPanel />
          </section>

          <section className="min-h-0">
            <WidgetsRegion />
          </section>
        </div>
      </main>

      {/* Modals */}
      <DashboardModal isOpen={modals.dashboard} onClose={() => closeModal('dashboard')} />
      <NoteToSelfModal isOpen={modals.messages} onClose={() => closeModal('messages')} />
      <TasksModal isOpen={modals.tasks} onClose={() => closeModal('tasks')} />
      <CalendarModal isOpen={modals.calendar} onClose={() => closeModal('calendar')} />
      <UserProfileModal isOpen={modals.profile} onClose={() => closeModal('profile')} />
    </div>
  )
}

export default function Layout({ onLogout, onNavigate }) {
  return (
    <ModalProvider>
      <LayoutContent onLogout={onLogout} onNavigate={onNavigate} />
    </ModalProvider>
  )
}
