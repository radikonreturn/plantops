import type { SessionSnapshot } from "../types";
import { FactoryZones, Pallets } from "./FactoryZones";
import { MachineStation } from "./MachineStation";
import { equipmentBays } from "./plantLayout";

export function FactoryFloor({session, selected, onSelect}: {session: SessionSnapshot; selected: string | null; onSelect: (id: string) => void}) {
  const profile = session.scenario_profile;
  const scene = profile.scene;
  const topAlert = profile.active_alerts[0];
  return <section className="floor-panel" aria-label="Live factory floor">
    <div className="section-heading"><h2>Plant View</h2><div className="legend"><span className="running">Running</span><span className="attention">Queue / risk</span><span className="critical">Down</span><span className="maintenance">Maintenance</span></div></div>
    <div className="floor-scroll" tabIndex={0} aria-label="Factory plan; scroll horizontally to inspect all bays"><svg className="factory-map" viewBox="0 0 1410 660" role="group" aria-label="Top-down bracket factory: receiving, laser, CNC, wash, assembly, test CMM, final quality, finished goods and dispatch">
      <defs><pattern id="floor-tiles" width="40" height="40" patternUnits="userSpaceOnUse"><path d="M40 0H0V40" fill="none" stroke="#ccc8bd" strokeWidth="0.6"/></pattern><marker id="process-arrow" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0 0l10 5-10 5z" fill="context-stroke"/></marker></defs>
      <rect className="floor-surface" width="1410" height="660"/><rect width="1410" height="660" fill="url(#floor-tiles)"/>
      <path className="building-wall" d="M8 30V7h1394v645H8V605M8 395V65"/>
      <text className="plan-caption" x="24" y="32">ARTEMIS / AUTOMOTIVE BRACKET LINE A</text><text className="plan-caption" x="1110" y="32">FIXED PLAN · LIVE CONDITIONS</text>
      <path className="safety-lane" d="M215 65v554h1180M245 65v554M215 315h1180M245 365h1150"/>
      <text className="lane-label" x="590" y="359">KEEP CLEAR · MATERIAL TRANSFER LANE</text>
      <rect className="work-zone" x="265" y="62" width="730" height="242"/><text className="zone-detail" x="280" y="78">CUTTING &amp; MACHINING</text>
      <rect className="work-zone" x="455" y="391" width="735" height="218"/>
      <FactoryZones scene={scene}/>
      {session.shift_events?.filter(e => e.state === "active" && ["receiving", "dispatch"].includes(e.zone)).map(e => <g key={e.id} className={`map-alert ${e.severity}`} transform={e.zone === "receiving" ? "translate(181,419)" : "translate(1370,83)"}><circle r="9"/><text y="4" textAnchor="middle">!</text><title>{e.severity}: {e.title} — {e.detail}</title></g>)}
      <path className="material-route" d="M110 400V310M1178 476h26M1300 400v-88" markerEnd="url(#process-arrow)"/>
      {profile.machines.map(asset => {
        const bay = equipmentBays[asset.stage_role];
        const route = scene.routes.find(r => r.id === asset.id)!;
        const input = scene.zones.find(z => z.id === asset.input_buffer)!;
        const alerts = profile.active_alerts.filter(a => a.zone === asset.id || a.zone === asset.input_buffer);
        // Resolve the actual route for classic sessions too; omit absent equipment bays.
        const upstream = profile.machines.find(m => m.output_buffer === asset.input_buffer);
        const origin = upstream ? equipmentBays[upstream.stage_role] : {x: 52, y: 120};
        const inlet = origin.y === bay.y
          ? `M${origin.x + 148} ${bay.y + 46}H${bay.x - 6}`
          : `M${origin.x + 148} ${origin.y + 46}H1000V336H446V${bay.y + 46}H${bay.x - 6}`;
        return <g key={asset.id}>
          <path className="conveyor-track" d={inlet}/>
          <path className={`conveyor-flow ${route.active ? "active" : ""} ${session.paused ? "paused" : ""} ${route.blocked ? "blocked" : ""} ${route.waiting_units ? "loaded" : ""}`} d={inlet} markerEnd="url(#process-arrow)"><title>{asset.name}: {route.status.toLowerCase()}, {route.waiting_units} waiting{route.blocked ? ", output full" : ""}</title></path>
          {asset.input_buffer !== "raw" && <g className={`buffer-zone ${input.congested ? "zone-attention" : ""}`}>
            <rect x={bay.queueX} y={bay.queueY} width="72" height="86"/>
            <text className="queue-caption" x={bay.queueX + 5} y={bay.queueY + 12}>TO {asset.stage_role.toUpperCase()}</text>
            <Pallets zone={input} x={bay.queueX + 9} y={bay.queueY + 20} columns={2} limit={4} showOverflow={false}/>
            <text className="buffer-label" x={bay.queueX + 6} y={bay.queueY + 80}>{input.units}/{input.capacity}</text>
            <title>{asset.input_buffer}: {input.units} units, {input.pallets} pallets</title>
          </g>}
          <MachineStation queue={session.summary.buffer_levels[asset.input_buffer]} asset={asset} metric={session.summary.machine_metrics[asset.id]} x={bay.x} y={bay.y} selected={selected === asset.id} highlighted={scene.highlighted_zone === asset.id} bottleneck={profile.capacity.bottleneck_machines.includes(asset.id)} onSelect={() => onSelect(asset.id)}/>
          {alerts.length > 0 && <g className={`map-alert ${alerts.some(a => a.severity === "critical") ? "critical" : "attention"}`} transform={`translate(${bay.x + 159},${bay.y + 105})`}><circle r="9"/><text y="4" textAnchor="middle">!</text><title>{alerts.map(a => a.message).join(" ")}</title></g>}
        </g>;
      })}
      <g className="floor-annotation"><text x="275" y="436">SHIFT OUTPUT</text><text x="275" y="460">{session.summary.good_production} good · {session.summary.total_scrap ?? session.summary.scrap} scrap</text><text x="275" y="481">{session.summary.wip} queued WIP</text><text x="275" y="510">{session.summary.finished_goods_allocated} units allocated</text></g>
      <g className="floor-annotation"><text x="1030" y="89">LINE SERVICES</text><path className="rack" d="M1030 114h145m-145 36h145M1030 111v62m145-62v62"/><text x="1030" y="199">Tooling &amp; fixtures</text><text x="1030" y="219">Service access</text></g>
      {scene.zones.some(z => z.congested) && <g className="material-token" transform="translate(295,332)"><rect width="27" height="18"/><path d="M27 2h17m-17 14h17M3-3h8m5 0h8M3 21h8m5 0h8"/><title>Material transfer marker: queued WIP requires handling</title></g>}
      <text className="plan-caption" x="275" y="641">FLOW: CUT → MACHINE → WASH ↶ ASSEMBLE → TEST → INSPECT → DISPATCH</text>
    </svg></div>
    <div className="map-events">{session.shift_events?.filter(e => e.state === "active").map(e => <span key={e.id} className={e.severity}>{e.severity.toUpperCase()} · {e.zone} · {e.title}</span>)}</div>
    <div className="map-concern" role="status">{topAlert ? topAlert.message : "No active exceptions."}</div>
    <div className="map-footer"><span>Attention: {scene.highlighted_zone?.replace(/_/g, " ") ?? "none"}</span><span>Pallet: 20 raw/FG or 2 WIP units · counts include hidden stacks · select equipment</span></div>
  </section>;
}
