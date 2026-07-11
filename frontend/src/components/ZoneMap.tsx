import React from 'react';
import type { Zone, Occupancy, Incident, Staff } from '../types';

interface ZoneMapProps {
  zones: Zone[];
  occupancies: Occupancy[];
  incidents: Incident[];
  staff: Staff[];
  onZoneClick?: (zoneId: string) => void;
}

export function ZoneMap({ zones, occupancies, incidents, staff, onZoneClick }: ZoneMapProps): React.JSX.Element {
  // Map zone data for easy lookup
  const occupancyMap = React.useMemo(() => {
    return new Map(occupancies.map((occ) => [occ.zone_id, occ]));
  }, [occupancies]);

  const incidentMap = React.useMemo(() => {
    const map = new Map<string, Incident[]>();
    incidents.forEach((inc) => {
      const list = map.get(inc.zone_id) || [];
      list.push(inc);
      map.set(inc.zone_id, list);
    });
    return map;
  }, [incidents]);

  const staffMap = React.useMemo(() => {
    const map = new Map<string, Staff[]>();
    staff.forEach((s) => {
      const list = map.get(s.zone_id) || [];
      list.push(s);
      map.set(s.zone_id, list);
    });
    return map;
  }, [staff]);

  // Color selection based on occupancy percentage
  const getCapacityStyles = (pct: number, hasCriticalIncident: boolean) => {
    if (hasCriticalIncident) {
      return {
        card: 'bg-red-950/30 border-red-500/80 hover:border-red-400 text-red-100 shadow-red-950/30 ring-1 ring-red-500/50 animate-pulse-slow',
        badge: 'bg-red-500/20 text-red-300 border-red-500/40',
        progressBar: 'bg-red-500',
        text: 'text-red-400',
      };
    }

    if (pct < 30) {
      return {
        card: 'bg-emerald-950/20 border-emerald-500/30 hover:border-emerald-500/60 text-emerald-100 shadow-emerald-950/20',
        badge: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
        progressBar: 'bg-emerald-500',
        text: 'text-emerald-400',
      };
    }
    if (pct < 60) {
      return {
        card: 'bg-slate-900/40 border-slate-800 hover:border-slate-700 text-slate-100',
        badge: 'bg-green-500/10 text-green-400 border-green-500/20',
        progressBar: 'bg-green-500',
        text: 'text-green-400',
      };
    }
    if (pct < 80) {
      return {
        card: 'bg-yellow-950/10 border-yellow-500/30 hover:border-yellow-500/60 text-yellow-100 shadow-yellow-950/10',
        badge: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
        progressBar: 'bg-yellow-500',
        text: 'text-yellow-400',
      };
    }
    if (pct < 95) {
      return {
        card: 'bg-orange-950/20 border-orange-500/40 hover:border-orange-500/70 text-orange-100 shadow-orange-950/20',
        badge: 'bg-orange-500/10 text-orange-400 border-orange-500/20',
        progressBar: 'bg-orange-500',
        text: 'text-orange-400',
      };
    }
    return {
      card: 'bg-red-950/20 border-red-500/60 hover:border-red-500/80 text-red-100 shadow-red-950/20 animate-pulse',
      badge: 'bg-red-500/20 text-red-400 border-red-500/30',
      progressBar: 'bg-red-500',
      text: 'text-red-400 font-bold',
    };
  };

  // Define layout positions in our custom 4-column, 3-row grid representing the stadium structure
  const gridPositions: Record<string, string> = {
    gate_north: 'col-start-2 col-span-1 row-start-1',
    vip_lounge: 'col-start-3 col-span-1 row-start-1',
    stand_west: 'col-start-1 col-span-1 row-start-2',
    concourse_a: 'col-start-2 col-span-1 row-start-2',
    concourse_b: 'col-start-3 col-span-1 row-start-2',
    stand_east: 'col-start-4 col-span-1 row-start-2',
    food_court: 'col-start-2 col-span-1 row-start-3',
    gate_south: 'col-start-3 col-span-1 row-start-3',
  };

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/30 backdrop-blur-md p-6 shadow-xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold text-white tracking-wide">Live Venue Map</h2>
          <p className="text-xs text-slate-400">Dynamic zone occupancy & incident overlays</p>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-emerald-500" />
            <span className="text-slate-400">&lt;60%</span>
          </span>
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-yellow-500" />
            <span className="text-slate-400">60-80%</span>
          </span>
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-orange-500" />
            <span className="text-slate-400">80-95%</span>
          </span>
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-red-500 animate-pulse" />
            <span className="text-slate-400">&gt;95% / Incident</span>
          </span>
        </div>
      </div>

      {/* Grid container representation of the stadium graph */}
      <div className="grid grid-cols-4 gap-4 min-h-[480px]">
        {zones.map((zone) => {
          const occ = occupancyMap.get(zone.id);
          const zoneIncidents = incidentMap.get(zone.id) || [];
          const zoneStaff = staffMap.get(zone.id) || [];

          // Safe capacity pct calculation (Rule C computes on backend, we provide safety fallbacks)
          const count = occ?.count ?? 0;
          const capacity = occ?.capacity ?? zone.capacity;
          const pct = Math.min(150, capacity > 0 ? (count / capacity) * 100 : 0);
          const trend = occ?.trend ?? 'stable';

          const hasCriticalIncident = zoneIncidents.some((i) => i.severity === 'critical' || i.severity === 'high');
          const styles = getCapacityStyles(pct, hasCriticalIncident);

          const positionClass = gridPositions[zone.id] || 'col-span-1';

          return (
            <div
              key={zone.id}
              onClick={() => onZoneClick?.(zone.id)}
              className={`rounded-xl border backdrop-blur-sm p-4 flex flex-col justify-between transition-all duration-300 cursor-pointer ${positionClass} ${styles.card}`}
            >
              {/* Header */}
              <div className="flex items-start justify-between gap-1 mb-2">
                <div>
                  <h3 className="font-semibold text-sm leading-snug text-white tracking-wide">{zone.name}</h3>
                  <span className="text-[10px] text-slate-500 font-mono tracking-wider uppercase">{zone.id}</span>
                </div>
                
                {/* Trend indicator */}
                <div className="flex items-center gap-1">
                  {trend === 'rising' && (
                    <span className="text-amber-400 font-semibold" title="Occupancy rising">
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
                      </svg>
                    </span>
                  )}
                  {trend === 'falling' && (
                    <span className="text-emerald-400 font-semibold" title="Occupancy falling">
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M13 17h8m0 0v-8m0 8l-8-8-4 4-6-6" />
                      </svg>
                    </span>
                  )}
                  {trend === 'stable' && (
                    <span className="text-slate-500" title="Occupancy stable">
                      <svg className="w-4.5 h-1.5" fill="currentColor" viewBox="0 0 16 4">
                        <rect width="16" height="4" rx="2" />
                      </svg>
                    </span>
                  )}
                </div>
              </div>

              {/* Occupancy metrics */}
              <div className="my-2">
                <div className="flex items-baseline justify-between mb-1">
                  <span className="text-2xl font-bold tracking-tight text-white">
                    {Math.round(pct)}%
                  </span>
                  <span className="text-xs text-slate-400 font-mono">
                    {count.toLocaleString()} / {capacity.toLocaleString()}
                  </span>
                </div>

                {/* Progress bar */}
                <div className="w-full h-1.5 bg-slate-950/60 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${styles.progressBar}`}
                    style={{ width: `${Math.min(100, pct)}%` }}
                  />
                </div>
              </div>

              {/* Status / Incidents / Staff badges */}
              <div className="flex flex-wrap gap-1.5 mt-3 pt-2 border-t border-slate-800/40">
                {zoneIncidents.length > 0 ? (
                  <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium border ${
                    hasCriticalIncident 
                      ? 'bg-red-500/25 border-red-500/50 text-red-200 animate-pulse'
                      : 'bg-amber-500/20 border-amber-500/30 text-amber-300'
                  }`}>
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                    <span>{zoneIncidents.length} Incident{zoneIncidents.length > 1 ? 's' : ''}</span>
                  </span>
                ) : null}

                {zoneStaff.length > 0 ? (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium bg-indigo-500/10 border border-indigo-500/20 text-indigo-300">
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
                    </svg>
                    <span>{zoneStaff.length} Staff</span>
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium bg-slate-800/40 border border-slate-800/60 text-slate-500">
                    No Staff
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
