import Login from '../components/Login'
import { ASSISTANT_NAME } from '../lib/branding'

const highlights = [
  'Natural language orchestration for inbox, meetings, and task execution.',
  'Unified dashboard controls for email, scheduling, and daily planning.',
  'Fast OAuth bootstrap with consistent error and recovery messaging.',
]

const metrics = [
  { label: 'Connected surfaces', value: '3' },
  { label: 'Action latency target', value: '< 2s' },
  { label: 'Workflow continuity', value: '24/7' },
]

export default function LandingPage({ onLoginSuccess, initialError = '' }) {
  return (
    <main className="landing-root relative min-h-screen overflow-hidden bg-background-DEFAULT text-text-primary">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_15%_5%,_rgba(246,102,53,0.28),_transparent_34%),radial-gradient(circle_at_90%_85%,_rgba(54,181,206,0.18),_transparent_44%)]"
      />

      <div className="relative z-10 mx-auto grid min-h-screen max-w-7xl items-center gap-8 px-4 py-10 md:px-8 lg:grid-cols-[1.25fr_0.75fr] lg:gap-12">
        <section className="space-y-8 lg:pr-6">
          <div className="landing-reveal inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-[#d5dce6]">
            {ASSISTANT_NAME} command interface
          </div>

          <div className="landing-reveal landing-reveal-2 space-y-5">
            <h1 className="font-display max-w-3xl text-5xl font-semibold leading-[0.88] tracking-[-0.02em] text-[#f6f1e9] md:text-7xl">
              Agentic command, cinematic clarity.
            </h1>
            <p className="max-w-2xl text-base leading-relaxed text-[#cad5df] md:text-lg">
              Coordinate inbox, calendar, and action workflows in one live surface designed for focused execution.
            </p>
          </div>

          <div className="landing-reveal landing-reveal-3 grid gap-3 sm:grid-cols-2">
            {highlights.map((item) => (
              <div
                key={item}
                className="rounded-2xl border border-white/15 bg-white/[0.045] p-4 text-sm leading-relaxed text-[#dbe4ec] shadow-[0_18px_50px_rgba(2,6,23,0.26)] backdrop-blur-sm"
              >
                {item}
              </div>
            ))}
          </div>

          <div className="landing-reveal landing-reveal-4 grid grid-cols-3 gap-3">
            {metrics.map((item) => (
              <div key={item.label} className="rounded-2xl border border-white/15 bg-black/20 p-4 backdrop-blur-sm">
                <p className="font-display text-2xl font-semibold tracking-tight text-[#f6efe1] md:text-3xl">
                  {item.value}
                </p>
                <p className="mt-1 text-xs uppercase tracking-[0.16em] text-[#9eb2c3]">{item.label}</p>
              </div>
            ))}
          </div>

        </section>

        <section className="landing-reveal landing-reveal-4 lg:justify-self-end lg:w-full lg:max-w-md">
          <Login onLoginSuccess={onLoginSuccess} initialError={initialError} variant="panel" />
        </section>
      </div>
    </main>
  )
}
