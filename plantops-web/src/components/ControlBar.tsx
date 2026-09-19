import { AudioControls } from "../audio/AudioControls";
import type { PlantAudio } from "../audio/usePlantAudio";
import { useState } from "react";
import { LanguageSelector, useI18n } from "../i18n";
import type { PlantSession } from "../hooks/usePlantSession";
import type { Difficulty, Workspace } from "../types";
import { clock } from "../format";
import { readStored } from "../tutorial/state";
import { Modal } from "./Modal";
export function ControlBar({control, onExit, audio, navigate}: {navigate?: (view: Workspace) => void; audio?: PlantAudio; control: PlantSession; onExit?: () => Promise<boolean>}) {
  const { t, percent } = useI18n();
  const {session, busy} = control;
  const [newShiftOpen, setNewShiftOpen] = useState(false);
  const [exitOpen, setExitOpen] = useState(false);
  const [seed, setSeed] = useState("");
  const [difficulty, setDifficulty] = useState<Difficulty>(session?.difficulty ?? "normal");
  const s = session?.summary;
  const ended = !!s && s.simulated_minutes >= s.shift_minutes;
  const paused = !session || session.paused || control.connectionHold;
  const opName = readStored("localStorage", "plantops.operatorName");
  return <>
    <header className="app-header">
      <div className="brand"><svg viewBox="0 0 30 30" aria-hidden="true"><path d="M3 26V12l8-5v7l8-5v7h8v10ZM5 5h4v5M8 20h3m5 0h3m4 0h2" /></svg><strong>PlantOps</strong></div>
      <div className="plant-identity"><strong>Artemis Manufacturing</strong><span>{opName ? t("Op: {value1} · Plant 01", {value1: opName}) : t("Plant 01 · Component line A")}</span></div>
      <div className="header-clock"><strong>{clock(s?.simulated_minutes ?? 0)}</strong><span>/ {clock(s?.shift_minutes ?? 480)}</span><progress aria-label={t("Shift progress")} max={s?.shift_minutes ?? 480} value={s?.simulated_minutes ?? 0} /></div>
      <div className="header-kpis"><span>{t("Production") + " "}<b>{s?.good_production ?? 0}</b></span><span>OEE <b>{percent(s?.oee ?? null)}</b></span><span>OTIF <b>{percent(s?.order_summary.otif ?? null)}</b></span><span>{t("WIP / backlog") + " "}<b>{s?.wip ?? 0} / {s?.order_summary.backlog_units ?? 0}</b></span></div>
      <div className="shift-buttons"><LanguageSelector />{session?.shift_events?.some(e => e.state === "active" && (e.choices?.length || e.kind === "management_objective")) && <button onClick={() => navigate?.("Office / Inbox")}>{t("Active decisions: {count}", { count: session.shift_events.filter(e => e.state === "active" && (e.choices?.length || e.kind === "management_objective")).length })}</button>}{audio && <AudioControls audio={audio} />}<button className="primary" disabled={!!busy || !session || (ended && session.paused)} onClick={() => void control.toggle()}>{ended ? t("Shift complete") : control.connectionHold ? t("Reconnect") : paused ? t("Start shift") : t("Pause")}</button><div className="speed-group" aria-label={t("Playback speed")}>{([1, 2, 4] as const).map(speed => <button key={speed} aria-pressed={session?.speed === speed} disabled={!!busy || !session} onClick={() => void control.speed(speed)}>{speed}×</button>)}</div><button disabled={!!busy} onClick={() => {setSeed(""); setDifficulty(session?.difficulty ?? "normal"); setNewShiftOpen(true);}}>{t("New Shift")}</button><button disabled={!!busy} onClick={() => setExitOpen(true)}>{t("Main menu")}</button></div>
    </header>
    {newShiftOpen && <Modal title={t("Open a new shift")} onClose={() => setNewShiftOpen(false)}>
      <p>{t("The current shift will be left paused. The new shift starts with its own handover, material condition and customer commitments.")}</p>
      <form onSubmit={async event => {event.preventDefault(); const next = seed.trim() === "" ? (session?.summary.seed ?? 41) + 1 : Number(seed); if (await control.newShift(next, "seeded", difficulty)) setNewShiftOpen(false);}}>
        <label className="field">{t("Difficulty")}<select value={difficulty} onChange={event => setDifficulty(event.target.value as Difficulty)}><option value="easy">{t("Easy")}</option><option value="normal">{t("Normal")}</option><option value="hard">{t("Hard")}</option></select></label>
        <details><summary>{t("Advanced / deterministic replay")}</summary><label className="field">{t("Replay seed")}<input aria-label={t("Replay seed")} type="number" min="0" max={Number.MAX_SAFE_INTEGER} step="1" value={seed} onChange={e => setSeed(e.target.value)} placeholder={t("Next seed: {value1}", {value1: (session?.summary.seed ?? 41) + 1})} /></label><p className="muted">{t("Same seed and decisions at the same simulated times reproduce the shift.")}</p></details>
        {control.error && <p role="alert" className="error-text">{control.error}</p>}
        <button className="primary" disabled={!!busy} type="submit">{busy ? t("Opening…") : t("Create shift")}</button>
      </form>
    </Modal>}
    {exitOpen && <Modal title={t("Return to main menu?")} onClose={() => setExitOpen(false)}>
      <p>{t("Your current shift will be paused and kept for Resume Shift.")}</p>
      <div className="dialog-actions"><button onClick={() => setExitOpen(false)}>{t("Cancel")}</button><button className="primary" disabled={!!busy} onClick={async () => {if (!onExit || await onExit()) setExitOpen(false);}}>{busy ? t("Saving…") : t("Save and return")}</button></div>
    </Modal>}
  </>;
}
