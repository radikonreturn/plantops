import { useState } from "react";
import type { PlantSession } from "../hooks/usePlantSession";
import { clock, percent } from "../format";
import { Modal } from "./Modal";
export function ControlBar({control}: {control: PlantSession}) {
  const {session, busy} = control;
  const [newShiftOpen, setNewShiftOpen] = useState(false);
  const [seed, setSeed] = useState("");
  const s = session?.summary;
  const ended = !!s && s.simulated_minutes >= s.shift_minutes;
  const paused = !session || session.paused || control.connectionHold;
  const opName = localStorage.getItem("plantops.operatorName");
  return <>
    <header className="app-header">
      <div className="brand"><svg viewBox="0 0 30 30" aria-hidden="true"><path d="M3 26V12l8-5v7l8-5v7h8v10ZM5 5h4v5M8 20h3m5 0h3m4 0h2" /></svg><strong>PlantOps</strong></div>
      <div className="plant-identity"><strong>Artemis Manufacturing</strong><span>{opName ? `Op: ${opName} · Plant 01` : "Plant 01 · Component line A"}</span></div>
      <div className="header-clock"><strong>{clock(s?.simulated_minutes ?? 0)}</strong><span>/ {clock(s?.shift_minutes ?? 480)}</span><progress aria-label="Shift progress" max={s?.shift_minutes ?? 480} value={s?.simulated_minutes ?? 0} /></div>
      <div className="header-kpis"><span>Production <b>{s?.good_production ?? 0}</b></span><span>OEE <b>{percent(s?.oee ?? null)}</b></span><span>OTIF <b>{percent(s?.order_summary.otif ?? null)}</b></span><span>WIP / backlog <b>{s?.wip ?? 0} / {s?.order_summary.backlog_units ?? 0}</b></span></div>
      <div className="shift-buttons"><button className="primary" disabled={!!busy || !session || (ended && session.paused)} onClick={() => void control.toggle()}>{ended ? "Shift complete" : control.connectionHold ? "Reconnect" : paused ? "Start shift" : "Pause"}</button><div className="speed-group" aria-label="Playback speed">{([1, 2, 4] as const).map(speed => <button key={speed} aria-pressed={session?.speed === speed} disabled={!!busy || !session} onClick={() => void control.speed(speed)}>{speed}×</button>)}</div><button disabled={!!busy} onClick={() => {setSeed(""); setNewShiftOpen(true);}}>New Shift</button></div>
    </header>
    {newShiftOpen && <Modal title="Open a new shift" onClose={() => setNewShiftOpen(false)}>
      <p>The current shift will be left paused. The new shift starts with its own handover, material condition and customer commitments.</p>
      <form onSubmit={async event => {event.preventDefault(); const next = seed.trim() === "" ? (session?.summary.seed ?? 41) + 1 : Number(seed); if (await control.newShift(next)) setNewShiftOpen(false);}}>
        <details><summary>Advanced / deterministic replay</summary><label className="field">Replay seed<input aria-label="Replay seed" type="number" min="0" max={Number.MAX_SAFE_INTEGER} step="1" value={seed} onChange={e => setSeed(e.target.value)} placeholder={`Next seed: ${(session?.summary.seed ?? 41) + 1}`} /></label><p className="muted">Same seed and decisions at the same simulated times reproduce the shift.</p></details>
        {control.error && <p role="alert" className="error-text">{control.error}</p>}
        <button className="primary" disabled={!!busy} type="submit">{busy ? "Opening…" : "Create shift"}</button>
      </form>
    </Modal>}
  </>;
}
