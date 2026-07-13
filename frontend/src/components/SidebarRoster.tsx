import React from 'react';
import type { Staff } from '../types';
import { VenueStats } from './VenueStats';

interface VenueStatsData {
  name: string;
  currentLoad: number;
  totalCapacity: number;
}

interface SidebarRosterProps {
  staff: Staff[];
  venue: VenueStatsData;
}

export function SidebarRoster({ staff, venue }: SidebarRosterProps): React.JSX.Element {
  return (
    <aside className="w-80 h-full bg-slate-900/60 border-r border-slate-800/80 backdrop-blur-md flex flex-col shrink-0 custom-scrollbar overflow-y-auto relative z-10">
      {/* Venue Overview using the new Triple-Nested Radial Gauge */}
      <div className="p-6 border-b border-slate-800/80">
        <VenueStats 
          name={venue.name} 
          currentLoad={venue.currentLoad} 
          totalCapacity={venue.totalCapacity} 
        />
      </div>

      {/* Staff Roster */}
      <div className="p-6 flex-1">
        <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-4 flex items-center justify-between">
          <span>Staff Roster</span>
          <span className="bg-slate-800 text-slate-300 px-2 py-0.5 rounded-full text-[10px] border border-slate-700/50">{staff.length}</span>
        </h2>
        
        <div className="space-y-3">
          {staff.length === 0 ? (
            <div className="text-center p-6 border border-dashed border-slate-700 rounded-xl bg-slate-800/30">
              <p className="text-xs text-slate-500 italic">No staff assigned.</p>
            </div>
          ) : (
            staff.map((member) => (
              <div key={member.id} className="premium-card p-3 flex flex-col gap-2 !shadow-sm !bg-slate-800/50">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs font-bold text-slate-100">{member.id}</span>
                  <span className={`px-2 py-0.5 rounded-full text-[9px] font-bold tracking-wide uppercase ${
                    member.status === 'responding' ? 'bg-red-900/40 text-red-400 border border-red-500/50 animate-pulse' :
                    member.status === 'on_duty' ? 'bg-emerald-900/40 text-emerald-400 border border-emerald-500/50' :
                    member.status === 'break' ? 'bg-amber-900/40 text-amber-400 border border-amber-500/50' :
                    'bg-slate-800/80 text-slate-400 border border-slate-700'
                  }`}>
                    {member.status.replace('_', ' ')}
                  </span>
                </div>
                <div className="flex items-center justify-between text-[11px]">
                  <span className="text-slate-400 capitalize font-medium flex items-center gap-1.5">
                    <svg className="w-3.5 h-3.5 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                    </svg>
                    {member.role}
                  </span>
                  <span className="text-slate-500 bg-slate-900 px-1.5 py-0.5 rounded font-mono border border-slate-700/50">
                    {member.zone_id}
                  </span>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </aside>
  );
}
