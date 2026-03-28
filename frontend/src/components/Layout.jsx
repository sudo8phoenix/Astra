import { useState } from 'react'
import TopNav from './TopNav'
import ChatPanel from './ChatPanel'
import WidgetsRegion from './WidgetsRegion'
import { ModalProvider, useModal } from '../lib/ModalContext'
import DashboardModal from './DashboardModal'
import NoteToSelfModal from './NoteToSelfModal'
import TasksModal from './TasksModal'
import CalendarModal from './CalendarModal'

/**
 * Main layout component
 * Semantic structure: nav + main (content)
 * Responsive: stacks vertically, top nav always visible
 */
function LayoutContent({ onLogout }) {
  const { modals, closeModal } = useModal()

  return (
    <div className="relative min-h-screen w-full overflow-hidden bg-background-DEFAULT text-text-primary">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,_rgba(0,212,255,0.16),_transparent_42%),radial-gradient(circle_at_bottom_right,_rgba(108,99,255,0.24),_transparent_42%)]"
      />

      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[80] focus:rounded-md focus:bg-background focus:px-3 focus:py-2 focus:text-text-primary"
      >
        Skip to main content
      </a>

      {/* Top Navigation */}
      <TopNav onLogout={onLogout} />

      {/* Main Content Region */}
      <main 
        id="main-content"
        className="relative z-10 flex min-h-[calc(100vh-73px)] flex-col overflow-hidden"
        role="main"
        aria-label="Dashboard"
      >
        <div className="grid h-full flex-1 grid-cols-1 gap-4 overflow-y-auto p-4 md:gap-5 md:p-6 lg:grid-cols-12">
          <section className="lg:col-span-7">
            <ChatPanel />
          </section>

          <section className="lg:col-span-5">
            <WidgetsRegion />
          </section>
        </div>
      </main>

      {/* Modals */}
      <DashboardModal isOpen={modals.dashboard} onClose={() => closeModal('dashboard')} />
      <NoteToSelfModal isOpen={modals.messages} onClose={() => closeModal('messages')} />
      <TasksModal isOpen={modals.tasks} onClose={() => closeModal('tasks')} />
      <CalendarModal isOpen={modals.calendar} onClose={() => closeModal('calendar')} />
    </div>
  )
}

export default function Layout({ onLogout }) {
  return (
    <ModalProvider>
      <LayoutContent onLogout={onLogout} />
    </ModalProvider>
  )
}
