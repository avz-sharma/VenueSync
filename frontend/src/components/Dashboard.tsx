import React, { useEffect, useState, useRef } from 'react';
import type { VenueSnapshot, ReasoningCycleOutput } from '../types';
import { ZoneMap } from './ZoneMap';
import { RecommendationQueue } from './RecommendationQueue';

export function Dashboard(): React.JSX.Element {
  // Snapshot states
  const [snapshot, setSnapshot] = useState<VenueSnapshot | null>(null);
  const [loadingSnapshot, setLoadingSnapshot] = useState<boolean>(true);
  const [isFetching, setIsFetching] = useState<boolean>(false);
  const [errorCount, setErrorCount] = useState<number>(0);
  const ERROR_THRESHOLD = 1;
  
  // Reasoning states
  const [reasoning, setReasoning] = useState<ReasoningCycleOutput | null>(null);
  const [loadingReasoning, setLoadingReasoning] = useState<boolean>(false);
  const lastReasonTimeRef = useRef<number>(0);
  
  // Interaction/Mutation states
  const [approvedActionIds, setApprovedActionIds] = useState<Set<string>>(new Set());
  const [dismissedActionIds, setDismissedActionIds] = useState<Set<string>>(new Set());
  const [scenarioLoading, setScenarioLoading] = useState<boolean>(false);
  const [scenarioMessage, setScenarioMessage] = useState<{ text: string; isError: boolean } | null>(null);
  
  // Connection / general error state
  const [connectionError, setConnectionError] = useState<string | null>(null);

  // Ref to track active interval for cleanup
  const pollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // API Call - Fetch snapshot
  const fetchSnapshot = async (isInitial = false): Promise<VenueSnapshot | null> => {
    if (isInitial) setLoadingSnapshot(true);
    setIsFetching(true);
    try {
      const res = await fetch('/api/snapshot');
      if (!res.ok) {
        throw new Error(`Failed to fetch venue snapshot: HTTP status ${res.status}`);
      }
      const data: VenueSnapshot = await res.json();
      setSnapshot(data);
      setConnectionError(null);
      setErrorCount(0);
      return data;
    } catch (err: any) {
      console.error(err);
      setConnectionError(err.message || 'API Server is currently unreachable.');
      setErrorCount((prev) => prev + 1);
      return null;
    } finally {
      setIsFetching(false);
      if (isInitial) setLoadingSnapshot(false);
    }
  };

  // API Call - Trigger Reasoning Engine
  const runReasoning = async (force = false): Promise<void> => {
    // If already loading reasoning, ignore
    if (loadingReasoning) return;

    const currentTime = Date.now();
    const timeSinceLastReasoning = currentTime - lastReasonTimeRef.current;

    // Respect backend's 15s debounce unless forcing (e.g. demo scenario load)
    if (!force && timeSinceLastReasoning < 15000) {
      console.log('Skipping reasoning fetch (client-side debounced)');
      return;
    }

    setLoadingReasoning(true);
    try {
      const res = await fetch('/api/reason', {
        method: 'POST',
      });
      if (!res.ok) {
        throw new Error(`Failed to trigger reasoning: HTTP status ${res.status}`);
      }
      const data: ReasoningCycleOutput = await res.json();
      setReasoning(data);
      lastReasonTimeRef.current = Date.now();
    } catch (err: any) {
      console.error('Reasoning call failed:', err);
      // We don't crash, we just log and show warning if needed
    } finally {
      setLoadingReasoning(false);
    }
  };

  // API Call - Approve Action
  const handleApproveAction = async (actionId: string): Promise<void> => {
    try {
      const res = await fetch(`/api/actions/${actionId}/approve`, {
        method: 'POST',
      });
      if (!res.ok) {
        throw new Error(`Action approval failed: HTTP status ${res.status}`);
      }
      // Add to local approved set
      setApprovedActionIds((prev) => {
        const next = new Set(prev);
        next.add(actionId);
        return next;
      });
    } catch (err: any) {
      console.error(err);
      alert(err.message || 'Could not approve this action.');
    }
  };

  // Local state - Dismiss Action
  const handleDismissAction = (actionId: string) => {
    setDismissedActionIds((prev) => {
      const next = new Set(prev);
      next.add(actionId);
      return next;
    });
  };

  // API Call - Load Demo Scenario
  const handleLoadDemoScenario = async () => {
    setScenarioLoading(true);
    setScenarioMessage(null);
    try {
      const res = await fetch('/api/demo/load-scenario');
      if (!res.ok) {
        throw new Error(`Failed to load demo scenario: HTTP status ${res.status}`);
      }
      
      // Reset approved and dismissed actions when scenario is overridden
      setApprovedActionIds(new Set());
      setDismissedActionIds(new Set());
      
      // Clear client-side reasoning timestamp so it can reason immediately on the new state
      lastReasonTimeRef.current = 0;

      // Update state
      const updatedSnapshot = await fetchSnapshot();
      setScenarioMessage({
        text: "Critical Incident Demo Scenario loaded successfully! 'gate_north' is at 98% with an active medical incident.",
        isError: false,
      });

      // Force reasoning cycle immediately
      if (updatedSnapshot) {
        await runReasoning(true);
      }
    } catch (err: any) {
      console.error(err);
      setScenarioMessage({
        text: err.message || 'Could not load demo scenario.',
        isError: true,
      });
    } finally {
      setScenarioLoading(false);
    }
  };

  // Helper to start the polling interval
  const startPolling = () => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
    }
    pollingIntervalRef.current = setInterval(async () => {
      // Stop execution if error threshold reached
      if (errorCount >= ERROR_THRESHOLD) {
        if (pollingIntervalRef.current) {
          clearInterval(pollingIntervalRef.current);
          pollingIntervalRef.current = null;
        }
        return;
      }
      
      const snap = await fetchSnapshot();
      if (!snap) {
        // Stop execution chain: clear the interval
        if (pollingIntervalRef.current) {
          clearInterval(pollingIntervalRef.current);
          pollingIntervalRef.current = null;
        }
      }
    }, 5000);
  };

  // API Call - Reconnect / Retry Connection
  const handleRetryConnection = async () => {
    setConnectionError(null);
    setErrorCount(0);
    const snap = await fetchSnapshot(true);
    if (snap) {
      // Run reasoning cycle on successful manual reconnect
      await runReasoning(true);
      startPolling();
    }
  };

  // Initial Load and Polling Setup
  useEffect(() => {
    // 1. Initial fetch of snapshot
    const initialLoad = async () => {
      const snap = await fetchSnapshot(true);
      if (snap) {
        // Run initial reasoning cycle on initial load
        await runReasoning(true);
        startPolling();
      }
    };

    void initialLoad();

    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
      }
    };
  }, []);

  // Derived Snapshot Metrics
  const metrics = React.useMemo(() => {
    if (!snapshot) return { totalOccupancy: 0, totalCapacity: 0, pct: 0, activeIncidents: 0, staffResponding: 0 };
    
    let totalCount = 0;
    let totalCapacity = 0;
    snapshot.occupancies.forEach((occ) => {
      totalCount += occ.count;
      totalCapacity += occ.capacity;
    });

    const activeIncidents = snapshot.incidents.length;
    const staffResponding = snapshot.staff.filter((s) => s.status === 'responding').length;
    const pct = totalCapacity > 0 ? (totalCount / totalCapacity) * 100 : 0;

    return {
      totalOccupancy: totalCount,
      totalCapacity,
      pct: Math.round(pct),
      activeIncidents,
      staffResponding,
    };
  }, [snapshot]);

  // Render unreachable backend screen
  if (connectionError && loadingSnapshot) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center p-6 text-slate-100">
        <div className="max-w-md w-full bg-slate-900 border border-red-500/30 rounded-2xl p-8 shadow-2xl text-center space-y-6">
          <div className="h-16 w-16 bg-red-500/10 border border-red-500/20 text-red-500 rounded-full flex items-center justify-center mx-auto animate-pulse">
            <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <div className="space-y-2">
            <h1 className="text-2xl font-bold tracking-tight text-white">API Connection Failed</h1>
            <p className="text-sm text-slate-400">
              VenueSync Command Dashboard could not connect to the backend server (Failed attempts: {errorCount} / Threshold: {ERROR_THRESHOLD}).
            </p>
          </div>
          <div className="text-xs font-mono bg-black/40 text-red-400 p-3 rounded-lg border border-red-950 break-words">
            {connectionError}
          </div>
          <button
            onClick={() => {
              void handleRetryConnection();
            }}
            className="w-full py-2.5 px-4 bg-red-600 hover:bg-red-500 text-white font-bold rounded-xl transition-all shadow-lg shadow-red-600/20"
          >
            Retry Connection
          </button>
        </div>
      </div>
    );
  }

  // Render clean layout even if snapshot is null (failsafe fallback screen)
  const isDataMissing = !snapshot;

  return (
    <div className="min-h-screen bg-slate-950 bg-[radial-gradient(ellipse_80%_80%_at_50%_-20%,rgba(120,119,198,0.15),rgba(255,255,255,0))] text-slate-100 p-6 font-sans">
      <div className="max-w-7xl mx-auto space-y-6">
        
        {/* TOP COMMAND BAR */}
        <header className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-slate-900">
          <div>
            <div className="flex items-center gap-2">
              {isFetching ? (
                <span className="h-2.5 w-2.5 rounded-full bg-cyan-400 animate-pulse" />
              ) : (
                <span className="h-2 w-2 rounded-full bg-emerald-500 animate-ping" />
              )}
              <h1 className="text-3xl font-extrabold bg-gradient-to-r from-emerald-400 via-cyan-400 to-indigo-400 bg-clip-text text-transparent tracking-tight">
                VenueSync
              </h1>
            </div>
            <p className="text-slate-400 text-xs mt-1 tracking-wider uppercase font-semibold">
              Operational Control Command Room
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {/* Manual Refresh Reasoning button */}
            <button
              onClick={() => void runReasoning(true)}
              disabled={loadingReasoning || isDataMissing}
              className="px-4 py-2 text-xs font-semibold bg-slate-900 border border-slate-800 hover:border-slate-700 hover:bg-slate-800 text-slate-300 disabled:opacity-40 disabled:pointer-events-none rounded-xl transition-all flex items-center gap-1.5"
            >
              {loadingReasoning ? (
                <>
                  <svg className="animate-spin h-3.5 w-3.5 text-slate-400" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  <span>Reasoning…</span>
                </>
              ) : (
                <>
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.21 8H18.5" />
                  </svg>
                  <span>Run Reasoning</span>
                </>
              )}
            </button>

            {/* Load Demo Scenario button */}
            <button
              onClick={() => void handleLoadDemoScenario()}
              disabled={scenarioLoading}
              className="relative px-5 py-2 text-xs font-bold text-slate-950 bg-gradient-to-r from-amber-400 to-orange-400 hover:from-amber-300 hover:to-orange-300 rounded-xl transition-all shadow-lg shadow-orange-500/10 flex items-center gap-1.5"
            >
              {scenarioLoading ? (
                <>
                  <svg className="animate-spin h-3.5 w-3.5 text-slate-950" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  <span>Loading Scenario…</span>
                </>
              ) : (
                <>
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                  <span>Load Demo Scenario</span>
                </>
              )}
            </button>
          </div>
        </header>

        {/* ALERTS AND SCENARIO MESSAGES */}
        {scenarioMessage && (
          <div className={`p-4 rounded-xl border flex items-start gap-3 transition-all ${
            scenarioMessage.isError
              ? 'bg-red-500/10 border-red-500/30 text-red-300'
              : 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
          }`}>
            <span className="mt-0.5 shrink-0">
              {scenarioMessage.isError ? (
                <svg className="w-5 h-5 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              ) : (
                <svg className="w-5 h-5 text-emerald-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              )}
            </span>
            <div className="flex-1 text-xs font-medium">
              {scenarioMessage.text}
            </div>
            <button
              onClick={() => setScenarioMessage(null)}
              className="text-slate-400 hover:text-white"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        )}

        {/* CONNECTION ERROR DISPLAY BAR */}
        {connectionError && (
          <div className="bg-red-500/10 border border-red-500/30 p-4 rounded-xl flex items-center justify-between text-xs text-red-300">
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-red-500 animate-ping" />
              <span><strong>Backend Offline:</strong> Polling snapshots failed (Attempt {errorCount}/{ERROR_THRESHOLD}). Polling is suspended.</span>
            </div>
            <button
              onClick={() => void handleRetryConnection()}
              className="underline hover:text-white font-bold"
            >
              Reconnect
            </button>
          </div>
        )}

        {/* STATS RIBBON */}
        <section className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Card 1: Total Occupancy */}
          <div className="rounded-xl border border-slate-900 bg-slate-900/25 p-4 flex items-center justify-between">
            <div>
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Total Occupancy</p>
              <h3 className="text-xl font-bold text-white mt-1">
                {loadingSnapshot ? '…' : `${metrics.totalOccupancy.toLocaleString()} / ${metrics.totalCapacity.toLocaleString()}`}
              </h3>
            </div>
            <div className="text-slate-700">
              <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
              </svg>
            </div>
          </div>

          {/* Card 2: Fill Capacity */}
          <div className="rounded-xl border border-slate-900 bg-slate-900/25 p-4 flex items-center justify-between">
            <div>
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Venue Load</p>
              <h3 className="text-xl font-bold text-white mt-1">
                {loadingSnapshot ? '…' : `${metrics.pct}%`}
              </h3>
            </div>
            <div className="text-slate-700">
              <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
            </div>
          </div>

          {/* Card 3: Active Incidents */}
          <div className={`rounded-xl border p-4 flex items-center justify-between transition-all ${
            metrics.activeIncidents > 0
              ? 'bg-red-950/20 border-red-500/30 text-red-100 shadow-lg shadow-red-950/20'
              : 'bg-slate-900/25 border-slate-900'
          }`}>
            <div>
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Active Incidents</p>
              <h3 className="text-xl font-bold text-white mt-1">
                {loadingSnapshot ? '…' : metrics.activeIncidents}
              </h3>
            </div>
            <div className={metrics.activeIncidents > 0 ? 'text-red-500 animate-pulse' : 'text-slate-700'}>
              <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
          </div>

          {/* Card 4: Staff Responding */}
          <div className="rounded-xl border border-slate-900 bg-slate-900/25 p-4 flex items-center justify-between">
            <div>
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Staff Dispatch</p>
              <h3 className="text-xl font-bold text-white mt-1">
                {loadingSnapshot ? '…' : `${metrics.staffResponding} Responding`}
              </h3>
            </div>
            <div className="text-slate-700">
              <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
          </div>
        </section>

        {/* MAIN DASHBOARD INTERFACE */}
        {isDataMissing && loadingSnapshot ? (
          /* Loading Dashboard state */
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 h-[550px]">
            <div className="lg:col-span-2 border border-slate-900 bg-slate-900/10 rounded-2xl p-6 flex flex-col justify-between animate-pulse">
              <div className="h-6 w-1/4 bg-slate-800 rounded" />
              <div className="h-3/4 w-full bg-slate-900/50 rounded-xl my-4" />
              <div className="h-6 w-1/3 bg-slate-800 rounded" />
            </div>
            <div className="border border-slate-900 bg-slate-900/10 rounded-2xl p-6 animate-pulse">
              <div className="h-6 w-1/3 bg-slate-800 rounded mb-4" />
              <div className="space-y-4">
                <div className="h-28 bg-slate-800/40 rounded-xl" />
                <div className="h-28 bg-slate-800/40 rounded-xl" />
              </div>
            </div>
          </div>
        ) : isDataMissing ? (
          /* Empty / fallback dashboard when no data can be fetched at all */
          <div className="border border-slate-900 bg-slate-900/20 rounded-2xl p-16 text-center space-y-4">
            <h2 className="text-xl font-bold text-white">No Venue Snapshot Data</h2>
            <p className="text-slate-400 max-w-md mx-auto text-sm">
              The dashboard has not received any live event feed telemetry yet. Click the "Load Demo Scenario" button or verify the backend is running synthetic cycles.
            </p>
          </div>
        ) : (
          /* Standard Operational Dashboard */
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
            
            {/* LEFT / CENTER COLUMN: MAP & OVERLAYS */}
            <div className="lg:col-span-2 space-y-6">
              
              {/* Map */}
              <ZoneMap
                zones={snapshot.zones}
                occupancies={snapshot.occupancies}
                incidents={snapshot.incidents}
                staff={snapshot.staff}
              />

              {/* Incidents & Staff Panel */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                
                {/* Incidents Feed */}
                <div className="rounded-2xl border border-slate-800 bg-slate-900/30 backdrop-blur-md p-5 shadow-xl">
                  <h3 className="text-sm font-semibold text-white tracking-wider mb-4 uppercase">
                    Active Incident Feed ({snapshot.incidents.length})
                  </h3>
                  <div className="space-y-3 max-h-[220px] overflow-y-auto pr-1">
                    {snapshot.incidents.length === 0 ? (
                      <p className="text-xs text-slate-500 italic p-4 text-center">
                        No active incidents reported.
                      </p>
                    ) : (
                      snapshot.incidents.map((incident) => {
                        const isCritical = incident.severity === 'critical' || incident.severity === 'high';
                        return (
                          <div
                            key={incident.id}
                            className={`p-3 rounded-lg border text-xs flex justify-between gap-3 ${
                              incident.severity === 'critical'
                                ? 'bg-red-500/10 border-red-500/30 text-red-200'
                                : incident.severity === 'high'
                                ? 'bg-orange-500/10 border-orange-500/30 text-orange-200'
                                : incident.severity === 'medium'
                                ? 'bg-yellow-500/10 border-yellow-500/25 text-yellow-200'
                                : 'bg-slate-900/80 border-slate-800 text-slate-300'
                            }`}
                          >
                            <div className="space-y-1">
                              <div className="flex items-center gap-1.5">
                                <span className={`h-1.5 w-1.5 rounded-full ${isCritical ? 'bg-red-500 animate-ping' : 'bg-current'}`} />
                                <span className="font-semibold capitalize">{incident.type} alert</span>
                              </div>
                              <p className="text-[10px] text-slate-400 font-mono">Zone: {incident.zone_id}</p>
                            </div>
                            <div className="text-right flex flex-col justify-between items-end">
                              <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold uppercase ${
                                incident.severity === 'critical'
                                  ? 'bg-red-500/20 text-red-400'
                                  : incident.severity === 'high'
                                  ? 'bg-orange-500/20 text-orange-400'
                                  : incident.severity === 'medium'
                                  ? 'bg-yellow-500/20 text-yellow-400'
                                  : 'bg-slate-800 text-slate-400'
                              }`}>
                                {incident.severity}
                              </span>
                              <span className="text-[9px] text-slate-500">
                                {new Date(incident.reported_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                              </span>
                            </div>
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>

                {/* Staff Roster Deployment */}
                <div className="rounded-2xl border border-slate-800 bg-slate-900/30 backdrop-blur-md p-5 shadow-xl">
                  <h3 className="text-sm font-semibold text-white tracking-wider mb-4 uppercase">
                    Staff Assignments ({snapshot.staff.length})
                  </h3>
                  <div className="space-y-3 max-h-[220px] overflow-y-auto pr-1">
                    {snapshot.staff.length === 0 ? (
                      <p className="text-xs text-slate-500 italic p-4 text-center">
                        No staff members assigned in system.
                      </p>
                    ) : (
                      snapshot.staff.map((member) => (
                        <div
                          key={member.id}
                          className="p-2.5 rounded-lg border border-slate-800 bg-slate-900/40 text-xs flex items-center justify-between gap-3"
                        >
                          <div>
                            <p className="font-medium text-slate-200 font-mono text-[11px]">{member.id}</p>
                            <div className="flex items-center gap-1.5 mt-0.5">
                              <span className="text-[10px] text-slate-400 capitalize">{member.role}</span>
                              <span className="text-[9px] text-slate-600 font-mono">·</span>
                              <span className="text-[10px] text-slate-500 font-mono">Zone: {member.zone_id}</span>
                            </div>
                          </div>

                          <span className={`px-2 py-0.5 rounded-full text-[9px] font-bold tracking-wide uppercase ${
                            member.status === 'responding'
                              ? 'bg-red-500/25 border border-red-500/30 text-red-300 animate-pulse'
                              : member.status === 'on_duty'
                              ? 'bg-emerald-500/10 border border-emerald-500/20 text-emerald-400'
                              : member.status === 'break'
                              ? 'bg-amber-500/10 border border-amber-500/20 text-amber-400'
                              : 'bg-slate-800 border border-slate-700 text-slate-500'
                          }`}>
                            {member.status.replace('_', ' ')}
                          </span>
                        </div>
                      ))
                    )}
                  </div>
                </div>

              </div>
            </div>

            {/* RIGHT COLUMN: ACTION RECOMMENDATIONS QUEUE */}
            <div className="lg:sticky lg:top-6">
              <RecommendationQueue
                reasoningOutput={reasoning}
                loading={loadingReasoning && !reasoning}
                onApprove={handleApproveAction}
                onDismiss={handleDismissAction}
                approvedIds={approvedActionIds}
                dismissedIds={dismissedActionIds}
              />
            </div>

          </div>
        )}

      </div>
    </div>
  );
}
export default Dashboard;
