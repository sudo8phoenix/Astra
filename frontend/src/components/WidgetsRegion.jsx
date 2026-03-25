import TasksWidget from './TasksWidget'
import CalendarWidget from './CalendarWidget'
import ActivityWidget from './ActivityWidget'

/**
 * Widgets Region Component
 * Responsive grid layout for dashboard widgets
 * Mobile: vertical stack | Tablet: 2 columns | Desktop: 3 columns
 * Accessibility: semantic section structure, aria-labels for each widget
 */
export default function WidgetsRegion() {
  return (
    <section
      className="
        flex-1 h-1/2 md:h-auto p-4 md:p-6 gap-4 overflow-y-auto
        grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 auto-rows-max
      "
      aria-label="Dashboard widgets"
    >
      <TasksWidget />
      <CalendarWidget />
      <ActivityWidget />
    </section>
  )
}
