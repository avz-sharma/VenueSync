import { useState, useEffect, useRef, useCallback } from 'react';
import type { VenueSnapshot, ReasoningCycleOutput, PreAlertOutput } from '../types';

export function useDashboard() {
  const [snapshot, setSnapshot] = useState<VenueSnapshot | null>(null);
  const [loadingSnapshot, setLoadingSnapshot] = useState<boolean>(true);
  const [isFetching, setIsFetching] = useState<boolean>(false);
  const [errorCount, setErrorCount] = useState<number>(0);
  const ERROR_THRESHOLD = 1;
  
  const [reasoning, setReasoning] = useState<ReasoningCycleOutput | null>(null);
  const [loadingReasoning, setLoadingReasoning] = useState<boolean>(false);
  const [lastReasonTime, setLastReasonTime] = useState<number>(0);
  const lastReasonTimeRef = useRef<number>(0);
  
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
  
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [preAlerts, setPreAlerts] = useState<PreAlertOutput | null>(null);
  
  const pollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  
  const [isDropdownOpen, setIsDropdownOpen] = useState<boolean>(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const [reconnectSeconds, setReconnectSeconds] = useState(0);

  const fetchSnapshot = useCallback(async (isInitial = false): Promise<VenueSnapshot | null> => {
    if (isInitial) setLoadingSnapshot(true);
    setIsFetching(true);
    try {
      const res = await fetch('/api/snapshot');
      if (!res.ok) throw new Error(`HTTP status ${res.status}`);
      const data: VenueSnapshot = await res.json();
      setSnapshot(data);
      setConnectionError(null);
      setErrorCount(0);
      return data;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'API Server unreachable';
      setConnectionError(msg);
      setErrorCount((prev) => prev + 1);
      return null;
    } finally {
      setIsFetching(false);
      if (isInitial) setLoadingSnapshot(false);
    }
  }, []);

  const runReasoning = useCallback(async (force = false): Promise<void> => {
    if (loadingReasoning && !force) return;
    setLoadingReasoning(true);
    try {
      const res = await fetch('/api/reason', { method: 'POST' });
      if (!res.ok) {
        throw new Error(`Failed to trigger reasoning: HTTP status ${res.status}`);
      }
      const data: ReasoningCycleOutput = await res.json();
      setReasoning(data);
      const now = Date.now();
      lastReasonTimeRef.current = now;
      setLastReasonTime(now);
    } catch (err) {
      // Error handled by state hooks or toast where necessary
    } finally {
      setLoadingReasoning(false);
    }
  }, [loadingReasoning]);

  const fetchPreAlerts = async (): Promise<void> => {
    try {
      const res = await fetch('/api/pre-alert');
      if (!res.ok) return;
      const data: PreAlertOutput = await res.json();
      setPreAlerts(data);
    } catch (err: unknown) {
      // Pre-alert fetch handled
    }
  };

  const handleApproveAction = async (actionId: string): Promise<void> => {
    try {
      const res = await fetch(`/api/actions/${actionId}/approve`, {
        method: 'POST',
      });
      if (!res.ok) {
        throw new Error(`Action approval failed: HTTP status ${res.status}`);
      }
      setApprovedActionIds((prev) => {
        const next = new Set(prev);
        next.add(actionId);
        return next;
      });
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : 'Could not approve this action.';
      alert(errorMsg);
    }
  };

  const handleDismissAction = (actionId: string) => {
    setDismissedActionIds((prev) => {
      const next = new Set(prev);
      next.add(actionId);
      return next;
    });
  };

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
      
      setApprovedActionIds(new Set());
      setDismissedActionIds(new Set());
      
      lastReasonTimeRef.current = 0;
      setLastReasonTime(0);

      const updatedSnapshot = await fetchSnapshot();

      let displayMsg = successMessage;
      try {
        const data = await res.json();
        if (data && data.message) {
          displayMsg = data.message;
        }
      } catch {
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

      if (updatedSnapshot) {
        await runReasoning(true);
      }
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : 'Could not trigger simulation scenario.';
      setScenarioMessage({
        text: errorMsg,
        isError: true,
      });
    } finally {
      setScenarioLoading(false);
    }
  };

  const startPolling = () => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
    }
    pollingIntervalRef.current = setInterval(async () => {
      if (errorCount >= ERROR_THRESHOLD) {
        if (pollingIntervalRef.current) {
          clearInterval(pollingIntervalRef.current);
          pollingIntervalRef.current = null;
        }
        return;
      }
      
      const snap = await fetchSnapshot();
      if (!snap) {
        if (pollingIntervalRef.current) {
          clearInterval(pollingIntervalRef.current);
          pollingIntervalRef.current = null;
        }
      }
    }, 5000);
  };

  const handleRetryConnection = async () => {
    setConnectionError(null);
    setErrorCount(0);
    const snap = await fetchSnapshot(true);
    if (snap) {
      await runReasoning(true);
      startPolling();
    }
  };

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

  useEffect(() => {
    const initialLoad = async () => {
      const snap = await fetchSnapshot(true);
      if (snap) {
        await runReasoning(true);
        await fetchPreAlerts();
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

  return {
    snapshot,
    loadingSnapshot,
    isFetching,
    errorCount,
    ERROR_THRESHOLD,
    reasoning,
    loadingReasoning,
    lastReasonTime,
    approvedActionIds,
    dismissedActionIds,
    scenarioLoading,
    scenarioMessage,
    setScenarioMessage,
    activeSimulation,
    connectionError,
    preAlerts,
    isDropdownOpen,
    setIsDropdownOpen,
    dropdownRef,
    reconnectSeconds,
    handleApproveAction,
    handleDismissAction,
    handleTriggerScenario,
    handleRetryConnection,
  };
}
