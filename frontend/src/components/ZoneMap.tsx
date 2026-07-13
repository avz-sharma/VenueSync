import React from 'react';
import type { Zone, Occupancy, Incident, Staff } from '../types';

type MapMode = 'density' | 'flow' | 'logistics';

interface HeatmapParticle {
  zoneId: string;
  x: number; // normalized 0..1
  y: number; // normalized 0..1
  intensity: number;
  targetIntensity: number;
  angle: number;
  speed: number;
  vx: number;
  vy: number;
}

const PHYSICS_CONFIG = {
  MAX_PARTICLES_PER_ZONE: 25,
  DRIFT_MULTIPLIER: 0.05,
  NOISE_MULTIPLIER: 0.15,
  SMOOTHING_FACTOR: 0.05,
  BLUR_RADIUS: 25,
  INTENSITY_SCALE: 4.0, // Scale normalized 0..1 to PHS 0..4 range
} as const;

const zoneGridCoords: Record<string, { col: number; row: number; colSpan: number; rowSpan: number }> = {
  gate_north: { col: 1, row: 0, colSpan: 1, rowSpan: 1 },
  vip_lounge: { col: 2, row: 0, colSpan: 1, rowSpan: 1 },
  stand_west: { col: 0, row: 1, colSpan: 1, rowSpan: 1 },
  concourse_a: { col: 1, row: 1, colSpan: 1, rowSpan: 1 },
  concourse_b: { col: 2, row: 1, colSpan: 1, rowSpan: 1 },
  stand_east: { col: 3, row: 1, colSpan: 1, rowSpan: 1 },
  food_court: { col: 1, row: 2, colSpan: 1, rowSpan: 1 },
  gate_south: { col: 2, row: 2, colSpan: 1, rowSpan: 1 },
};

interface ZoneMapProps {
  zones: Zone[];
  occupancies: Occupancy[];
  incidents: Incident[];
  staff: Staff[];
  activeSimulation?: {
    name: string;
    startedAt: number;
    durationMs: number;
    affectedZones: string[];
  } | null;
  onZoneClick?: (zoneId: string) => void;
}

export function ZoneMap({ zones, occupancies, incidents, staff, activeSimulation, onZoneClick }: ZoneMapProps): React.JSX.Element {
  const canvasRef = React.useRef<HTMLCanvasElement | null>(null);
  const particlesRef = React.useRef<HeatmapParticle[]>([]);
  const [mode, setMode] = React.useState<MapMode>('density');
  const modeRef = React.useRef<MapMode>(mode);
  const staffRef = React.useRef<Staff[]>(staff);

  const timelineFillRef = React.useRef<HTMLDivElement | null>(null);
  const timelineTextRef = React.useRef<HTMLSpanElement | null>(null);

  React.useEffect(() => {
    if (!activeSimulation) return;
    let animationFrameId: number;
    const { startedAt, durationMs, name } = activeSimulation;

    const renderProgress = () => {
      const now = Date.now();
      const elapsed = now - startedAt;
      const alpha = Math.min(1.0, Math.max(0.0, elapsed / durationMs));
      
      if (timelineFillRef.current) {
        timelineFillRef.current.style.width = `${alpha * 100}%`;
      }
      if (timelineTextRef.current) {
        const remainingSeconds = Math.max(0, Math.ceil((durationMs - elapsed) / 1000));
        timelineTextRef.current.innerText = `${name} - View progressive impact: ${remainingSeconds}s`;
      }

      if (alpha < 1.0) {
        animationFrameId = requestAnimationFrame(renderProgress);
      }
    };
    animationFrameId = requestAnimationFrame(renderProgress);

    return () => cancelAnimationFrame(animationFrameId);
  }, [activeSimulation]);

  React.useEffect(() => {
    staffRef.current = staff;
  }, [staff]);

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

  // Particle synchronizer mapping real-time data or fallback states without re-rendering the DOM
  React.useEffect(() => {
    const nextParticles: HeatmapParticle[] = [];

    zones.forEach((zone) => {
      const occ = occupancyMap.get(zone.id);
      const zoneIncidents = incidentMap.get(zone.id) || [];
      const hasCriticalIncident = zoneIncidents.some((i) => i.severity === 'critical' || i.severity === 'high');

      // 1. Check if zone has custom heatmap points from the backend
      if (zone.heatmap_points && zone.heatmap_points.length > 0) {
        zone.heatmap_points.forEach((pt) => {
          // Find existing particle close to it, or create a new one
          const existing = particlesRef.current.find(
            (p) => p.zoneId === zone.id && Math.abs(p.x - pt.x) < 0.1 && Math.abs(p.y - pt.y) < 0.1
          );

          nextParticles.push({
            zoneId: zone.id,
            x: pt.x,
            y: pt.y,
            intensity: existing ? existing.intensity : pt.intensity,
            targetIntensity: pt.intensity,
            angle: existing ? existing.angle : (pt.vx !== undefined && pt.vy !== undefined ? Math.atan2(pt.vy, pt.vx) : Math.random() * Math.PI * 2),
            speed: existing ? existing.speed : (pt.vx !== undefined && pt.vy !== undefined ? Math.sqrt(pt.vx * pt.vx + pt.vy * pt.vy) : (0.2 + Math.random() * 0.8) * 0.01),
            vx: pt.vx !== undefined ? pt.vx : (existing ? existing.vx : (Math.random() - 0.5) * 0.005),
            vy: pt.vy !== undefined ? pt.vy : (existing ? existing.vy : (Math.random() - 0.5) * 0.005),
          });
        });
      } else {
        // 2. Synthetic fallback: Determine particle count based on occupancy and incidents
        const count = occ?.count ?? 0;
        const capacity = occ?.capacity ?? zone.capacity;
        const pct = Math.min(150, capacity > 0 ? (count / capacity) * 100 : 0);

        // More density -> more particles
        let targetCount = Math.min(
          PHYSICS_CONFIG.MAX_PARTICLES_PER_ZONE,
          Math.max(2, Math.floor(pct / 5))
        );

        // Boost targetCount if there's an active incident
        if (zoneIncidents.length > 0) {
          targetCount += zoneIncidents.length * 5;
        }

        // Get existing particles for this zone
        const existingParticles = particlesRef.current.filter((p) => p.zoneId === zone.id);

        for (let i = 0; i < targetCount; i++) {
          const existing = existingParticles[i];
          if (existing) {
            // Keep existing particle but update its targetIntensity
            const targetIntensity = hasCriticalIncident ? 0.9 : Math.min(1.0, pct / 100);
            nextParticles.push({
              ...existing,
              targetIntensity,
            });
          } else {
            // Create a new particle
            const targetIntensity = hasCriticalIncident ? 0.9 : Math.min(1.0, pct / 100);
            nextParticles.push({
              zoneId: zone.id,
              x: 0.1 + Math.random() * 0.8,
              y: 0.1 + Math.random() * 0.8,
              intensity: 0,
              targetIntensity,
              angle: Math.random() * Math.PI * 2,
              speed: (0.2 + Math.random() * 0.8) * 0.01,
              vx: (Math.random() - 0.5) * 0.005,
              vy: (Math.random() - 0.5) * 0.005,
            });
          }
        }
      }
    });

    particlesRef.current = nextParticles;
  }, [zones, occupancyMap, incidentMap]);

  // RequestAnimationFrame high-performance rendering loop
  React.useEffect(() => {
    let animationFrameId: number;

    const renderLoop = () => {
      const canvas = canvasRef.current;
      if (!canvas) {
        animationFrameId = requestAnimationFrame(renderLoop);
        return;
      }

      const ctx = canvas.getContext('2d');
      if (!ctx) {
        animationFrameId = requestAnimationFrame(renderLoop);
        return;
      }

      // 1. Sync canvas buffer size with client size (window resize handling)
      if (canvas.width !== canvas.clientWidth || canvas.height !== canvas.clientHeight) {
        canvas.width = canvas.clientWidth;
        canvas.height = canvas.clientHeight;
      }

      // 2. Clear canvas
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // Grid dimensions matching CSS grid: 4 columns, 3 rows, gap-4 (16px)
      const cols = 4;
      const rows = 3;
      const gap = 16;
      const cellWidth = (canvas.width - gap * (cols - 1)) / cols;
      const cellHeight = (canvas.height - gap * (rows - 1)) / rows;

      // 3. Update physics
      particlesRef.current.forEach((particle) => {
        // Smoothly interpolate intensity
        particle.intensity += (particle.targetIntensity - particle.intensity) * PHYSICS_CONFIG.SMOOTHING_FACTOR;

        // Apply drift and Brownian noise
        particle.angle += (Math.random() - 0.5) * PHYSICS_CONFIG.NOISE_MULTIPLIER;
        particle.x += Math.cos(particle.angle) * particle.speed * PHYSICS_CONFIG.DRIFT_MULTIPLIER;
        particle.y += Math.sin(particle.angle) * particle.speed * PHYSICS_CONFIG.DRIFT_MULTIPLIER;

        // Keep particles within zone bounds [0.05, 0.95]
        if (particle.x < 0.05 || particle.x > 0.95) {
          particle.x = Math.max(0.05, Math.min(0.95, particle.x));
          particle.angle = Math.PI - particle.angle;
        }
        if (particle.y < 0.05 || particle.y > 0.95) {
          particle.y = Math.max(0.05, Math.min(0.95, particle.y));
          particle.angle = -particle.angle;
        }
      });

      // 4. Render based on current mode
      const currentMode = modeRef.current;

      if (currentMode === 'density') {
        particlesRef.current.forEach((particle) => {
          const coords = zoneGridCoords[particle.zoneId];
          if (!coords) return;
          const zoneLeft = coords.col * (cellWidth + gap);
          const zoneTop = coords.row * (cellHeight + gap);
          const zoneWidth = coords.colSpan * cellWidth + (coords.colSpan - 1) * gap;
          const zoneHeight = coords.rowSpan * cellHeight + (coords.rowSpan - 1) * gap;
          const pixelX = zoneLeft + particle.x * zoneWidth;
          const pixelY = zoneTop + particle.y * zoneHeight;

          const radius = PHYSICS_CONFIG.BLUR_RADIUS;
          const gradient = ctx.createRadialGradient(pixelX, pixelY, 0, pixelX, pixelY, radius);

          const scaledIntensity = particle.intensity * PHYSICS_CONFIG.INTENSITY_SCALE;
          const alpha = Math.min(scaledIntensity / 4.0, 1.0);

          gradient.addColorStop(0, `rgba(239, 68, 68, ${alpha})`); // Red for critical (>4.0 PPL/m²)
          gradient.addColorStop(0.5, `rgba(245, 158, 11, ${alpha * 0.5})`); // Amber for restricted
          gradient.addColorStop(1, 'rgba(16, 185, 129, 0)'); // Fades to Green/Transparent

          ctx.fillStyle = gradient;
          ctx.beginPath();
          ctx.arc(pixelX, pixelY, radius, 0, 2 * Math.PI);
          ctx.fill();
        });
      } else if (currentMode === 'flow') {
        particlesRef.current.forEach((particle) => {
          const coords = zoneGridCoords[particle.zoneId];
          if (!coords) return;
          const zoneLeft = coords.col * (cellWidth + gap);
          const zoneTop = coords.row * (cellHeight + gap);
          const zoneWidth = coords.colSpan * cellWidth + (coords.colSpan - 1) * gap;
          const zoneHeight = coords.rowSpan * cellHeight + (coords.rowSpan - 1) * gap;
          const pixelX = zoneLeft + particle.x * zoneWidth;
          const pixelY = zoneTop + particle.y * zoneHeight;

          const arrowLength = 12;
          const endX = pixelX + Math.cos(particle.angle) * arrowLength;
          const endY = pixelY + Math.sin(particle.angle) * arrowLength;

          ctx.strokeStyle = 'rgba(148, 163, 184, 0.8)'; // slate-400
          ctx.lineWidth = 1.5;
          ctx.beginPath();
          ctx.moveTo(pixelX, pixelY);
          ctx.lineTo(endX, endY);
          ctx.stroke();

          const headLength = 4;
          const headAngle = Math.PI / 6;
          ctx.beginPath();
          ctx.moveTo(endX, endY);
          ctx.lineTo(
            endX - headLength * Math.cos(particle.angle - headAngle),
            endY - headLength * Math.sin(particle.angle - headAngle)
          );
          ctx.lineTo(
            endX - headLength * Math.cos(particle.angle + headAngle),
            endY - headLength * Math.sin(particle.angle + headAngle)
          );
          ctx.closePath();
          ctx.fillStyle = 'rgba(148, 163, 184, 0.8)';
          ctx.fill();
        });
      } else if (currentMode === 'logistics') {
        const staffList = staffRef.current;
        const now = Date.now();
        const pulseScale = 1 + Math.sin(now / 150) * 0.4; // 1.0 to 1.4

        staffList.forEach((s) => {
          const coords = zoneGridCoords[s.zone_id];
          if (!coords) return;
          
          const idNum = s.id.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
          const px = 0.1 + ((idNum * 13) % 80) / 100;
          const py = 0.1 + ((idNum * 17) % 80) / 100;
          
          const zoneLeft = coords.col * (cellWidth + gap);
          const zoneTop = coords.row * (cellHeight + gap);
          const zoneWidth = coords.colSpan * cellWidth + (coords.colSpan - 1) * gap;
          const zoneHeight = coords.rowSpan * cellHeight + (coords.rowSpan - 1) * gap;
          
          const pixelX = zoneLeft + px * zoneWidth;
          const pixelY = zoneTop + py * zoneHeight;

          const isEmergency = (s.role === 'medical' || s.role === 'security') || s.status === 'responding';
          const nodeRadius = 6;
          
          ctx.beginPath();
          ctx.arc(pixelX, pixelY, nodeRadius, 0, 2 * Math.PI);
          ctx.fillStyle = s.role === 'medical' ? '#ef4444' : s.role === 'security' ? '#3b82f6' : '#10b981'; // red, blue, green
          ctx.fill();
          
          if (isEmergency) {
            ctx.beginPath();
            ctx.arc(pixelX, pixelY, nodeRadius * pulseScale, 0, 2 * Math.PI);
            ctx.strokeStyle = `rgba(${s.role === 'medical' ? '239, 68, 68' : '59, 130, 246'}, ${1.0 - (pulseScale - 1) / 0.4})`;
            ctx.lineWidth = 2;
            ctx.stroke();
          }
          
          ctx.beginPath();
          ctx.arc(pixelX, pixelY, 2, 0, 2 * Math.PI);
          ctx.fillStyle = '#ffffff';
          ctx.fill();
        });
      }

      animationFrameId = requestAnimationFrame(renderLoop);
    };

    animationFrameId = requestAnimationFrame(renderLoop);

    return () => {
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  // Dark mode aesthetics for the cards
  const getCapacityStyles = (pct: number, hasCriticalIncident: boolean) => {
    if (hasCriticalIncident) {
      return {
        card: 'bg-red-950/60 border-red-500/50 hover:border-red-400 text-red-200 shadow-sm ring-1 ring-red-500/50 animate-pulse-slow',
        progressBar: 'bg-red-500',
        text: 'text-red-400',
      };
    }

    if (pct < 30) {
      return {
        card: 'bg-emerald-950/40 border-emerald-500/30 hover:border-emerald-500/50 text-emerald-200 shadow-sm',
        progressBar: 'bg-emerald-500',
        text: 'text-emerald-400',
      };
    }
    if (pct < 60) {
      return {
        card: 'bg-slate-800/60 border-slate-700 hover:border-slate-600 text-slate-200 shadow-sm',
        progressBar: 'bg-emerald-400',
        text: 'text-slate-300',
      };
    }
    if (pct < 80) {
      return {
        card: 'bg-yellow-950/40 border-yellow-500/30 hover:border-yellow-500/50 text-yellow-200 shadow-sm',
        progressBar: 'bg-yellow-500',
        text: 'text-yellow-400',
      };
    }
    if (pct < 95) {
      return {
        card: 'bg-orange-950/50 border-orange-500/40 hover:border-orange-500/60 text-orange-200 shadow-sm',
        progressBar: 'bg-orange-500',
        text: 'text-orange-400',
      };
    }
    return {
      card: 'bg-red-950/50 border-red-500/60 hover:border-red-400 text-red-200 shadow-sm animate-pulse',
      progressBar: 'bg-red-600',
      text: 'text-red-400 font-bold',
    };
  };

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
    <div className="h-full w-full relative bg-slate-900/60 border border-slate-800/80 backdrop-blur-md rounded-xl overflow-hidden shadow-2xl shadow-slate-900/50">
      
      {/* Progress Timeline HUD */}
      {activeSimulation && (
        <div className="absolute top-4 left-4 z-20 w-96 bg-slate-900/90 p-3 rounded-lg border border-slate-700/80 backdrop-blur-md shadow-2xl flex flex-col gap-2">
          <div className="flex justify-between items-center">
            <span ref={timelineTextRef} className="text-xs font-bold text-amber-400 uppercase tracking-wider">
              {activeSimulation.name} - View progressive impact: 12s
            </span>
          </div>
          <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden border border-slate-700/50">
            <div ref={timelineFillRef} className="h-full bg-amber-500 rounded-full transition-none" style={{ width: '0%' }} />
          </div>
        </div>
      )}

      {/* Top-Right Mode Switcher */}
      <div className="absolute top-4 right-4 z-20 flex bg-slate-800/80 p-1 rounded-lg border border-slate-700/50 backdrop-blur-md">
        {(['density', 'flow', 'logistics'] as MapMode[]).map((m) => (
          <button
            key={m}
            onClick={() => {
              setMode(m);
              modeRef.current = m;
            }}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all ${
              mode === m
                ? 'bg-slate-700 text-white shadow-sm'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            {m.charAt(0).toUpperCase() + m.slice(1)}
          </button>
        ))}
      </div>

      {/* Grid container representation of the stadium graph */}
      <div className="absolute inset-0 grid grid-cols-4 gap-4 p-4 mt-16">
        {/* Render canvas layer */}
        <canvas
          ref={canvasRef}
          className="absolute inset-0 pointer-events-none w-full h-full rounded-xl z-10"
          style={{ mixBlendMode: mode === 'density' ? 'screen' : 'normal', opacity: mode === 'density' ? 0.8 : 1 }}
        />
        {zones.map((zone) => {
          const occ = occupancyMap.get(zone.id);
          const zoneIncidents = incidentMap.get(zone.id) || [];
          const zoneStaff = staffMap.get(zone.id) || [];

          const count = occ?.count ?? 0;
          const capacity = occ?.capacity ?? zone.capacity;
          const pct = Math.min(150, capacity > 0 ? (count / capacity) * 100 : 0);
          const trend = occ?.trend ?? 'stable';

          const hasCriticalIncident = zoneIncidents.some((i) => i.severity === 'critical' || i.severity === 'high');
          const styles = getCapacityStyles(pct, hasCriticalIncident);

          const positionClass = gridPositions[zone.id] || 'col-span-1';

          const isAffected = activeSimulation && activeSimulation.affectedZones.includes(zone.id);
          const overrideCardClass = isAffected 
            ? styles.card.replace(/border-[a-z]+-\d+(?:\/\d+)?/, 'border-amber-500/80 border-dashed animate-pulse shadow-[0_0_15px_rgba(245,158,11,0.2)] ring-1 ring-amber-500/50') 
            : styles.card;

          return (
            <div
              key={zone.id}
              onClick={() => onZoneClick?.(zone.id)}
              className={`rounded-xl border p-4 flex flex-col justify-between transition-all duration-300 cursor-pointer ${positionClass} ${overrideCardClass} z-0 relative backdrop-blur-sm`}
            >
              {/* Header */}
              <div className="flex items-start justify-between gap-1 mb-2">
                <div>
                  <h3 className={`font-semibold text-sm leading-snug tracking-wide ${styles.text}`}>{zone.name}</h3>
                  <span className="text-[10px] text-slate-400 font-mono tracking-wider uppercase">{zone.id}</span>
                </div>
                
                {/* Trend indicator */}
                <div className="flex items-center gap-1">
                  {trend === 'rising' && (
                    <span className="text-amber-500 font-semibold" title="Occupancy rising">
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
                      </svg>
                    </span>
                  )}
                  {trend === 'falling' && (
                    <span className="text-emerald-500 font-semibold" title="Occupancy falling">
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
                  <span className={`text-2xl font-bold tracking-tight ${styles.text}`}>
                    {Math.round(pct)}%
                  </span>
                  <span className="text-xs text-slate-400 font-mono">
                    {count.toLocaleString()} / {capacity.toLocaleString()}
                  </span>
                </div>

                {/* Progress bar */}
                <div className="w-full h-1.5 bg-slate-800/80 rounded-full overflow-hidden border border-slate-700/50">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${styles.progressBar}`}
                    style={{ width: `${Math.min(100, pct)}%` }}
                  />
                </div>
              </div>

              {/* Status / Incidents / Staff badges */}
              <div className="flex flex-wrap gap-1.5 mt-3 pt-2 border-t border-slate-700/50">
                {zoneIncidents.length > 0 ? (
                  <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium border ${
                    hasCriticalIncident 
                      ? 'bg-red-900/40 border-red-500/50 text-red-400 animate-pulse'
                      : 'bg-amber-900/40 border-amber-500/50 text-amber-400'
                  }`}>
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                    <span>{zoneIncidents.length} Incident{zoneIncidents.length > 1 ? 's' : ''}</span>
                  </span>
                ) : null}

                {zoneStaff.length > 0 ? (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium bg-indigo-900/40 border border-indigo-500/50 text-indigo-300">
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
                    </svg>
                    <span>{zoneStaff.length} Staff</span>
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium bg-slate-800/60 border border-slate-700/50 text-slate-400">
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
