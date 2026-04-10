export default function TypingIndicator({ phase = 'Thinking...' }) {
  return (
    <div className="flex gap-3 animate-fade-in" role="status" aria-label="AI is typing" aria-live="polite">
      <div className="mt-0.5 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full border border-white/20 bg-white/[0.03]">
        <span className="text-[9px] font-semibold uppercase tracking-[0.08em] text-[#a7b8c7]">AI</span>
      </div>
      <div className="max-w-xs rounded-xl border border-white/12 bg-white/[0.03] px-3.5 py-3 text-[#dbe6f0] shadow-[0_6px_18px_rgba(2,6,23,0.16)] md:max-w-md">
        <p className="mb-2 text-[10px] uppercase tracking-[0.12em] text-[#8ea3b5]">{phase}</p>
        <div className="typing-indicator">
          <span aria-hidden="true" />
          <span aria-hidden="true" />
          <span aria-hidden="true" />
        </div>
      </div>
    </div>
  )
}
