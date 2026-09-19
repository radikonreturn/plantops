import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useI18n } from "../i18n";
import { localizeSession } from "../i18n/backend";
import { message, resolveMessage, type Message } from "../i18n/core";
import { readStored, writeStored } from "../tutorial/state";
import * as api from "../api/plantops";
import type { Difficulty, EquipmentAction, PlaybackSpeed, SessionSnapshot } from "../types";

export function usePlantSession() {
  const { locale } = useI18n();
  const [session, setSession] = useState<SessionSnapshot | null>(null);
  const current = useRef<SessionSnapshot | null>(null);
  const locked = useRef(false);
  const newShiftPending = useRef(false);
  const commandPending = useRef(false);
  const initialized = useRef(false);
  const mounted = useRef(true);
  const hold = useRef(false);
  const [busy, setBusy] = useState<Message | null>(null);
  const [error, setError] = useState<Message | string | null>(null);
  const [notice, setNotice] = useState(message("Choose a shift to begin."));
  const [connectionHold, setConnectionHold] = useState(false);
  const publish = useCallback((snapshot: SessionSnapshot) => {
    current.current = snapshot;
    writeStored("sessionStorage", "plantops.activeSession", snapshot.session_id);
    if (mounted.current) setSession(snapshot);
  }, []);
  const fail = useCallback((reason: unknown) => {
    hold.current = true;
    if (mounted.current) {
      setConnectionHold(true);
      setError(reason instanceof api.PlantOpsConnectionError
        ? message("Cannot reach PlantOps at {base} for {method} {path}. Check that dev:full is running.", { base: api.API_BASE_URL, method: reason.method, path: reason.path })
        : reason instanceof api.PlantOpsApiError && !reason.hasDetail
        ? message("PlantOps API request failed ({status})", { status: reason.status })
        : reason instanceof Error ? reason.message : message("Request failed. Inspect the API response and retry."));
    }
  }, []);
  const newShift = useCallback(async (
    seed: number,
    mode: "seeded" | "tutorial" = "seeded",
    difficulty: Difficulty = "normal",
  ) => {
    if (newShiftPending.current || commandPending.current) return false;
    if (!Number.isSafeInteger(seed) || seed < 0) {
      setError(message("Replay seed must be a whole number from 0 to 9007199254740991.")); return false;
    }
    newShiftPending.current = true; setBusy(message("Opening shift")); setError(null);
    while (locked.current) await new Promise(resolve => window.setTimeout(resolve, 30));
    locked.current = true;
    try {
      if (current.current && !current.current.paused) publish(await api.pauseSession(current.current.session_id));
      const created = await api.createSession({seed, speed: 1, failures_enabled: true, scenario_mode: mode, difficulty});
      // Retain the ID if the initial pause response is lost.
      publish(created); publish(await api.pauseSession(created.session_id));
      hold.current = false; setConnectionHold(false);
      window.location.hash = encodeURIComponent("Office / Inbox");
      setNotice(message("Shift ready. Review the handover in Office / Inbox, then start when ready."));
      return true;
    } catch (reason) { fail(reason); return false; }
    finally { locked.current = false; newShiftPending.current = false; if (mounted.current) setBusy(null); }
  }, [fail, publish]);
  const returnToMenu = useCallback(async () => {
    if (locked.current || newShiftPending.current || commandPending.current) return false;
    locked.current = true; setBusy(message("Saving shift")); setError(null);
    try {
      let snapshot = current.current;
      if (snapshot && !snapshot.paused) snapshot = await api.pauseSession(snapshot.session_id);
      if (snapshot) publish(snapshot);
      if (mounted.current) setSession(null);
      window.location.hash = "";
      setNotice(message("Shift saved. Resume it from the main menu when ready."));
      return true;
    } catch (reason) { fail(reason); return false; }
    finally { locked.current = false; if (mounted.current) setBusy(null); }
  }, [fail, publish]);
  const act = useCallback(async (message: Message, operation: (id: string) => Promise<SessionSnapshot>) => {
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
  const restoreSession = useCallback(async () => {
    const saved = readStored("sessionStorage", "plantops.activeSession");
    if (!saved || locked.current) return;
    locked.current = true; setBusy(message("Restoring shift")); setError(null);
    try {
      const fresh = await api.getSession(saved);
      publish(fresh.paused ? fresh : await api.pauseSession(saved));
      hold.current = false; setConnectionHold(false);
      setNotice(message("Shift restored on control hold. Review the current state before resuming."));
    } catch (reason) {
      if (reason instanceof api.PlantOpsApiError && reason.status === 404) {
        writeStored("sessionStorage", "plantops.activeSession", null);
        setNotice(message("The previous in-memory shift is no longer available. Open a new shift or replay the tutorial."));
      } else fail(reason);
    } finally { locked.current = false; if (mounted.current) setBusy(null); }
  }, [publish, fail]);
  useEffect(() => {
    mounted.current = true;
    if (!initialized.current) { initialized.current = true; void restoreSession(); }
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
            setNotice(message("Shift complete. Open Reports to review delivery performance and costs."));
          }
        } catch (reason) {
          fail(reason);
          try { publish(await api.getSession(snapshot.session_id)); } catch { /* Preserve original error. */ }
        } finally { locked.current = false; }
      })();
    }, 1000);
    return () => { mounted.current = false; window.clearInterval(timer); };
  }, [restoreSession, publish, fail]);
  const command = useCallback(async (message: Message, operation: (id: string) => Promise<SessionSnapshot>) => {
    if (busy || commandPending.current || newShiftPending.current) return false;
    commandPending.current = true;
    setBusy(message);
    try {
      while (locked.current) await new Promise(resolve => window.setTimeout(resolve, 30));
      return await act(message, operation);
    } finally { commandPending.current = false; }
  }, [act, busy]);
  const displaySession = useMemo(() => session ? localizeSession(session, locale) : null, [session, locale]);
  return {
    session: displaySession,
    busy: resolveMessage(locale, busy), error: resolveMessage(locale, error), notice: resolveMessage(locale, notice),
    connectionHold, newShift, restoreSession, returnToMenu,
    overtime: () => command(message("Overtime authorized: 60 minutes / 600 labor cost"), id => api.livingAction(id, "authorize-overtime")),
    contain: () => command(message("Quality containment activated"), id => api.livingAction(id, "activate-containment")),
    expeditePurchase: (poId: string) => command(message("{value1} expedited / 120 cost", {value1: poId}), id => api.livingAction(id, "expedite-purchase-order", poId)),
    toggle: () => command(message("Playback updated"), async id => {
      const fresh = await api.getSession(id);
      const next = hold.current || fresh.paused
        ? (fresh.summary.simulated_minutes >= fresh.summary.shift_minutes ? await api.pauseSession(id) : await api.resumeSession(id))
        : await api.pauseSession(id);
      hold.current = false; setConnectionHold(false); return next;
    }),
    speed: (speed: PlaybackSpeed) => command(message("Playback speed set to {value1}×", {value1: speed}), id => api.setSessionSpeed(id, speed)),
    prioritize: (orderId: string, priority: number) => command(message("{value1} priority saved as {value2}", {value1: orderId, value2: priority}), id => api.prioritizeOrder(id, orderId, priority)),
    purchase: (supplierId: string, quantity: number) => command(message("Purchase order placed: {value1} units from {value2}", {value1: quantity, value2: supplierId}), id => api.placePurchaseOrder(id, supplierId, quantity)),
    repair: (machineId: string) => command(message("{value1} emergency repair completed", {value1: machineId}), id => api.expediteRepair(id, machineId)),
    service: (machineId: string, action: EquipmentAction) => command(message("{value1} service requested", {value1: machineId}), id => api.equipmentAction(id, machineId, action)),
    maintain: (machineId: string) => command(message("{value1} preventive maintenance started", {value1: machineId}), id => api.startPreventiveMaintenance(id, machineId)),
  };
}
export type PlantSession = ReturnType<typeof usePlantSession>;
