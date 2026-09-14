import { useEffect, useRef, useState } from "react";
import {
  advanceSession,
  createSession,
  expediteRepair,
  pauseSession,
  placePurchaseOrder,
  prioritizeOrder,
  resumeSession,
  setSessionSpeed,
  startPreventiveMaintenance,
} from "./api/plantops";
import { ControlBar } from "./components/ControlBar";
import { FactoryFloor } from "./components/FactoryFloor";
import { OperationsPanel } from "./components/OperationsPanel";
import { OrderBoard } from "./components/OrderBoard";
import type {
  CustomerOrder,
  PlaybackSpeed,
  SessionSnapshot,
} from "./types";

const DEFAULT_SEED = 42;

function describeError(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "The PlantOps API could not complete the request.";
}

export default function App() {
  const [session, setSession] = useState<SessionSnapshot | null>(null);
  const [seedValue, setSeedValue] = useState(String(DEFAULT_SEED));
  const [selectedMachineId, setSelectedMachineId] = useState("cnc_01");
  const [alert, setAlert] = useState<string | null>(null);
  const [busyLabel, setBusyLabel] = useState<string | null>("Initializing shift");
  const bootstrapped = useRef(false);
  const requestInFlight = useRef(false);
  const activeSessionId = useRef<string | null>(null);
  const sessionRef = useRef<SessionSnapshot | null>(null);

  useEffect(() => {
    sessionRef.current = session;
  }, [session]);

  async function createPausedShift(seed: number) {
    if (requestInFlight.current) return;
    requestInFlight.current = true;
    setBusyLabel("Creating new shift");
    setAlert(null);
    try {
      const created = await createSession({
        seed,
        failures_enabled: true,
        speed: 1,
      });
      const paused = await pauseSession(created.session_id);
      activeSessionId.current = paused.session_id;
      sessionRef.current = paused;
      setSession(paused);
      setSelectedMachineId("cnc_01");
    } catch (error) {
      setAlert(describeError(error));
    } finally {
      requestInFlight.current = false;
      setBusyLabel(null);
    }
  }

  useEffect(() => {
    if (bootstrapped.current) return;
    bootstrapped.current = true;
    void createPausedShift(DEFAULT_SEED);
  }, []);

  async function updateCurrentSession(
    label: string,
    operation: (sessionId: string) => Promise<SessionSnapshot>,
  ) {
    const current = sessionRef.current;
    if (!current || requestInFlight.current) return;
    const targetSessionId = current.session_id;
    requestInFlight.current = true;
    setBusyLabel(label);
    setAlert(null);
    try {
      const updated = await operation(targetSessionId);
      if (activeSessionId.current === targetSessionId) {
        sessionRef.current = updated;
        setSession(updated);
      }
    } catch (error) {
      setAlert(describeError(error));
    } finally {
      requestInFlight.current = false;
      setBusyLabel(null);
    }
  }

  useEffect(() => {
    if (!session || session.paused) return;
    if (session.summary.simulated_minutes >= session.summary.shift_minutes) return;

    const timer = window.setInterval(() => {
      const current = sessionRef.current;
      if (!current || current.paused || requestInFlight.current) return;
      const remaining = current.summary.shift_minutes - current.summary.simulated_minutes;
      if (remaining <= 0) return;

      const targetSessionId = current.session_id;
      const advanceMinutes = Math.min(current.speed, remaining);
      requestInFlight.current = true;
      setBusyLabel("Advancing simulation");

      void (async () => {
        try {
          let updated = await advanceSession(targetSessionId, advanceMinutes);
          if (updated.summary.simulated_minutes >= updated.summary.shift_minutes) {
            updated = await pauseSession(targetSessionId);
          }
          if (activeSessionId.current === targetSessionId) {
            sessionRef.current = updated;
            setSession(updated);
          }
        } catch (error) {
          setAlert(describeError(error));
        } finally {
          requestInFlight.current = false;
          setBusyLabel(null);
        }
      })();
    }, 1000);

    return () => window.clearInterval(timer);
  }, [session?.session_id, session?.paused]);

  function handleNewShift() {
    const seed = Number(seedValue);
    if (!Number.isInteger(seed) || seed < 0) {
      setAlert("Replay seed must be a non-negative integer.");
      return;
    }
    void createPausedShift(seed);
  }

  function handleTogglePlayback() {
    if (!session) return;
    void updateCurrentSession(
      session.paused ? "Starting shift" : "Pausing shift",
      session.paused ? resumeSession : pauseSession,
    );
  }

  function handleSpeedChange(speed: PlaybackSpeed) {
    if (session?.speed === speed) return;
    void updateCurrentSession(`Setting ${speed}× speed`, (sessionId) =>
      setSessionSpeed(sessionId, speed),
    );
  }

  function handleRushOrder(order: CustomerOrder) {
    const nextPriority = Math.min(100, order.priority + 10);
    void updateCurrentSession(`Rushing ${order.id}`, (sessionId) =>
      prioritizeOrder(sessionId, order.id, nextPriority),
    );
  }

  const busy = busyLabel !== null;

  return (
    <div className="app-shell">
      <ControlBar
        session={session}
        seedValue={seedValue}
        busy={busy}
        onSeedChange={setSeedValue}
        onTogglePlayback={handleTogglePlayback}
        onSpeedChange={handleSpeedChange}
        onNewShift={handleNewShift}
      />

      {session ? (
        <main className="operations-workspace">
          <FactoryFloor
            machineMetrics={session.summary.machine_metrics}
            bufferLevels={session.summary.buffer_levels}
            finishedGoodsAvailable={session.summary.finished_goods_available}
            selectedMachineId={selectedMachineId}
            onSelectMachine={setSelectedMachineId}
          />
          <OperationsPanel
            session={session}
            selectedMachineId={selectedMachineId}
            alert={alert}
            busy={busy}
            busyLabel={busyLabel}
            onDismissAlert={() => setAlert(null)}
            onExpediteRepair={(machineId) =>
              void updateCurrentSession("Dispatching repair crew", (sessionId) =>
                expediteRepair(sessionId, machineId),
              )
            }
            onStartMaintenance={(machineId) =>
              void updateCurrentSession("Starting preventive maintenance", (sessionId) =>
                startPreventiveMaintenance(sessionId, machineId),
              )
            }
            onPlacePurchaseOrder={(quantity) =>
              void updateCurrentSession("Placing purchase order", (sessionId) =>
                placePurchaseOrder(sessionId, "STEEL-01", quantity),
              )
            }
          />
          <OrderBoard
            orderSummary={session.summary.order_summary}
            simulatedMinutes={session.summary.simulated_minutes}
            busy={busy}
            onRushOrder={handleRushOrder}
          />
        </main>
      ) : (
        <main className="startup-state">
          <div className="startup-state__mark" aria-hidden="true">
            <span />
            <span />
            <span />
          </div>
          <h2>Connecting to PlantOps control</h2>
          <p>{alert ?? "Creating deterministic shift session with seed 42…"}</p>
          {alert ? (
            <button type="button" onClick={() => void createPausedShift(DEFAULT_SEED)} disabled={busy}>
              Retry connection
            </button>
          ) : null}
        </main>
      )}

      <footer className="system-footer">
        <span>PLANTOPS CONTROL / IN-MEMORY MVP</span>
        <span>{session ? `SESSION ${session.session_id.slice(0, 8).toUpperCase()}` : "SESSION PENDING"}</span>
        <span>{session ? `DIGEST ${session.event_digest.slice(0, 12).toUpperCase()}` : "DIGEST —"}</span>
      </footer>
    </div>
  );
}
