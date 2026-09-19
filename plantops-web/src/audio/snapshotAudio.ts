import type { MachineState, SessionSnapshot } from "../types";
import type { AudioCue } from "./audioTypes";

export interface AudioFrame {
  session: string;
  minute: number;
  ended: boolean;
  paused: boolean;
  machines: Record<string, { state: MachineState; failures: number }>;
  orders: Record<string, "none" | "due" | "late">;
  received: number;
  production: number;
  conveyor: boolean;
}
// Retain only primitive audio observations, never references into API state.
export function audioFrame(snapshot: SessionSnapshot): AudioFrame {
  const s = snapshot.summary;
  return {
    session: snapshot.session_id, minute: s.simulated_minutes,
    ended: s.simulated_minutes >= s.shift_minutes, paused: snapshot.paused,
    machines: Object.fromEntries(Object.entries(s.machine_metrics).map(([id, m]) => [id, { state: m.state, failures: m.failures }])),
    orders: Object.fromEntries(s.order_summary.orders.map(o => [o.id,
      o.remaining_quantity <= 0 || o.release_minute > s.simulated_minutes ? "none" :
        o.status === "LATE" || s.simulated_minutes > o.due_minute ? "late" :
          o.due_minute - s.simulated_minutes <= 30 ? "due" : "none"])),
    received: s.supply_summary.received_units, production: s.good_production,
    conveyor: snapshot.scenario_profile.scene.routes.some(r => r.active && !r.blocked) && Object.values(s.machine_metrics).some(m => m.state === "RUNNING"),
  };
}
export function audioTransitions(previous: AudioFrame, next: AudioFrame): AudioCue[] {
  const cues = new Set<AudioCue>();
  for (const [id, machine] of Object.entries(next.machines)) {
    const old = previous.machines[id];
    if (!old) continue;
    if (machine.failures > old.failures || (machine.state === "DOWN" && old.state !== "DOWN")) cues.add("failure");
    if (machine.state === old.state) continue;
    if (machine.state === "PLANNED_MAINTENANCE") cues.add("maintenanceStart");
    if (["DOWN", "PLANNED_MAINTENANCE"].includes(old.state) && !["DOWN", "PLANNED_MAINTENANCE"].includes(machine.state)) cues.add("maintenanceEnd");
    if (["STARVED", "BLOCKED"].includes(machine.state)) cues.add("flowWarning");
  }
  for (const [id, phase] of Object.entries(next.orders)) {
    if (previous.orders[id] !== phase && phase !== "none") cues.add(phase);
  }
  if (next.received > previous.received) cues.add("delivery");
  if (next.production > previous.production) cues.add("production");
  if (!previous.ended && next.ended) cues.add("shiftEnd");
  return [...cues];
}
export const cuePriority: AudioCue[] = ["failure", "late", "maintenanceStart", "maintenanceEnd", "delivery", "shiftEnd", "due", "flowWarning", "production"];
