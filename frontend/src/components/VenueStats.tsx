import React from 'react';

interface VenueStatsProps {
  name: string;
  currentLoad: number;
  totalCapacity: number;
}

export function VenueStats({ name, currentLoad, totalCapacity }: VenueStatsProps): React.JSX.Element {
  const loadPercentage = totalCapacity > 0 ? (currentLoad / totalCapacity) * 100 : 0;
  
  // Concentric Radial Gauge Specifications
  // We use strict arithmetic for stroke offsets to prevent React re-render lag
  const size = 200;
  const center = size / 2;
  const strokeWidth = 8;
  const gap = 4;
  
  // Outer Ring: Maps Flow/Capacity Boundary metrics
  const radiusOuter = 80;
  const circumferenceOuter = 2 * Math.PI * radiusOuter;
  // Flow boundary: We can map this to show loadPercentage vs total (0-100%)
  const progressOuter = Math.min(Math.max(loadPercentage, 0), 100) / 100;
  const offsetOuter = circumferenceOuter - (progressOuter * circumferenceOuter);
  
  // Middle Ring: Maps Optimal Capacity tracking
  const radiusMiddle = radiusOuter - strokeWidth - gap;
  const circumferenceMiddle = 2 * Math.PI * radiusMiddle;
  // Optimal capacity: Maps up to 80% as a full ring
  const progressMiddle = Math.min(Math.max(loadPercentage, 0), 80) / 80;
  const offsetMiddle = circumferenceMiddle - (progressMiddle * circumferenceMiddle);
  
  // Inner Ring: Maps Low Capacity tracking
  const radiusInner = radiusMiddle - strokeWidth - gap;
  const circumferenceInner = 2 * Math.PI * radiusInner;
  // Low capacity: Maps up to 30% as a full ring
  const progressInner = Math.min(Math.max(loadPercentage, 0), 30) / 30;
  const offsetInner = circumferenceInner - (progressInner * circumferenceInner);

  return (
    <div className="premium-card flex flex-col items-center justify-center relative w-full">
      <h2 className="text-slate-100 font-bold tracking-wider uppercase text-sm w-full text-left mb-6">{name}</h2>
      
      <div className="relative flex items-center justify-center w-full" style={{ height: size }}>
        {/* SVG Wrapper with -rotate-90 to start from top (12 o'clock) */}
        <svg 
          className="absolute transform -rotate-90" 
          width={size} 
          height={size} 
          viewBox={`0 0 ${size} ${size}`}
        >
          <defs>
            <linearGradient id="venueGreenGradient" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#064e3b" />   {/* forest green */}
              <stop offset="50%" stopColor="#10b981" />  {/* vibrant emerald */}
              <stop offset="100%" stopColor="#34d399" /> {/* mint green */}
            </linearGradient>
          </defs>
          
          {/* --- Outer Ring Background & Progress --- */}
          <circle 
            cx={center} cy={center} r={radiusOuter} 
            fill="none" stroke="#1e293b" strokeWidth={strokeWidth} 
          />
          <circle 
            cx={center} cy={center} r={radiusOuter} 
            fill="none" stroke="url(#venueGreenGradient)" strokeWidth={strokeWidth}
            strokeDasharray={circumferenceOuter} 
            strokeDashoffset={offsetOuter} 
            strokeLinecap="round"
            className="transition-all duration-700 ease-out" 
          />
            
          {/* --- Middle Ring Background & Progress --- */}
          <circle 
            cx={center} cy={center} r={radiusMiddle} 
            fill="none" stroke="#1e293b" strokeWidth={strokeWidth} 
          />
          <circle 
            cx={center} cy={center} r={radiusMiddle} 
            fill="none" stroke="url(#venueGreenGradient)" strokeWidth={strokeWidth}
            strokeDasharray={circumferenceMiddle} 
            strokeDashoffset={offsetMiddle} 
            strokeLinecap="round"
            className="transition-all duration-700 ease-out delay-75" 
          />
            
          {/* --- Inner Ring Background & Progress --- */}
          <circle 
            cx={center} cy={center} r={radiusInner} 
            fill="none" stroke="#1e293b" strokeWidth={strokeWidth} 
          />
          <circle 
            cx={center} cy={center} r={radiusInner} 
            fill="none" stroke="url(#venueGreenGradient)" strokeWidth={strokeWidth}
            strokeDasharray={circumferenceInner} 
            strokeDashoffset={offsetInner} 
            strokeLinecap="round"
            className="transition-all duration-700 ease-out delay-150" 
          />
        </svg>
        
        {/* Center Stack Overlay */}
        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none z-10">
          <span className="text-2xl font-bold text-slate-100">{Math.round(loadPercentage)}% Load</span>
          <span className="text-metadata font-mono text-xs mt-1">
            {currentLoad.toLocaleString()} / {totalCapacity.toLocaleString()}
          </span>
        </div>
      </div>
    </div>
  );
}
