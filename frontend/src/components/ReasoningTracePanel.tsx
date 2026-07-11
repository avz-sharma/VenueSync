import React from 'react';

interface ReasoningTracePanelProps {
  confidence: number;
  rationale: string;
  predictedImpact: string;
  degradedMode?: boolean;
}

export function ReasoningTracePanel({
  confidence,
  rationale,
  predictedImpact,
  degradedMode = false,
}: ReasoningTracePanelProps): React.JSX.Element {
  // Turn confidence decimal (e.g. 0.9) into percentage (90%)
  const confidencePct = Math.round(confidence * 100);

  const getConfidenceColor = (score: number) => {
    if (score >= 0.8) return 'text-cyan-400 bg-cyan-950/30 border-cyan-800/50 shadow-cyan-950/50';
    if (score >= 0.6) return 'text-amber-400 bg-amber-950/30 border-amber-800/50 shadow-amber-950/30';
    return 'text-rose-400 bg-rose-950/30 border-rose-800/50 shadow-rose-950/30';
  };

  const confidenceStyles = getConfidenceColor(confidence);

  return (
    <div className="mt-4 rounded-xl border border-violet-800/40 bg-gradient-to-br from-slate-900/90 to-indigo-950/30 p-4 shadow-inner">
      {/* Header */}
      <div className="flex items-center justify-between mb-3 pb-2 border-b border-indigo-900/30">
        <div className="flex items-center gap-2">
          {/* Sparkles / AI Icon */}
          <span className="text-violet-400 animate-pulse">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
          </span>
          <span className="text-xs font-semibold text-violet-300 uppercase tracking-wider">
            AI Judgment Trace
          </span>
        </div>

        {/* Confidence Badge */}
        <div className={`flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold border ${confidenceStyles}`}>
          <span className="h-1.5 w-1.5 rounded-full bg-current animate-ping" />
          <span>{confidencePct}% Confidence</span>
        </div>
      </div>

      {/* Rationale Body */}
      <div className="space-y-3">
        <div>
          <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider block mb-1">
            Reasoning Rationale
          </span>
          <p className="text-xs text-slate-300 leading-relaxed italic bg-slate-950/40 p-2.5 rounded-lg border border-slate-900">
            "{rationale}"
          </p>
        </div>

        {/* Predicted Impact */}
        <div>
          <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider block mb-1">
            Predicted Operational Impact
          </span>
          <div className="flex items-start gap-2 bg-cyan-950/15 border border-cyan-800/20 p-2.5 rounded-lg">
            <span className="text-cyan-400 mt-0.5 shrink-0">
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </span>
            <p className="text-xs text-cyan-200/90 leading-relaxed font-medium">
              {predictedImpact}
            </p>
          </div>
        </div>

        {/* Degraded mode indicator if active */}
        {degradedMode && (
          <div className="flex items-center gap-2 p-2 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-300">
            <span className="shrink-0">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </span>
            <span className="text-[10px] uppercase font-bold tracking-wider">
              System running in degraded (fallback) mode
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
