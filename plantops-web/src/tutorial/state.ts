import type { SessionSnapshot } from "../types";

export interface TutorialProgress {
  sessionId: string;
  handoverRead: boolean;
  plantVisited: boolean;
  assetInspected: boolean;
  runFirst: boolean;
  reviewed: boolean;
  dismissed: boolean;
}
export type StorageArea = "localStorage" | "sessionStorage";
export function readStored(area: StorageArea, key: string): string | null {
  try { return window[area].getItem(key); } catch { return null; }
}
export function writeStored(area: StorageArea, key: string, value: string | null): void {
  try {
    if (value === null) window[area].removeItem(key);
    else window[area].setItem(key, value);
  } catch { /* Private browsing or denied storage must not block a shift. */ }
}
export function emptyProgress(sessionId: string): TutorialProgress {
  return {sessionId, handoverRead: false, plantVisited: false, assetInspected: false, runFirst: false, reviewed: false, dismissed: false};
}
export function restoreProgress(sessionId: string): TutorialProgress {
  const fresh = emptyProgress(sessionId);
  try {
    const saved = JSON.parse(readStored("sessionStorage", "plantops.tutorial.progress") ?? "null");
    if (!saved || saved.sessionId !== sessionId) return fresh;
    for (const key of ["handoverRead", "plantVisited", "assetInspected", "runFirst", "reviewed", "dismissed"] as const) fresh[key] = saved[key] === true;
  } catch { /* Corrupt progress is safely restarted at the handover. */ }
  return fresh;
}
export function tutorialStep(session: SessionSnapshot, progress: TutorialProgress): number | null {
  if (session.scenario_profile.id !== "tutorial-v1" || progress.sessionId !== session.session_id || progress.dismissed) return null;
  if (!progress.handoverRead) return 1;
  if (!progress.plantVisited) return 2;
  if (!progress.assetInspected) return 3;
  const laser = session.summary.machine_metrics.laser_01;
  const acted = session.action_log.some(a => a.machine_id === "laser_01" && ["EQUIPMENT_SERVICE_REQUESTED", "PLANNED_MAINTENANCE_STARTED"].includes(a.kind));
  if (!acted && !progress.runFirst && session.summary.simulated_minutes === 0) return 4;
  const closed = session.summary.simulated_minutes >= session.summary.shift_minutes;
  const observed = session.summary.simulated_minutes >= 20 && laser.processed > 0 && !laser.service?.pending && !laser.service?.active && laser.state !== "PLANNED_MAINTENANCE";
  if (!closed && !observed) return 5;
  return progress.reviewed ? 7 : 6;
}
