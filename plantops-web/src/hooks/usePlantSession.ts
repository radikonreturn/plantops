import { useCallback, useEffect, useRef, useState } from "react";
import * as api from "../api/plantops";
import type { PlaybackSpeed, SessionSnapshot } from "../types";

export function usePlantSession() {
  const [session, setSession] = useState<SessionSnapshot | null>(null);
  const current = useRef<SessionSnapshot | null>(null);
  const locked = useRef(false);
  const newShiftPending = useRef(false);
  const commandPending = useRef(false);
  const initialized = useRef(false);
  const mounted = useRef(true);
  const hold = useRef(false);
  const [busy, setBusy] = useState<string | null>("Opening shift");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState("Preparing the shift handover…");
  const [connectionHold, setConnectionHold] = useState(false);
  const publish = useCallback((snapshot: SessionSnapshot) => {
    current.current = snapshot;
    if (mounted.current) setSession(snapshot);
  }, []);
  const fail = useCallback((reason: unknown) => {
    hold.current = true;
    if (mounted.current) {
      setConnectionHold(true);
      setError(reason instanceof Error ? reason.message : "Request failed. Inspect the API response and retry.");
    }
  }, []);
  const newShift = useCallback(async (seed: number) => {
    if (newShiftPending.current || commandPending.current) return false;
    if (!Number.isSafeInteger(seed) || seed < 0) {
      setError("Replay seed must be a whole number from 0 to 9007199254740991."); return false;
    }
    newShiftPending.current = true; setBusy("Opening shift"); setError(null);
    while (locked.current) await new Promise(resolve => window.setTimeout(resolve, 30));
    locked.current = true;
    try {
      if (current.current && !current.current.paused) publish(await api.pauseSession(current.current.session_id));
      const created = await api.createSession({seed, speed: 1, failures_enabled: true, scenario_mode: "seeded"});
      // Retain the ID if the initial pause response is lost.
      publish(created); publish(await api.pauseSession(created.session_id));
      hold.current = false; setConnectionHold(false);
      setNotice("Shift ready. Review the handover in Office / Inbox, then start when ready.");
      return true;
    } catch (reason) { fail(reason); return false; }
    finally { locked.current = false; newShiftPending.current = false; if (mounted.current) setBusy(null); }
  }, [fail, publish]);
  const act = useCallback(async (message: string, operation: (id: string) => Promise<SessionSnapshot>) => {
    if (locked.current || !current.current) return false;
    locked.current = true; setBusy(message); setError(null);
    try { publish(await operation(current.current.session_id)); setNotice(message); return true; }
    catch (reason) {
      fail(reason);
      // Reconcile a potentially accepted action; never retry a chargeable command.
      try { publish(await api.getSession(current.current.session_id)); } catch { /* Preserve original error. */ }
      return false;
    } finally { locked.current = false; if (mounted.current) setBusy(null); }
  }, [fail, publish]);
  useEffect(() => {
    mounted.current = true;
    if (!initialized.current) { initialized.current = true; void newShift(42); }
    const timer = window.setInterval(() => {
      const snapshot = current.current;
      if (!snapshot || snapshot.paused || hold.current || locked.current || newShiftPending.current || commandPending.current) return;
      locked.current = true;
      void (async () => {
        try {
          const remaining = snapshot.summary.shift_minutes - snapshot.summary.simulated_minutes;
          let next = remaining > 0 ? await api.advanceSession(snapshot.session_id, Math.min(remaining, snapshot.speed)) : snapshot;
          publish(next);
          if (next.summary.simulated_minutes >= next.summary.shift_minutes) {
            next = await api.pauseSession(snapshot.session_id); publish(next);
            setNotice("Shift complete. Open Reports to review delivery performance and costs.");
          }
        } catch (reason) {
          fail(reason);
          try { publish(await api.getSession(snapshot.session_id)); } catch { /* Preserve original error. */ }
        } finally { locked.current = false; }
      })();
    }, 1000);
    return () => { mounted.current = false; window.clearInterval(timer); };
  }, [newShift, publish, fail]);
  const command = useCallback(async (message: string, operation: (id: string) => Promise<SessionSnapshot>) => {
    if (busy || commandPending.current || newShiftPending.current) return false;
    commandPending.current = true;
    setBusy(message);
    try {
      while (locked.current) await new Promise(resolve => window.setTimeout(resolve, 30));
      return await act(message, operation);
    } finally { commandPending.current = false; }
  }, [act, busy]);
  return {
    session, busy, error, notice, connectionHold, newShift,
    toggle: () => command("Playback updated", async id => {
      const fresh = await api.getSession(id);
      const next = hold.current || fresh.paused
        ? (fresh.summary.simulated_minutes >= fresh.summary.shift_minutes ? await api.pauseSession(id) : await api.resumeSession(id))
        : await api.pauseSession(id);
      hold.current = false; setConnectionHold(false); return next;
    }),
    speed: (speed: PlaybackSpeed) => command(`Playback speed set to ${speed}×`, id => api.setSessionSpeed(id, speed)),
    prioritize: (orderId: string, priority: number) => command(`${orderId} priority saved as ${priority}`, id => api.prioritizeOrder(id, orderId, priority)),
    purchase: (supplierId: string, quantity: number) => command(`Purchase order placed: ${quantity} units from ${supplierId}`, id => api.placePurchaseOrder(id, supplierId, quantity)),
    repair: (machineId: string) => command(`${machineId} emergency repair completed`, id => api.expediteRepair(id, machineId)),
    maintain: (machineId: string) => command(`${machineId} preventive maintenance started`, id => api.startPreventiveMaintenance(id, machineId)),
  };
}
export type PlantSession = ReturnType<typeof usePlantSession>;
