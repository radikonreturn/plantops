import { usePlantAudio } from "./audio/usePlantAudio";
import { useEffect, useState } from "react";
import { useI18n } from "./i18n";
import { usePlantSession } from "./hooks/usePlantSession";
import { workspaces, type Workspace } from "./types";
import { ControlBar } from "./components/ControlBar";
import { LeftRail } from "./components/LeftRail";
import { FactoryFloor } from "./components/FactoryFloor";
import { OrderBoard } from "./components/OrderBoard";
import { AssetPopover } from "./components/AssetPopover";
import { InboxView } from "./views/InboxView";
import { ProductionPlanView } from "./views/ProductionPlanView";
import { MaintenanceView } from "./views/MaintenanceView";
import { QualityView } from "./views/QualityView";
import { InventoryView } from "./views/InventoryView";
import { Coach } from "./tutorial/Coach";
import { emptyProgress, restoreProgress, tutorialStep, writeStored } from "./tutorial/state";
import { ReportsView } from "./views/ReportsView";
import { LoginScreen } from "./components/LoginScreen";

function viewFromHash(): Workspace {
  const hash = window.location.hash.slice(1);
  return workspaces.find(view => encodeURIComponent(view) === hash) ?? "Plant View";
}
export default function App() {
  const { t } = useI18n();
  const control = usePlantSession();
  const {session, busy, error, notice} = control;
  const audio = usePlantAudio(session, control.connectionHold);
  const [view, setView] = useState<Workspace>(viewFromHash);
  const [progress, setProgress] = useState(() => emptyProgress(""));
  const [selected, setSelected] = useState<string | null>(null);
  useEffect(() => {
    const changed = () => {setView(viewFromHash()); setSelected(null);};
    window.addEventListener("hashchange", changed);
    return () => window.removeEventListener("hashchange", changed);
  }, []);
  useEffect(() => {setSelected(null);}, [session?.session_id]);
  useEffect(() => {if (session) setProgress(restoreProgress(session.session_id));}, [session?.session_id]);
  useEffect(() => {
    if (session?.session_id === progress.sessionId) writeStored("sessionStorage", "plantops.tutorial.progress", JSON.stringify(progress));
  }, [progress, session?.session_id]);
  const step = session ? tutorialStep(session, progress) : null;
  useEffect(() => {
    if (step === 2 && view === "Plant View") setProgress(p => ({...p, plantVisited: true}));
  }, [step, view]);
  const navigate = (next: Workspace) => {setView(next); setSelected(null); window.location.hash = encodeURIComponent(next);};
  const inspect = (id: string) => {
    setSelected(id);
    if (step === 3 && id === "laser_01") setProgress(p => ({...p, assetInspected: true}));
  };
  const replay = () => {void control.newShift(0, "tutorial");};
  const dismiss = () => {
    setProgress(p => ({...p, dismissed: true}));
    writeStored("localStorage", "plantops.tutorial.status", step === 7 ? "completed" : "dismissed");
  };
  if (!session) return <LoginScreen control={control} replay={replay} />;
  return <div className="app-shell" data-tutorial-step={step ?? undefined} data-workspace={view}><a className="skip-link" href="#workspace-content">{t("Skip to workspace")}</a>
    <ControlBar audio={audio} control={control} onExit={control.returnToMenu}/><div className="application-body"><LeftRail session={session} view={view} navigate={navigate}/>
    <main id="workspace-content" className="workspace-content">
      <div className={`operation-feedback ${error ? "has-error" : ""}`} role={error ? "alert" : "status"}><span className="signal"/><span>{error ?? busy ?? notice}{error && " " + t("Playback held; use Reconnect before continuing.")}</span></div>
      {session ? <>
        {step && <Coach step={step} control={control} view={view} navigate={navigate} skip={dismiss} replay={replay} runFirst={() => setProgress(p => ({...p, runFirst: true}))} review={() => {setProgress(p => ({...p, reviewed: true})); writeStored("localStorage", "plantops.tutorial.status", "completed");}}/>}
        <div className="shift-context"><strong>{session.scenario_profile.title}</strong><span>{session.summary.simulated_minutes >= session.summary.shift_minutes ? t("Shift closed · outcome recorded") : session.paused ? t("Shift paused · decisions remain available") : t("Live shift")}</span><button onClick={() => navigate("Office / Inbox")}>{t("Read handover")}</button></div>
        {view === "Plant View" && <><FactoryFloor session={session} selected={selected} onSelect={inspect}/><OrderBoard session={session} busy={!!busy} save={control.prioritize}/></>}
        {view === "Office / Inbox" && <InboxView session={session} navigate={navigate} replay={replay} busy={!!busy} onReadHandover={() => setProgress(p => ({...p, handoverRead: true}))} handoverRead={progress.handoverRead}/>}
        {view === "Production Plan" && <ProductionPlanView control={control}/>}
        {view === "Orders" && <div className="office-view"><div className="view-heading"><h1>{t("Orders")}</h1><span>{t("Delivery performance and dispatch decisions")}</span></div><OrderBoard session={session} busy={!!busy} save={control.prioritize}/></div>}
        {view === "Maintenance" && <MaintenanceView control={control}/>}
        {view === "Quality" && <QualityView control={control}/>}
        {view === "Inventory" && <InventoryView control={control}/>}
        {view === "Reports" && <ReportsView session={session}/>}
        {selected && <AssetPopover machineId={selected} control={control} onClose={() => setSelected(null)}/>}
      </> : <section className="startup-state"><h1>{t("Opening the shift")}</h1><p>{error ?? t("Connecting to production control and receiving the manager handover.")}</p>{error && <button disabled={!!busy} onClick={() => void control.newShift(42)}>{t("Retry connection")}</button>}</section>}
    </main></div>
  </div>;
}
