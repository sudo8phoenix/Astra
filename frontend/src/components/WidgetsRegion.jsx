import TasksWidget from './TasksWidget'
import CalendarWidget from './CalendarWidget'
import ActivityWidget from './ActivityWidget'
import EmailsWidget from './EmailsWidget'

/**
 * Widgets Region Component
 * Responsive grid layout for dashboard widgets
 * Mobile: vertical stack | Tablet: 2 columns | Desktop: 3 columns
 * Accessibility: semantic section structure, aria-labels for each widget
 */
export default function WidgetsRegion() {
  return (
    <section className="flex h-full min-h-0 flex-col gap-3 overflow-hidden" aria-label="Dashboard widgets">
      <header className="rounded-2xl border border-white/15 bg-white/[0.045] px-4 py-3 shadow-[0_18px_50px_rgba(2,6,23,0.26)] backdrop-blur-sm">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="font-display text-base font-semibold text-[#f6efe1]">Focus widgets</h2>
            <p className="text-xs text-[#a8bac9]">
              Quick status cards for tasks, schedule, and momentum.
            </p>
          </div>
          <div className="hidden rounded-full border border-white/15 bg-white/[0.03] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-[#9eb2c3] xl:block">
            Live overview
          </div>
        </div>
      </header>

      <div className="grid flex-1 min-h-0 gap-3 lg:grid-cols-2 lg:grid-rows-2 lg:auto-rows-fr">
        <TasksWidget />
        <CalendarWidget />
        <EmailsWidget />
        <ActivityWidget />
      </div>
    </section>
  )
}
