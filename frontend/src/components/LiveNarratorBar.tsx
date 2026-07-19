import React from 'react';

interface LiveNarratorBarProps {
  venueSummary: string;
  loading: boolean;
  degradedMode: boolean;
}

export function LiveNarratorBar({
  venueSummary,
  loading,
  degradedMode,
}: LiveNarratorBarProps): React.JSX.Element {
  const hasContent = venueSummary && venueSummary.length > 0;

  return (
    <div
      role="region"
      aria-label="Real time AI venue status narration banner"
      className="w-full rounded-xl border border-slate-800 bg-gradient-to-r from-slate-900/80 via-indigo-950/30 to-slate-900/80 px-5 py-3 shadow-lg backdrop-blur-sm"
    >
      <div className="flex items-center gap-3">
        {/* AI Indicator */}
        <div className="flex items-center gap-2 shrink-0">
          <div className="relative">
            <div className={`h-2.5 w-2.5 rounded-full ${degradedMode ? 'bg-amber-500' : 'bg-emerald-500'} ${loading ? 'animate-ping' : 'animate-pulse'}`} />
            <div className={`absolute inset-0 h-2.5 w-2.5 rounded-full ${degradedMode ? 'bg-amber-500' : 'bg-emerald-500'}`} />
          </div>
          <span className="text-[10px] font-bold text-indigo-400 uppercase tracking-widest">
            AI NARRATOR
          </span>
        </div>

        {/* Separator */}
        <div className="h-4 w-px bg-slate-700 shrink-0" />

        {/* Summary Text */}
        <div className="flex-1 min-w-0">
          {loading && !hasContent ? (
            <div className="flex items-center gap-2">
              <div className="h-3 w-3 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
              <span className="text-xs text-slate-500 italic">Analyzing venue state…</span>
            </div>
          ) : hasContent ? (
            <p className="text-sm text-slate-200 font-medium truncate leading-snug">
              {venueSummary}
            </p>
          ) : (
            <p className="text-xs text-slate-500 italic">
              Waiting for first reasoning cycle…
            </p>
          )}
        </div>

        {/* Degraded Mode Badge */}
        {degradedMode && (
          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-amber-950/40 border border-amber-500/30 shrink-0">
            <svg className="w-3 h-3 text-amber-400 animate-pulse" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <span className="text-[9px] text-amber-400 font-bold uppercase tracking-wider">Degraded</span>
          </div>
        )}
      </div>
    </div>
  );
}
