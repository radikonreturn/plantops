import type { SessionSnapshot } from "../types";
import { FactoryZones, Pallets } from "./FactoryZones";
import { MachineStation } from "./MachineStation";
const stationX = [280, 510, 740, 970];

export function FactoryFloor({session, selected, onSelect}: {session: SessionSnapshot; selected: string | null; onSelect: (id: string) => void}) {
  const profile = session.scenario_profile;
  const scene = profile.scene;
  return <section className="floor-panel" aria-label="Live factory floor">
    <div className="section-heading"><h2>Plant View</h2><div className="legend"><span className="running">Running</span><span className="attention">Attention</span><span className="critical">Down</span><span className="maintenance">Maintenance</span></div></div>
    <div className="floor-scroll"><svg className="factory-map" viewBox="0 0 1220 510" role="group" aria-label="Top-down factory floor: receiving, raw warehouse, CNC, wash, assembly, quality, finished goods and dispatch">
      <defs><pattern id="floor-tiles" width="40" height="40" patternUnits="userSpaceOnUse"><path d="M40 0H0V40" fill="none" stroke="#ccc8bd" strokeWidth="0.6" /></pattern><marker id="process-arrow" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0 0l10 5-10 5z" fill="currentColor" /></marker></defs>
      <rect className="floor-surface" width="1220" height="510"/><rect width="1220" height="510" fill="url(#floor-tiles)"/>
      <path className="building-wall" d="M8 30V7h1204v495H8v-12M8 330V65"/>
      <text className="plan-caption" x="24" y="32">ARTEMIS / COMPONENT LINE A</text><text className="plan-caption" x="929" y="32">TOP VIEW · SCHEMATIC</text>
      <path className="safety-lane" d="M214 65v278h989M213 367h691M246 65v260h957"/>
      <text className="lane-label" x="412" y="361">KEEP CLEAR · MATERIAL TRANSFER LANE</text>
      <rect className="work-zone" x="265" y="62" width="873" height="266"/>
      <text className="zone-detail" x="280" y="86">MACHINING</text><text className="zone-detail" x="510" y="86">CLEANING</text><text className="zone-detail" x="740" y="86">ASSEMBLY</text><text className="zone-detail" x="970" y="86">INSPECTION</text>
      <FactoryZones zones={scene.zones} highlight={scene.highlighted_zone}/>
      <path className="material-route" d="M114 375v-45M1173 321v32H1065v14M926 443h-33" markerEnd="url(#process-arrow)"/>
      {profile.machines.map((asset, i) => {
        const x = stationX[i];
        const route = scene.routes.find(r => r.id === asset.id);
        const input = scene.zones.find(z => z.id === asset.input_buffer)!;
        return <g key={asset.id}>
          <path className="conveyor-frame" d={`M${i === 0 ? 205 : stationX[i - 1] + 148} 208H${x}M${i === 0 ? 205 : stationX[i - 1] + 148} 220H${x}`} />
          <path className={`conveyor-flow ${route?.active && !session.paused ? "active" : ""}`} d={`M${i === 0 ? 207 : stationX[i - 1] + 150} 214H${x - 5}`} markerEnd="url(#process-arrow)"/>
          {i > 0 && <g className={`buffer-zone ${input.congested ? "zone-attention" : ""}`}><rect x={x - 68} y="96" width="60" height="88"/><Pallets zone={input} x={x - 63} y={104} columns={2} limit={4}/><text className="buffer-label" x={x - 62} y="174">{input.units}/{input.capacity}</text></g>}
          <MachineStation asset={asset} metric={session.summary.machine_metrics[asset.id]} x={x} selected={selected === asset.id} onSelect={() => onSelect(asset.id)}/>
          {profile.active_alerts.some(a => a.zone === asset.id) && <g className="map-alert" transform={`translate(${x + 160},280)`}><circle r="9"/><text y="4" textAnchor="middle">!</text><title>{profile.active_alerts.filter(a => a.zone === asset.id).map(a => a.message).join(" ")}</title></g>}
        </g>;
      })}
      <path className="conveyor-frame" d="M1118 208h55v115M1118 220h43v103"/>
      <g className="floor-annotation"><text x="280" y="410">SHIFT OUTPUT</text><text x="280" y="436">{session.summary.good_production} good · {session.summary.scrap} scrap</text><text x="280" y="460">{session.summary.finished_goods_allocated} allocated to customers</text></g>
    </svg></div>
    <div className="map-footer"><span>{profile.scene.highlighted_zone ? `Attention zone: ${profile.scene.highlighted_zone.replace(/_/g, " ")}` : "No active exceptions"}</span><span>Pallet symbols: up to 20 raw/FG units or 2 WIP units · Select equipment for details</span></div>
  </section>;
}
