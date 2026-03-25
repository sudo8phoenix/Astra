/**
 * Activity / Insights Widget Component
 * Features: productivity metrics, tasks completed, emails handled
 * Visualization: progress bars and key metrics
 * Accessibility: semantic structure with aria-labels for metrics
 */
export default function ActivityWidget() {
  const metrics = [
    {
      label: 'Productivity Score',
      value: 87,
      max: 100,
      color: 'gradient-primary',
      icon: '📈',
    },
    {
      label: 'Tasks Completed',
      value: 12,
      max: 20,
      color: 'bg-green-500',
      icon: '✓',
    },
    {
      label: 'Emails Processed',
      value: 28,
      max: 50,
      color: 'bg-blue-500',
      icon: '📧',
    },
  ]

  return (
    <article className="glass rounded-lg p-6 border border-white/10">
      {/* Header */}
      <h2 className="text-lg font-bold text-text-primary mb-4">Today's Activity</h2>

      {/* Metrics Grid */}
      <div className="space-y-4" role="region" aria-label="Daily activity metrics">
        {metrics.map((metric, index) => {
          const percentage = (metric.value / metric.max) * 100

          return (
            <div key={index} className="space-y-2">
              {/* Label and Icon */}
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-text-primary flex items-center gap-2">
                  <span>{metric.icon}</span>
                  {metric.label}
                </p>
                <span
                  className="text-sm font-semibold text-secondary"
                  aria-label={`${metric.value} out of ${metric.max}`}
                >
                  {metric.value}/{metric.max}
                </span>
              </div>

              {/* Progress Bar */}
              <div className="w-full bg-white/5 rounded-full h-2 overflow-hidden">
                <div
                  className={`h-full ${metric.color} transition-all duration-500`}
                  style={{ width: `${percentage}%` }}
                  role="progressbar"
                  aria-valuenow={metric.value}
                  aria-valuemin="0"
                  aria-valuemax={metric.max}
                />
              </div>
            </div>
          )
        })}
      </div>

      {/* Summary Stats */}
      <div className="mt-6 pt-4 border-t border-white/10 space-y-2">
        <p className="text-xs text-text-secondary">
          <span className="font-semibold text-text-primary">3 hours</span> productive time
        </p>
        <p className="text-xs text-text-secondary">
          <span className="font-semibold text-text-primary">Next break</span> in 45 minutes
        </p>
      </div>

      {/* View Insights Link */}
      <button
        className="
          touch-target mt-4 w-full text-center text-sm text-secondary hover:text-secondary/80
          py-2 rounded transition-colors focus-visible:outline-none
          focus-visible:ring-2 focus-visible:ring-secondary
        "
        aria-label="View detailed insights"
      >
        View insights →
      </button>
    </article>
  )
}
