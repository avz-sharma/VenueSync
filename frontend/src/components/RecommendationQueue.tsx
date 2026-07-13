import React from 'react';
import type { ActionRecommendation, ReasoningCycleOutput } from '../types';
import { ReasoningTracePanel } from './ReasoningTracePanel';

interface RecommendationQueueProps {
  reasoningOutput: ReasoningCycleOutput | null;
  loading: boolean;
  onApprove: (actionId: string) => Promise<void>;
  onDismiss: (actionId: string) => void;
  approvedIds: Set<string>;
  dismissedIds: Set<string>;
}

export function RecommendationQueue({
  reasoningOutput,
  loading,
  onApprove,
  onDismiss,
  approvedIds,
  dismissedIds,
}: RecommendationQueueProps): React.JSX.Element {
  // Action approval loading states (per action ID)
  const [approvingIds, setApprovingIds] = React.useState<Set<string>>(new Set());

  const handleApproveClick = async (actionId: string) => {
    setApprovingIds((prev) => {
      const next = new Set(prev);
      next.add(actionId);
      return next;
    });
    try {
      await onApprove(actionId);
    } finally {
      setApprovingIds((prev) => {
        const next = new Set(prev);
        next.delete(actionId);
        return next;
      });
    }
  };

  // Helper to make action type names human-readable
  const formatActionType = (type: string) => {
    switch (type) {
      case 'redirect_crowd':
        return 'Redirect Crowd Flow';
      case 'dispatch_security':
        return 'Dispatch Security Team';
      case 'dispatch_medical':
        return 'Deploy Medical Response';
      case 'open_emergency_exit':
        return 'Open Emergency Exit Gates';
      case 'broadcast_announcement':
        return 'Broadcast PA Announcement';
      default:
        return type
          .split('_')
          .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
          .join(' ');
    }
  };

  const getActionStyles = (type: string) => {
    switch (type) {
      case 'open_emergency_exit':
      case 'dispatch_medical':
        return {
          badge: 'bg-red-50 text-red-600 border-red-200',
          indicator: 'bg-red-500 shadow-red-500/50',
          cardBorder: 'border-red-200 hover:border-red-300 ring-1 ring-red-50 hover:ring-red-100',
        };
      case 'dispatch_security':
        return {
          badge: 'bg-orange-50 text-orange-600 border-orange-200',
          indicator: 'bg-orange-500 shadow-orange-500/50',
          cardBorder: 'border-orange-200 hover:border-orange-300 ring-1 ring-orange-50 hover:ring-orange-100',
        };
      case 'redirect_crowd':
        return {
          badge: 'bg-blue-50 text-blue-600 border-blue-200',
          indicator: 'bg-blue-500 shadow-blue-500/50',
          cardBorder: 'border-blue-200 hover:border-blue-300 ring-1 ring-blue-50 hover:ring-blue-100',
        };
      default:
        return {
          badge: 'bg-slate-100 text-slate-700 border-slate-200',
          indicator: 'bg-slate-500 shadow-slate-500/50',
          cardBorder: 'border-slate-200 hover:border-slate-300',
        };
    }
  };

  // Filter out dismissed actions and sort by priority ascending (1 is highest)
  const activeActions: ActionRecommendation[] = React.useMemo(() => {
    if (!reasoningOutput?.actions) return [];
    return [...reasoningOutput.actions]
      .filter((action) => !dismissedIds.has(action.id))
      .sort((a, b) => a.priority - b.priority);
  }, [reasoningOutput, dismissedIds]);

  // Loading skeleton state
  if (loading) {
    return (
      <div className="flex flex-col h-full space-y-4">
        {[1, 2].map((i) => (
          <div key={i} className="border border-slate-200 bg-slate-50 rounded-xl p-4 space-y-4 animate-pulse">
            <div className="flex items-center justify-between">
              <div className="h-5 w-36 bg-slate-200 rounded" />
              <div className="h-5 w-16 bg-slate-200 rounded-full" />
            </div>
            <div className="h-4 w-full bg-slate-200 rounded" />
            <div className="h-24 w-full bg-slate-100 rounded-lg" />
            <div className="flex gap-2 pt-2">
              <div className="h-9 w-24 bg-slate-200 rounded-lg" />
              <div className="h-9 flex-1 bg-slate-200 rounded-lg" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {reasoningOutput?.degraded_mode && (
        <div className="mb-4 inline-flex items-center self-start gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-50 border border-amber-200 text-amber-700">
          <span className="h-1.5 w-1.5 rounded-full bg-amber-500 animate-ping" />
          <span>Degraded Mode Active</span>
        </div>
      )}

      {/* Action cards list */}
      <div className="space-y-4 overflow-y-auto h-full pr-1 custom-scrollbar">
        {activeActions.length === 0 ? (
          <div className="h-full border border-dashed border-slate-200 bg-slate-50 rounded-xl p-8 text-center flex flex-col items-center justify-center">
            <div className="h-12 w-12 rounded-full bg-emerald-50 flex items-center justify-center text-emerald-500 mb-4 border border-emerald-100 shadow-sm">
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <h3 className="font-semibold text-slate-900">No Action Required</h3>
            <p className="text-xs text-slate-500 mt-2 max-w-[250px]">
              All venue zones are operating within safe occupancy thresholds. No crowd redirects or dispatches are recommended.
            </p>
          </div>
        ) : (
          activeActions.map((action) => {
            const isApproved = approvedIds.has(action.id);
            const isApproving = approvingIds.has(action.id);
            const styles = getActionStyles(action.action_type);

            return (
              <div
                key={action.id}
                className={`border rounded-xl bg-white p-4 transition-all duration-300 flex flex-col justify-between shadow-sm ${
                  isApproved
                    ? 'border-emerald-200 bg-emerald-50/50 opacity-90 shadow-none'
                    : styles.cardBorder
                }`}
              >
                <div>
                  {/* Priority & Badge Header */}
                  <div className="flex items-center justify-between mb-3 gap-2">
                    <div className="flex items-center gap-2">
                      {/* Priority Dot */}
                      <span className={`inline-flex items-center justify-center h-6 w-6 rounded-lg text-xs font-black bg-slate-100 border border-slate-200 text-slate-600`}>
                        P{action.priority}
                      </span>
                      <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-bold tracking-wide uppercase border ${styles.badge}`}>
                        <span className={`h-1.5 w-1.5 rounded-full ${styles.indicator}`} />
                        <span>{formatActionType(action.action_type)}</span>
                      </span>
                    </div>

                    <span className="text-[10px] text-slate-400 font-mono tracking-wider">
                      ID: {action.id.slice(0, 8)}
                    </span>
                  </div>

                  {/* Target zones details */}
                  <div className="mb-3">
                    <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider block mb-1">
                      Target Zones
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      {action.target_zones.map((zone) => (
                        <span
                          key={zone}
                          className="px-2 py-0.5 rounded bg-slate-100 border border-slate-200 text-slate-600 font-mono text-[11px]"
                        >
                          {zone}
                        </span>
                      ))}
                    </div>
                  </div>

                  {/* Reasoning trace block */}
                  <ReasoningTracePanel
                    confidence={action.confidence}
                    rationale={action.rationale}
                    predictedImpact={action.predicted_impact}
                    degradedMode={reasoningOutput?.degraded_mode}
                    actionType={action.action_type}
                    targetZones={action.target_zones}
                  />
                </div>

                {/* Card footer control buttons */}
                <div className="flex items-center justify-between gap-2 mt-4 pt-4 border-t border-slate-100">
                  {isApproved ? (
                    <div className="flex items-center gap-2 text-emerald-600 font-semibold text-xs w-full justify-center bg-emerald-50 py-2 border border-emerald-100 rounded-lg">
                      <svg className="w-4 h-4 shrink-0 animate-bounce" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                      </svg>
                      <span>Action Approved & Dispatched</span>
                    </div>
                  ) : (
                    <>
                      <button
                        onClick={() => onDismiss(action.id)}
                        disabled={isApproving}
                        className="px-4 py-2 border border-slate-200 bg-white text-slate-600 hover:text-slate-900 hover:bg-slate-50 hover:border-slate-300 disabled:opacity-50 disabled:pointer-events-none rounded-lg text-xs font-semibold transition-all shrink-0"
                      >
                        Dismiss
                      </button>
                      <button
                        onClick={() => handleApproveClick(action.id)}
                        disabled={isApproving}
                        className="w-full flex items-center justify-center gap-1.5 px-4 py-2 text-xs font-bold text-white bg-slate-900 hover:bg-slate-800 disabled:opacity-50 disabled:pointer-events-none rounded-lg transition-all shadow-sm active:scale-[0.98]"
                      >
                        {isApproving ? (
                          <>
                            <svg className="animate-spin h-3.5 w-3.5 text-white" fill="none" viewBox="0 0 24 24">
                              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                            </svg>
                            <span>Executing…</span>
                          </>
                        ) : (
                          <>
                            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                            </svg>
                            <span>Approve Intervention</span>
                          </>
                        )}
                      </button>
                    </>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
