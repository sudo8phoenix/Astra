import Sidebar from './Sidebar'
import ChatPanel from './ChatPanel'
import WidgetsRegion from './WidgetsRegion'

/**
 * Main layout component
 * Semantic structure: aside (sidebar) + main (content)
 * Responsive: stacks on mobile, side-by-side on desktop
 */
export default function Layout() {
  return (
    <div className="flex h-screen w-full bg-background-DEFAULT overflow-hidden">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[60] focus:rounded-md focus:bg-background focus:px-3 focus:py-2 focus:text-text-primary"
      >
        Skip to main content
      </a>

      {/* Sidebar - Navigation */}
      <Sidebar />

      {/* Main Content Region */}
      <main 
        id="main-content"
        className="flex flex-col flex-1 overflow-hidden"
        role="main"
        aria-label="Dashboard"
      >
        {/* Chat Panel - Primary Content */}
        <ChatPanel />

        {/* Widgets Region - Secondary Content */}
        <WidgetsRegion />
      </main>
    </div>
  )
}
