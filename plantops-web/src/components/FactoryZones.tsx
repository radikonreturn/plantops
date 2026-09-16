import type { ScenarioProfile, SceneZone } from "../types";

export function Pallets({zone, x, y, columns = 4, limit = 16, showOverflow = true}: {zone: SceneZone; x: number; y: number; columns?: number; limit?: number; showOverflow?: boolean}) {
  return <g className={`pallets ${zone.congested ? "congested" : ""}`} aria-label={`${zone.pallets} pallets, ${zone.units} units`}>
    {Array.from({length: Math.min(zone.pallets, limit)}, (_, i) => <g key={i} transform={`translate(${x + i % columns * 25},${y + Math.floor(i / columns) * 21})`}><rect width="19" height="15"/><path d="M3 2v11M9 2v11M15 2v11" /></g>)}
    {showOverflow && zone.pallets > limit && <text x={x} y={y + Math.ceil(limit / columns) * 21 + 10}>+{zone.pallets - limit} pallets</text>}
  </g>;
}

export function FactoryZones({scene}: {scene: ScenarioProfile["scene"]}) {
  const raw = scene.zones.find(z => z.id === "raw")!;
  const finished = scene.zones.find(z => z.id === "finished")!;
  return <>
    <g className={`factory-zone ${scene.highlighted_zone === "raw" ? "zone-attention" : ""}`}>
      <rect x="20" y="65" width="180" height="240"/><text className="zone-name" x="32" y="88">RAW MATERIAL</text><text className="zone-detail" x="32" y="106">Steel blanks · bracket family</text>
      <path className="rack" d="M32 121h153M32 177h153M32 233h153M32 119v145M185 119v145"/>
      <Pallets zone={raw} x={39} y={130} columns={6} limit={30}/><text className="stock-count" x="32" y="285">{raw.units} units on hand</text>
    </g>
    <g className={`factory-zone ${scene.receiving.uncovered_demand > 0 ? "zone-attention" : ""}`}>
      <rect x="20" y="400" width="180" height="210"/><text className="zone-name" x="32" y="424">RECEIVING</text>
      <text className="zone-detail" x="32" y="449">{scene.receiving.inbound_units} units inbound</text>
      <text className="zone-detail" x="32" y="468">{scene.receiving.open_purchase_orders} open purchase orders</text>
      <text className="stock-count" x="32" y="493">{scene.receiving.uncovered_demand} uncovered units</text>
      <path className="loading-bay" d="M32 519h153v73H32zM70 519v73M108 519v73M146 519v73"/>
      {scene.receiving.open_purchase_orders > 0 && <g className="material-token" transform="translate(44,538)"><rect width="43" height="23"/><path d="M43 3h14v20H43M4 26h10m32 0h10"/><title>Inbound purchase orders</title></g>}
    </g>
    <g className={`factory-zone ${scene.highlighted_zone === "finished" ? "zone-attention" : ""}`}>
      <rect x="1210" y="400" width="180" height="210"/><text className="zone-name" x="1222" y="424">FINISHED GOODS</text>
      <Pallets zone={finished} x={1225} y={451} columns={6} limit={24}/><text className="stock-count" x="1222" y="589">{finished.units} available units</text>
    </g>
    <g className={`factory-zone ${scene.dispatch.at_risk_orders ? "zone-attention" : ""}`}>
      <rect x="1210" y="65" width="180" height="240"/><text className="zone-name" x="1222" y="88">DISPATCH</text>
      <text className="zone-detail" x="1222" y="114">{scene.dispatch.allocated_units} units allocated</text>
      <text className="stock-count" x="1222" y="139">{scene.dispatch.at_risk_orders} orders at risk / late</text>
      <path className="loading-bay" d="M1222 163h153v114h-153zM1273 163v114M1324 163v114"/>
      <text className="zone-detail" x="1229" y="298">CUSTOMER COLLECTION</text>
    </g>
  </>;
}
