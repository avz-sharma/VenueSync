import React from 'react';
import type { PreAlertRecommendation } from '../types';

interface PreAlertBadgeProps {
  alert: PreAlertRecommendation;
}

export function PreAlertBadge({ alert }: PreAlertBadgeProps): React.JSX.Element {
  const riskConfig = {
    imminent: {
      bg: 'bg-red-950/50',
      border: 'border-red-500/40',
      text: 'text-red-400',
      dot: 'bg-red-500',
      label: 'IMMINENT',
    },
    high: {
      bg: 'bg-amber-950/50',
      border: 'border-amber-500/40',
      text: 'text-amber-400',
      dot: 'bg-amber-500',
      label: 'HIGH RISK',
    },
    elevated: {
      bg: 'bg-yellow-950/50',
      border: 'border-yellow-500/30',
      text: 'text-yellow-400',
      dot: 'bg-yellow-500',
      label: 'ELEVATED',
    },
  };

  const config = riskConfig[alert.risk_level] || riskConfig.elevated;

  return (
    <div
      className={`rounded-lg ${config.bg} border ${config.border} p-2.5 mt-2 shadow-sm`}
      title={`Pre-Alert: ${alert.preemptive_action}`}
    >
      <div className="flex items-center gap-2 mb-1.5">
        {/* Animated risk dot */}
        <div className="relative">
          <div className={`h-2 w-2 rounded-full ${config.dot} animate-ping absolute inset-0`} />
          <div className={`h-2 w-2 rounded-full ${config.dot} relative`} />
        </div>

        <span className={`text-[9px] font-bold ${config.text} uppercase tracking-widest`}>
          {config.label}
        </span>

        <span className="ml-auto text-[9px] text-slate-500 font-mono">
          ~{alert.estimated_minutes_to_critical}min
        </span>
      </div>

      <p className={`text-[11px] ${config.text} font-medium leading-snug`}>
        {alert.preemptive_action}
      </p>

      <div className="mt-1.5 flex items-center gap-2">
        <span className="text-[9px] text-slate-500">
          {Math.round(alert.confidence * 100)}% confidence
        </span>
      </div>
    </div>
  );
}
