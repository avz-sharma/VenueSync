export interface IntensityPoint {
  x: number;
  y: number;
  intensity: number;
  vx?: number;
  vy?: number;
}

export interface Zone {
  id: string;
  name: string;
  capacity: number;
  adjacent_zones: string[];
  heatmap_points?: IntensityPoint[];
}

export interface Occupancy {
  zone_id: string;
  count: number;
  capacity: number;
  pct_capacity: number;
  trend: 'rising' | 'falling' | 'stable';
}

export interface Incident {
  id: string;
  zone_id: string;
  type: 'medical' | 'security' | 'overcrowding' | 'equipment_failure' | 'weather';
  severity: 'low' | 'medium' | 'high' | 'critical';
  reported_at: string;
}

export interface Staff {
  id: string;
  role: 'security' | 'medical' | 'operations' | 'hospitality';
  zone_id: string;
  status: 'on_duty' | 'off_duty' | 'break' | 'responding';
}

export interface VenueSnapshot {
  timestamp: string;
  zones: Zone[];
  occupancies: Occupancy[];
  incidents: Incident[];
  staff: Staff[];
}

export interface ActionRecommendation {
  id: string;
  action_type: string;
  priority: number;
  target_zones: string[];
  confidence: number;
  rationale: string;
  predicted_impact: string;
}

export interface ReasoningCycleOutput {
  actions: ActionRecommendation[];
  degraded_mode: boolean;
  venue_summary: string;
}

export interface ApproveResponse {
  status: string;
  action_id: string;
  already_approved: boolean;
  message: string;
}

export interface LoadScenarioResponse {
  status: string;
  message: string;
}

// ---------------------------------------------------------------------------
// Pre-Alert Engine types (Component 1)
// ---------------------------------------------------------------------------

export interface PreAlertRecommendation {
  zone_id: string;
  zone_name: string;
  risk_level: 'elevated' | 'high' | 'imminent';
  estimated_minutes_to_critical: number;
  preemptive_action: string;
  confidence: number;
  rationale: string;
}

export interface PreAlertOutput {
  alerts: PreAlertRecommendation[];
  degraded_mode: boolean;
}

// ---------------------------------------------------------------------------
// Operator Chat types (Component 2)
// ---------------------------------------------------------------------------

export interface OperatorQueryResponse {
  answer: string;
  supporting_data: string[];
  confidence: number;
  degraded_mode: boolean;
}

// ---------------------------------------------------------------------------
// GenAI Scenario Planner types (Component 3)
// ---------------------------------------------------------------------------

export interface ScenarioIntent {
  target_zone: string;
  intent_type: 'overwhelm' | 'evacuate' | 'incident_inject' | 'capacity_shift';
  intensity: number;
  description: string;
}

export interface ScenarioSpec {
  name: string;
  narrative: string;
  intents: ScenarioIntent[];
  estimated_duration_seconds: number;
}

export interface GenerateScenarioResponse {
  status: string;
  scenario: ScenarioSpec;
  message: string;
}

