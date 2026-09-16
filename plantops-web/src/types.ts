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

export interface SessionSnapshot {
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
  maintenance_duration: number; maintenance_cost: number; scrap_probability: number;
  input_buffer: string; output_buffer: string;
}
export interface Supplier {
  id: string; name: string; min_lead_minutes: number; max_lead_minutes: number;
  late_probability: number; max_delay_minutes: number; unit_cost: number;
}
export interface ScenarioProfile {
  id: string; title: string; briefing: string; active_alerts: OperationalAlert[];
  machines: AssetConfig[]; suppliers: Supplier[];
  initial_conditions: {raw_units: number; wip: Record<string, number>; machine_health: Record<string, number>};
  scene: {zones: SceneZone[]; highlighted_zone: string | null;
    routes: {id: string; from: string; to: string; active: boolean}[];
    order_risks: Record<string, string>};
  capacity: {bottleneck_cycle_minutes: number; ideal_shift_units: number; estimate_note: string};
}
export interface ActionRecord {id: number; minute: number; kind: string; machine_id: string | null; detail: string}
