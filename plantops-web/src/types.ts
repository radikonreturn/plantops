export type PlaybackSpeed = 1 | 2 | 4;

export type MachineState =
  | "IDLE"
  | "RUNNING"
  | "STARVED"
  | "BLOCKED"
  | "DOWN"
  | "PLANNED_MAINTENANCE";

export interface MachineMetric {
  state: MachineState;
  processed: number;
  scrap: number;
  failures: number;
  run_minutes: number;
  down_minutes: number;
  unplanned_downtime_minutes: number;
  planned_maintenance_minutes: number;
  maintenance_count: number;
  health: number;
  availability: number;
  performance: number;
}

export type OrderStatus =
  | "PENDING"
  | "ACTIVE"
  | "LATE"
  | "COMPLETED_ON_TIME"
  | "COMPLETED_LATE";

export interface CustomerOrder {
  id: string;
  quantity: number;
  fulfilled_quantity: number;
  remaining_quantity: number;
  release_minute: number;
  due_minute: number;
  priority: number;
  status: OrderStatus;
}

export interface OrderSummary {
  orders_total: number;
  orders_released: number;
  orders_due: number;
  orders_completed: number;
  orders_late: number;
  units_ordered: number;
  units_delivered: number;
  units_on_time: number;
  units_late: number;
  backlog_units: number;
  backlog_orders: number;
  otif: number | null;
  orders: CustomerOrder[];
}

export type PurchaseOrderStatus =
  | "OPEN"
  | "RECEIVED_ON_TIME"
  | "RECEIVED_LATE";

export interface PurchaseOrder {
  expedited?: boolean; expedite_cost?: number; expected_receipt_minute?: number; supplier_late?: boolean;
  id: string;
  supplier_id: string;
  quantity: number;
  placed_minute: number;
  promised_receipt_minute: number;
  actual_receipt_minute: number | null;
  unit_cost: number;
  total_committed_cost: number;
  status: PurchaseOrderStatus;
}

export interface SupplySummary {
  raw_material_on_hand: number;
  purchase_orders_total: number;
  purchase_orders_open: number;
  purchase_orders_received: number;
  purchase_orders_late: number;
  inbound_units: number;
  received_units: number;
  procurement_committed_cost: number;
  purchase_orders: PurchaseOrder[];
}

export interface BufferLevels {
  raw: number;
  after_cnc_01: number;
  after_wash_01: number;
  after_assembly_01: number;
  finished: number;
  [bufferId: string]: number;
}

export interface SimulationSummary {
  shift_events?: ShiftEvent[]; overtime?: OvertimeState; quality_containment?: ContainmentState;
  seed: number;
  simulated_minutes: number;
  shift_minutes: number;
  good_production: number;
  scrap: number;
  quality: number;
  oee: number;
  wip: number;
  raw_material_remaining: number;
  finished_goods_available: number;
  finished_goods_allocated: number;
  finished_goods_total: number;
  buffer_levels: BufferLevels;
  machine_metrics: Record<string, MachineMetric>;
  event_counts: Record<string, number>;
  order_summary: OrderSummary;
  supply_summary: SupplySummary;
}

export interface ShiftEvent {
  id: string; minute: number; end_minute: number; kind: string; title: string; detail: string;
  severity: "info" | "attention" | "critical"; zone: string; workspace: Workspace;
  state: "scheduled" | "active" | "resolved" | "expired"; affected_ids: string[]; closed_minute: number | null;
}
export interface OvertimeState {
  authorized: boolean; extension_minutes: number; normal_shift_minutes: number; labor_cost: number;
  fatigue_active: boolean; failure_multiplier: number; unavailable_reason: string | null;
}
export interface ContainmentState {
  available: boolean; active: boolean; unavailable_reason: string | null; inspected_units: number;
  added_inspection_minutes: number; inspection_cost: number; captured_units: number;
  customer_escapes: number; suspect_finished_units: number;
}
export interface CostBreakdown {
  emergency_repair: number; preventive_maintenance: number; procurement: number;
  expediting: number; overtime: number; inspection: number; total: number;
}
export interface TimelineEntry {id: string; minute: number; title: string; state: string; workspace: Workspace}
export interface SessionSnapshot {
  shift_events?: ShiftEvent[]; overtime?: OvertimeState; quality_containment?: ContainmentState;
  maintenance_history: ActionRecord[];
  cost_breakdown: CostBreakdown; timeline: TimelineEntry[];
  session_id: string;
  paused: boolean;
  speed: PlaybackSpeed;
  intervention_cost: number;
  preventive_maintenance_cost: number;
  summary: SimulationSummary;
  event_digest: string;
  scenario_profile: ScenarioProfile;
  action_log: ActionRecord[];
}

export interface CreateSessionInput {
  seed: number;
  failures_enabled: boolean;
  speed: PlaybackSpeed;
  scenario_mode?: "classic" | "seeded";
}

export const workspaces = ["Plant View", "Office / Inbox", "Production Plan", "Orders", "Maintenance", "Quality", "Inventory", "Reports"] as const;
export type Workspace = typeof workspaces[number];
export interface OperationalAlert {
  id: string; zone: string; severity: "info" | "attention" | "critical";
  message: string; workspace: Workspace;
}
export interface SceneZone {
  id: string; units: number; capacity: number | null;
  pallets: number; units_per_pallet: number; congested: boolean;
}
export interface AssetConfig {
  id: string; name: string; ideal_cycle_minutes: number; failure_risk: number;
  stage_role: "laser" | "cnc" | "wash" | "assembly" | "test" | "quality";
  fault_mode: string; status: MachineState; attention_reason: string | null;
  maintenance_available: boolean; maintenance_label: string; maintenance_unavailable_reason: string | null;
  maintenance_duration: number; maintenance_cost: number; scrap_probability: number;
  input_buffer: string; output_buffer: string;
}
export interface Supplier {
  id: string; name: string; min_lead_minutes: number; max_lead_minutes: number;
  late_probability: number; max_delay_minutes: number; unit_cost: number;
}
export interface ScenarioProfile {
  id: string; title: string; briefing: string; primary_zone: string | null; active_alerts: OperationalAlert[];
  machines: AssetConfig[]; suppliers: Supplier[];
  initial_conditions: {raw_units: number; wip: Record<string, number>; machine_health: Record<string, number>};
  scene: {zones: SceneZone[]; highlighted_zone: string | null;
    routes: {id: string; from: string; to: string; active: boolean; blocked: boolean; waiting_units: number; status: MachineState}[];
    machine_concerns: Record<string, string>;
    receiving: {inbound_units: number; open_purchase_orders: number; uncovered_demand: number};
    dispatch: {allocated_units: number; at_risk_orders: number};
    order_risks: Record<string, string>; order_forecasts: Record<string, number | null>};
  capacity: {bottleneck_cycle_minutes: number; bottleneck_machines: string[]; ideal_shift_units: number; estimate_note: string};
  decision_cards: DecisionCard[];
  shift_review: ShiftReview;
}
export interface ActionRecord {id: number; minute: number; kind: string; machine_id: string | null; detail: string}
export interface DecisionCard {
  id: string; title: string; detail: string; workspace: Workspace;
  status: string; decision_logged: boolean;
}
export interface ShiftReview {
  cost_breakdown: CostBreakdown; event_history: ShiftEvent[]; quality_containment: ContainmentState | null;
  state: "interim" | "final";
  headline: string;
  conclusion: string;
  actions_recorded: number;
  scorecard: {id: string; label: string; status: "good" | "attention" | "critical"; value: string}[];
}
