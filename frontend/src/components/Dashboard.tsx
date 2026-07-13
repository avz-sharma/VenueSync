import React, { useEffect, useState, useRef } from 'react';
import type { VenueSnapshot, ReasoningCycleOutput } from '../types';
import { ZoneMap } from './ZoneMap';
import { RecommendationQueue } from './RecommendationQueue';
import { SidebarRoster } from './SidebarRoster';

// Micro-component for Cache Cooldown Progress Circle
function CooldownRing({ lastReasonTime }: { lastReasonTime: number }): React.JSX.Element {
  const circleRef = useRef<SVGCircleElement>(null);
  const textRef = useRef<SVGTextElement>(null);
  const [isSpinning, setIsSpinning] = useState(false);

  useEffect(() => {
    let frame: number;
    const update = () => {
      const now = Date.now();
      const elapsed = now - lastReasonTime;
      const remaining = Math.max(0, 15000 - elapsed);
      const pct = 1 - (remaining / 15000);
      
      if (circleRef.current) {
        const circum = 2 * Math.PI * 14;
        circleRef.current.style.strokeDashoffset = `${circum - pct * circum}`;
      }
      if (textRef.current) {
        textRef.current.textContent = remaining > 0 ? `${Math.ceil(remaining / 1000)}s` : 'RDY';
      }
      
      if (remaining > 0) {
        frame = requestAnimationFrame(update);
      }
    };
    frame = requestAnimationFrame(update);
    return () => cancelAnimationFrame(frame);
  }, [lastReasonTime]);

  const handleClick = () => {
    if (Date.now() - lastReasonTime < 15000) {
      setIsSpinning(true);
      setTimeout(() => setIsSpinning(false), 500);
    }
  };

  return (
    <div className="relative w-8 h-8 cursor-pointer shrink-0" onClick={handleClick} title="AI Reasoning Cooldown Cache">
      <svg className={`w-8 h-8 -rotate-90 ${isSpinning ? 'animate-spin' : ''}`} viewBox="0 0 32 32">
        <circle cx="16" cy="16" r="14" fill="none" className="stroke-slate-800" strokeWidth="3" />
        <circle 
          ref={circleRef}
          cx="16" cy="16" r="14" fill="none" 
          className="stroke-indigo-500 transition-none" 
          strokeWidth="3" 
          strokeDasharray={2 * Math.PI * 14}
          strokeDashoffset={2 * Math.PI * 14}
          strokeLinecap="round"
        />
        <text 
          ref={textRef}
          x="16" y="16" 
          dominantBaseline="middle" 
          textAnchor="middle" 
          className="fill-slate-400 font-mono text-[8px] font-bold"
          transform="rotate(90 16 16)"
        >
          RDY
        </text>
      </svg>
    </div>
  );
}

// React click-outside listener hook (Apple interface pattern)
function useClickOutside(ref: React.RefObject<HTMLElement | null>, handler: () => void) {
  useEffect(() => {
    const listener = (event: MouseEvent) => {
      if (!ref.current || ref.current.contains(event.target as Node)) {
        return;
      }
      handler();
    };
    document.addEventListener('mousedown', listener);
    return () => {
      document.removeEventListener('mousedown', listener);
    };
  }, [ref, handler]);
}

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
  const [lastReasonTime, setLastReasonTime] = useState<number>(0);
  const lastReasonTimeRef = useRef<number>(0);
  
  // Interaction/Mutation states
  const [approvedActionIds, setApprovedActionIds] = useState<Set<string>>(new Set());
  const [dismissedActionIds, setDismissedActionIds] = useState<Set<string>>(new Set());
  const [scenarioLoading, setScenarioLoading] = useState<boolean>(false);
  const [scenarioMessage, setScenarioMessage] = useState<{ text: string; isError: boolean } | null>(null);
  
  const [activeSimulation, setActiveSimulation] = useState<{
    name: string;
    startedAt: number;
    durationMs: number;
    affectedZones: string[];
  } | null>(null);
  
  // Connection / general error state
  const [connectionError, setConnectionError] = useState<string | null>(null);

  // Ref to track active interval for cleanup
  const pollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Dropdown states for scenario simulation
  const [isDropdownOpen, setIsDropdownOpen] = useState<boolean>(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close menu when clicking outside
  useClickOutside(dropdownRef, () => setIsDropdownOpen(false));

  // Reconnection hook (clean component lifecycle)
  const [reconnectSeconds, setReconnectSeconds] = useState(0);
  useEffect(() => {
    let interval: ReturnType<typeof setInterval>;
    if (connectionError) {
      setReconnectSeconds(4);
      interval = setInterval(() => {
        setReconnectSeconds(prev => {
          if (prev <= 1) {
            void handleRetryConnection();
            return 4; 
          }
          return prev - 1;
        });
      }, 1000);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [connectionError]);

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
    // If already loading reasoning, ignore unless forced
    if (loadingReasoning && !force) return;

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
      const now = Date.now();
      lastReasonTimeRef.current = now;
      setLastReasonTime(now);
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

  // API Call - Trigger Simulation Scenario
  const handleTriggerScenario = async (
    endpoint: string,
    method: 'GET' | 'POST',
    body?: { gate_id: string },
    successMessage?: string,
    simulationName?: string,
    affectedZones?: string[]
  ) => {
    setScenarioLoading(true);
    setScenarioMessage(null);
    setIsDropdownOpen(false);
    try {
      const config: RequestInit = { method };
      if (body) {
        config.headers = { 'Content-Type': 'application/json' };
        config.body = JSON.stringify(body);
      }
      
      const res = await fetch(endpoint, config);
      if (!res.ok) {
        throw new Error(`Failed to trigger scenario: HTTP status ${res.status}`);
      }
      
      // Reset approved and dismissed actions when scenario is overridden
      setApprovedActionIds(new Set());
      setDismissedActionIds(new Set());
      
      // Clear client-side reasoning timestamp so it can reason immediately on the new state
      lastReasonTimeRef.current = 0;
      setLastReasonTime(0);

      // Update state
      const updatedSnapshot = await fetchSnapshot();

      // Check if response contains a custom message
      let displayMsg = successMessage;
      try {
        const data = await res.json();
        if (data && data.message) {
          displayMsg = data.message;
        }
      } catch (e) {
        // Fallback to custom successMessage if parsing fails
      }

      setScenarioMessage({
        text: displayMsg || 'Simulation scenario triggered successfully.',
        isError: false,
      });

      if (simulationName && affectedZones) {
        const sim = {
          name: simulationName,
          startedAt: Date.now(),
          durationMs: 12000,
          affectedZones,
        };
        setActiveSimulation(sim);
        setTimeout(() => {
          setActiveSimulation((prev) => (prev?.startedAt === sim.startedAt ? null : prev));
        }, 12500);
      } else {
        setActiveSimulation(null);
      }

      // Force reasoning cycle immediately
      if (updatedSnapshot) {
        await runReasoning(true);
      }
    } catch (err: any) {
      console.error(err);
      setScenarioMessage({
        text: err.message || 'Could not trigger simulation scenario.',
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
      <div className="min-h-screen flex items-center justify-center p-6 bg-[#080c14]">
        <div className="max-w-md w-full bg-slate-900/60 border border-red-500/50 backdrop-blur-md rounded-2xl p-8 shadow-2xl text-center space-y-6">
          <div className="h-16 w-16 bg-red-50 border border-red-100 text-red-500 rounded-full flex items-center justify-center mx-auto animate-pulse">
            <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <div className="space-y-2">
            <h1 className="text-2xl font-bold tracking-tight text-slate-100">API Connection Failed</h1>
            <p className="text-sm text-slate-400">
              VenueSync Command Dashboard could not connect to the backend server (Failed attempts: {errorCount} / Threshold: {ERROR_THRESHOLD}).
            </p>
          </div>
          <div className="text-xs font-mono bg-slate-50 text-red-600 p-3 rounded-lg border border-red-100 break-words">
            {connectionError}
          </div>
          <button
            onClick={() => {
              void handleRetryConnection();
            }}
            className="w-full py-2.5 px-4 bg-red-600 hover:bg-red-700 text-white font-bold rounded-xl transition-all shadow-sm"
          >
            Retry Connection
          </button>
        </div>
      </div>
    );
  }

  const isDataMissing = !snapshot;

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#080c14] text-slate-100 font-sans">
      
      {/* COLUMN 1: Left-Hand Side Roster & Capacities */}
      <SidebarRoster 
        staff={snapshot?.staff || []} 
        venue={{
          name: "Metropolitan Arena",
          currentLoad: metrics.totalOccupancy,
          totalCapacity: metrics.totalCapacity > 0 ? metrics.totalCapacity : 22000
        }} 
      />

      {/* CORE WORKSPACE ANCHOR */}
      <div className="flex-1 flex flex-col min-w-0 h-full relative">
        
        {/* Apple-Style Global Control Strip */}
        <header className="h-16 border-b border-slate-800/80 bg-slate-900/60 backdrop-blur-md px-8 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3 w-1/3">
            {isFetching ? (
              <span className="h-2 w-2 rounded-full bg-indigo-500 animate-pulse" />
            ) : (
              <span className="h-2 w-2 rounded-full bg-emerald-500 animate-ping" />
            )}
            <div>
              <h1 className="text-sm font-bold text-slate-100 tracking-tight">VenueSync Core</h1>
              <p className="text-[10px] text-slate-400 font-medium uppercase tracking-wider">Operational Command</p>
            </div>
          </div>
          
          {/* Real-Time Telemetry Status Bar */}
          <div className="flex-1 flex justify-center w-1/3">
            {connectionError ? (
              <div className="flex items-center gap-2 px-4 py-1.5 bg-red-950/40 border border-red-500/50 rounded-full shadow-[0_0_15px_rgba(239,68,68,0.2)]">
                <span className="h-2 w-2 rounded-full bg-red-500 animate-pulse" />
                <span className="text-[10px] font-bold text-red-400 tracking-widest uppercase">
                  [ TELEMETRY INTERRUPTED - Reconnecting in {reconnectSeconds}s ]
                </span>
              </div>
            ) : (
              <div className="flex items-center gap-2 px-4 py-1.5 bg-emerald-950/30 border border-emerald-500/30 rounded-full shadow-[0_0_15px_rgba(16,185,129,0.1)]">
                <span className="h-2 w-2 rounded-full bg-emerald-500" />
                <span className="text-[10px] font-bold text-emerald-400 tracking-widest uppercase">
                  [ CONNECTED - Live Telemetry ]
                </span>
              </div>
            )}
          </div>

          {/* Action Optimization Toggles */}
          <div className="relative inline-flex items-center justify-end w-1/3" ref={dropdownRef}>
            {/* Main Split Action Button */}
            <button
              onClick={() =>
                void handleTriggerScenario(
                  '/api/demo/load-scenario',
                  'GET',
                  undefined,
                  "Critical Incident Demo Scenario loaded successfully! 'gate_north' is at 98% with an active medical incident."
                )
              }
              disabled={scenarioLoading}
              className="bg-slate-900 hover:bg-slate-800 text-white font-medium text-sm px-4 h-10 rounded-l-xl transition-all duration-200 active:scale-[0.98] shadow-sm flex items-center gap-2 border-r border-slate-800 disabled:opacity-50"
            >
              {scenarioLoading ? (
                <>
                  <svg className="animate-spin h-3.5 w-3.5 text-white" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  <span>Loading…</span>
                </>
              ) : (
                <>
                  <svg className="w-3.5 h-3.5 text-slate-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                  <span>Load Demo Scenario</span>
                </>
              )}
            </button>

            {/* Dropdown Chevron Toggle */}
            <button
              onClick={() => setIsDropdownOpen(!isDropdownOpen)}
              className="group bg-slate-900 hover:bg-slate-800 text-white h-10 px-2.5 rounded-r-xl transition-all duration-200 active:scale-[0.98] shadow-sm flex items-center justify-center border-l border-slate-800"
              aria-label="Select Scenario"
            >
              <svg
                className={`w-4 h-4 text-slate-300 transition-transform duration-200 ${
                  isDropdownOpen ? 'rotate-180' : 'group-hover:rotate-180'
                }`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2.5}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            {/* Dropdown Menu */}
            {isDropdownOpen && (
              <div className="absolute right-0 top-full mt-2 w-72 bg-slate-900/95 backdrop-blur-md border border-slate-800 rounded-xl shadow-2xl z-50 p-1.5 animate-in fade-in slide-in-from-top-1 duration-150">
                <div className="px-3 py-2 text-[11px] font-bold text-slate-400 uppercase tracking-wider">
                  Select Venue Stress Scenario
                </div>

                <button
                  onClick={() =>
                    void handleTriggerScenario(
                      '/api/demo/load-scenario',
                      'GET',
                      undefined,
                      "Critical Incident Demo Scenario loaded successfully! 'gate_north' is at 98% with an active medical incident."
                    )
                  }
                  className="w-full text-left px-3 py-2.5 rounded-lg text-sm font-medium text-slate-850 hover:bg-slate-50 transition-colors flex flex-col gap-0.5"
                >
                  <span className="text-slate-900 font-semibold">1. Critical Incident (Tense)</span>
                  <span className="text-xs text-slate-400">98% Gate North flood + Active medical emergency.</span>
                </button>

                <button
                  onClick={() =>
                    void handleTriggerScenario(
                      '/api/demo/gate-closure',
                      'POST',
                      { gate_id: 'gate_north' },
                      "Gate Closure Simulation triggered successfully! North gate closed. Rerouting in progress.",
                      "Gate Closure",
                      ['gate_north', 'gate_south', 'concourse_a', 'concourse_b']
                    )
                  }
                  className="w-full text-left px-3 py-2.5 rounded-lg text-sm font-medium text-slate-850 hover:bg-slate-50 transition-colors flex flex-col gap-0.5"
                >
                  <span className="text-slate-900 font-semibold">2. Gate Closure Simulation</span>
                  <span className="text-xs text-slate-400">Close Gate North. 12s progressive rerouting to South.</span>
                </button>

                <button
                  onClick={() =>
                    void handleTriggerScenario(
                      '/api/demo/rain-simulation',
                      'POST',
                      undefined,
                      "Rain Simulation triggered successfully! Crowd shifting to covered zones.",
                      "Rain simulation",
                      ['stand_west', 'stand_east', 'concourse_a', 'concourse_b', 'vip_lounge']
                    )
                  }
                  className="w-full text-left px-3 py-2.5 rounded-lg text-sm font-medium text-slate-850 hover:bg-slate-50 transition-colors flex flex-col gap-0.5"
                >
                  <span className="text-slate-900 font-semibold">3. Rain Simulation Event</span>
                  <span className="text-xs text-slate-400">50% exposed crowd shifts to covered shelters over 12s.</span>
                </button>
              </div>
            )}
          </div>
        </header>

        {/* ALERTS AND SCENARIO MESSAGES (Positioned absolutely over main content or fixed at top) */}
        <div className="absolute top-16 left-0 right-0 z-50 flex flex-col items-center gap-2 pt-4 pointer-events-none">
          {scenarioMessage && (
            <div className={`p-3 rounded-xl border flex items-start gap-3 shadow-md bg-white pointer-events-auto max-w-2xl mx-auto w-full transition-all ${
              scenarioMessage.isError
                ? 'border-red-200 text-red-700 bg-red-50'
                : 'border-emerald-200 text-emerald-700 bg-emerald-50'
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
              <div className="flex-1 text-sm font-medium">
                {scenarioMessage.text}
              </div>
              <button
                onClick={() => setScenarioMessage(null)}
                className="text-slate-400 hover:text-slate-600"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          )}

          {connectionError && (
            <div className="bg-red-50 border border-red-200 p-3 rounded-xl flex items-center justify-between text-sm text-red-700 shadow-md pointer-events-auto max-w-2xl mx-auto w-full">
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-red-500 animate-ping" />
                <span><strong>Backend Offline:</strong> Polling snapshots failed. Polling suspended.</span>
              </div>
              <button
                onClick={() => void handleRetryConnection()}
                className="underline hover:text-red-900 font-bold"
              >
                Reconnect
              </button>
            </div>
          )}
        </div>

        {/* WORKSPACE SUB-GRID */}
        <main className="flex-1 flex overflow-hidden p-6 gap-6 pt-8">
          
          {isDataMissing && loadingSnapshot ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="animate-pulse flex items-center gap-3 text-slate-500 font-medium text-sm">
                <div className="h-2 w-2 rounded-full bg-slate-400 animate-ping" />
                Initializing VenueSync Workspace...
              </div>
            </div>
          ) : isDataMissing ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="premium-card text-center space-y-4 max-w-md w-full">
                <h2 className="text-xl font-bold text-slate-100">No Venue Data</h2>
                <p className="text-slate-400 text-sm">
                  The dashboard has not received any live event feed telemetry yet.
                </p>
              </div>
            </div>
          ) : (
            <>
              {/* COLUMN 2: High-Performance Canvas Map Space */}
              <div className="flex-1 flex flex-col h-full min-w-0">
                <div className="mb-3 px-1">
                  <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400">Live Venue Map</h2>
                  <p className="text-xs text-slate-500">Dynamic zone density & spatial tracking overlay</p>
                </div>
                
                {/* The canvas wrapper using flex relative size instead of forced aspect-video */}
                <div className="flex-1 flex flex-col min-h-0 bg-slate-900/40 border border-slate-800/80 backdrop-blur-md rounded-2xl p-4 shadow-sm">
                   <div className="flex-1 relative overflow-hidden">
                      <ZoneMap
                        zones={snapshot?.zones || []}
                        occupancies={snapshot?.occupancies || []}
                        incidents={snapshot?.incidents || []}
                        staff={snapshot?.staff || []}
                        activeSimulation={activeSimulation}
                      />
                   </div>
                </div>
              </div>

              {/* COLUMN 3: Right-Hand Side Contextual Action Queue */}
              <div className="w-[384px] flex flex-col h-full shrink-0">
                <div className="mb-3 px-1 flex items-center justify-between">
                  <div>
                    <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400">AI Logic Queue</h2>
                    <p className="text-xs text-slate-500">PHS prioritized resource routing interventions</p>
                  </div>
                  <CooldownRing lastReasonTime={lastReasonTime} />
                </div>
                
                <div className="flex-1 bg-slate-900/40 border border-slate-800/80 backdrop-blur-md rounded-2xl p-4 shadow-sm overflow-hidden flex flex-col">
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
            </>
          )}

        </main>
      </div>
    </div>
  );
}
export default Dashboard;
