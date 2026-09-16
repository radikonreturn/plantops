import { useEffect, useState } from "react";
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
import { ReportsView } from "./views/ReportsView";

function viewFromHash(): Workspace {
  const hash = window.location.hash.slice(1);
  return workspaces.find(view => encodeURIComponent(view) === hash) ?? "Plant View";
}
export default function App() {
  const control = usePlantSession();
  const {session, busy, error, notice} = control;
  const [view, setView] = useState<Workspace>(viewFromHash);
  const [selected, setSelected] = useState<string | null>(null);
  useEffect(() => {
    const changed = () => {setView(viewFromHash()); setSelected(null);};
    window.addEventListener("hashchange", changed);
    return () => window.removeEventListener("hashchange", changed);
  }, []);
  useEffect(() => {setSelected(null);}, [session?.session_id]);
  const navigate = (next: Workspace) => {setView(next); setSelected(null); window.location.hash = encodeURIComponent(next);};
  return <div className="app-shell"><a className="skip-link" href="#workspace-content">Skip to workspace</a>
    <ControlBar control={control}/><div className="application-body"><LeftRail session={session} view={view} navigate={navigate}/>
    <main id="workspace-content" className="workspace-content">
      <div className={`operation-feedback ${error ? "has-error" : ""}`} role={error ? "alert" : "status"}><span className="signal"/><span>{error ?? busy ?? notice}{error && " Playback held; use Reconnect before continuing."}</span></div>
      {session ? <>
        <div className="shift-context"><strong>{session.scenario_profile.title}</strong><span>{session.paused ? "Shift paused · decisions remain available" : "Live shift"}</span><button onClick={() => navigate("Office / Inbox")}>Read handover</button></div>
        {view === "Plant View" && <><FactoryFloor session={session} selected={selected} onSelect={setSelected}/><OrderBoard session={session} busy={!!busy} save={control.prioritize}/></>}
        {view === "Office / Inbox" && <InboxView session={session} navigate={navigate}/>}
        {view === "Production Plan" && <ProductionPlanView control={control}/>}
        {view === "Orders" && <div className="office-view"><div className="view-heading"><h1>Orders</h1><span>Delivery performance and dispatch decisions</span></div><OrderBoard session={session} busy={!!busy} save={control.prioritize}/></div>}
        {view === "Maintenance" && <MaintenanceView control={control}/>}
        {view === "Quality" && <QualityView session={session}/>}
        {view === "Inventory" && <InventoryView control={control}/>}
        {view === "Reports" && <ReportsView session={session}/>}
        {selected && <AssetPopover machineId={selected} control={control} onClose={() => setSelected(null)}/>}
      </> : <section className="startup-state"><h1>Opening the shift</h1><p>{error ?? "Connecting to production control and receiving the manager handover."}</p>{error && <button disabled={!!busy} onClick={() => void control.newShift(42)}>Retry connection</button>}</section>}
    </main></div>
  </div>;
}
