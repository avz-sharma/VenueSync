import React from 'react';

interface ReasoningTracePanelProps {
  confidence: number;
  rationale: string;
  predictedImpact: string;
  degradedMode?: boolean;
  actionType: string;
  targetZones: string[];
}

export function ReasoningTracePanel({
  confidence,
  rationale,
  predictedImpact,
  degradedMode = false,
  actionType,
}: ReasoningTracePanelProps): React.JSX.Element {
  const confidencePct = Math.round(confidence * 100);

  const getConfidenceColor = (score: number) => {
    if (score >= 0.8) return 'text-emerald-400 bg-emerald-950/40 border-emerald-500/30';
    if (score >= 0.6) return 'text-amber-400 bg-amber-950/40 border-amber-500/30';
    return 'text-red-400 bg-red-950/40 border-red-500/30';
  };

  const getRuleCheck = (type: string) => {
    if (type.includes('redirect') || type.includes('crowd')) return 'Rule #45.1.A - Congestion Protocol';
    if (type.includes('medical')) return 'Rule #12.4.C - Medical Emergency Protocol';
    if (type.includes('security')) return 'Rule #8.9.B - Security Escalation Protocol';
    if (type.includes('exit') || type.includes('evac')) return 'Rule #1.1.A - Critical Evacuation Protocol';
    return 'Rule #0.0.X - Standard Operational Protocol';
  };

  // Safe Parsing Logic with Fallbacks
  let trigger = "Telemetry anomaly detected.";
  let strategy = rationale;
  try {
    const parts = rationale.split('. ');
    if (parts.length > 1) {
      trigger = parts[0] + '.';
      strategy = parts.slice(1).join('. ');
    } else {
      if (rationale.toLowerCase().includes('critical') || rationale.includes('%') || rationale.toLowerCase().includes('incident')) {
        trigger = rationale;
        strategy = "Strategy formulated based on immediate telemetry.";
      }
    }
    
    // Override for degraded mode handling
    if (degradedMode) {
      trigger = "SYSTEM DEGRADED - TELEMETRY UNRELIABLE";
      strategy = rationale;
    }
  } catch (err) {
    // Graceful degraded mode / parsing error fallback
    trigger = "Unknown Telemetry State";
    strategy = rationale;
  }

  // Highlight target zones dynamically in the strategy text
  const renderStrategyWithHighlights = (text: string) => {
    try {
      const regex = /(Gate (?:North|South|East|West)|(?:North|South|East|West) Gate|Concourse [A-Z]|Main Stand|VIP Lounge|Food Court)/gi;
      const parts = text.split(regex);
      return (
        <>
          {parts.map((part, i) => {
            if (/^(Gate (?:North|South|East|West)|(?:North|South|East|West) Gate|Concourse [A-Z]|Main Stand|VIP Lounge|Food Court)$/i.test(part)) {
              return <strong key={i} className="text-slate-100 font-bold bg-slate-800/80 px-1 py-0.5 rounded">{part}</strong>;
            }
            return <span key={i}>{part}</span>;
          })}
        </>
      );
    } catch (e) {
      return text;
    }
  };

  return (
    <div className="mt-4 rounded-xl border border-slate-800 bg-slate-900/60 p-5 shadow-2xl relative">
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-2">
          <span className="text-indigo-400 animate-pulse">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
          </span>
          <span className="text-xs font-bold text-indigo-400 uppercase tracking-wider">
            AI Logic Trace
          </span>
        </div>

        {/* Reliability Badge */}
        <div className={`flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${getConfidenceColor(confidence)}`}>
          <span className="h-1.5 w-1.5 rounded-full bg-current animate-ping" />
          <span>{confidencePct}% Confidence</span>
        </div>
      </div>

      {/* Logic Tree Topology Timeline */}
      <div className="relative pl-6 space-y-6 before:absolute before:inset-y-0 before:left-[11px] before:w-[2px] before:bg-slate-800">
        
        {/* Step 1: Telemetry Trigger */}
        <div className="relative">
          <div className="absolute -left-[27px] top-1 h-2.5 w-2.5 rounded-full bg-red-500 ring-4 ring-slate-900 z-10" />
          <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider block mb-1">
            Step 1: Telemetry Trigger
          </span>
          <p className="text-sm text-slate-200 font-medium">
            {trigger}
          </p>
        </div>

        {/* Step 2: Deterministic Rule Check */}
        <div className="relative">
          <div className="absolute -left-[27px] top-1 h-2.5 w-2.5 rounded-full bg-blue-500 ring-4 ring-slate-900 z-10" />
          <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider block mb-1">
            Step 2: Rule Verification
          </span>
          <p className="text-sm text-slate-300 font-mono bg-slate-800/50 p-2 rounded border border-slate-700/50">
            {getRuleCheck(actionType)}
          </p>
        </div>

        {/* Step 3: LLM Rationale */}
        <div className="relative">
          <div className="absolute -left-[27px] top-1 h-2.5 w-2.5 rounded-full bg-emerald-500 ring-4 ring-slate-900 z-10" />
          <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider block mb-1">
            Step 3: Tactical Strategy
          </span>
          <p className="text-sm text-slate-300 leading-relaxed italic bg-slate-900 p-3 rounded-lg border border-slate-700/50 shadow-inner">
            {renderStrategyWithHighlights(strategy)}
          </p>
        </div>
      </div>

      {/* Predicted Impact Footer */}
      <div className="mt-6 pt-4 border-t border-slate-800/80">
        <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider block mb-2">
          Predicted Operational Impact
        </span>
        <div className="flex items-start gap-2 bg-blue-950/30 border border-blue-900/50 p-3 rounded-lg shadow-sm">
          <span className="text-blue-400 mt-0.5 shrink-0">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </span>
          <p className="text-xs text-blue-200 leading-relaxed font-medium">
            {predictedImpact}
          </p>
        </div>
      </div>

      {/* Degraded mode indicator if active */}
      {degradedMode && (
        <div className="mt-4 flex items-center gap-2 p-2 rounded-lg bg-amber-950/40 border border-amber-500/30 text-amber-400">
          <span className="shrink-0">
            <svg className="w-4 h-4 animate-pulse" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </span>
          <span className="text-[10px] uppercase font-bold tracking-wider">
            System running in degraded (fallback) mode
          </span>
        </div>
      )}
    </div>
  );
}
