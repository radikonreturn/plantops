import type { SceneZone } from "../types";

export function Pallets({zone, x, y, columns = 4, limit = 16}: {zone: SceneZone; x: number; y: number; columns?: number; limit?: number}) {
  return <g className={`pallets ${zone.congested ? "congested" : ""}`} aria-label={`${zone.pallets} pallets, ${zone.units} units`}>
    {Array.from({length: Math.min(zone.pallets, limit)}, (_, i) => <g key={i} transform={`translate(${x + i % columns * 25},${y + Math.floor(i / columns) * 21})`}><rect width="19" height="15"/><path d="M3 2v11M9 2v11M15 2v11" /></g>)}
    {zone.pallets > limit && <text x={x} y={y + Math.ceil(limit / columns) * 21 + 10}>+{zone.pallets - limit} pallets</text>}
  </g>;
}

export function FactoryZones({zones, highlight}: {zones: SceneZone[]; highlight: string | null}) {
  const raw = zones.find(z => z.id === "raw")!;
  const finished = zones.find(z => z.id === "finished")!;
  return <>
    <g className={`factory-zone ${highlight === "raw" || highlight === "receiving" ? "zone-attention" : ""}`}>
      <rect x="20" y="58" width="185" height="260"/><text className="zone-name" x="34" y="81">RAW MATERIAL</text><text className="zone-detail" x="34" y="100">Steel blanks · RM-01</text>
      <path className="rack" d="M34 122h155v3H34zM34 180h155v3H34zM34 238h155v3H34zM34 120v150M189 120v150" />
      <Pallets zone={raw} x={42} y={132} columns={6} limit={30}/>
      <text className="stock-count" x="34" y="298">{raw.units} units on hand</text>
    </g>
    <g className="factory-zone"><rect x="20" y="375" width="185" height="112"/><text className="zone-name" x="34" y="398">RECEIVING</text><text className="zone-detail" x="34" y="420">Supplier deliveries</text><path className="loading-bay" d="M34 435h150v40H34M59 435v40M84 435v40M109 435v40M134 435v40M159 435v40"/></g>
    <g className={`factory-zone ${highlight === "finished" ? "zone-attention" : ""}`}>
      <rect x="926" y="367" width="274" height="120"/><text className="zone-name" x="940" y="390">FINISHED GOODS</text><Pallets zone={finished} x={941} y={408} columns={6} limit={12}/><text className="stock-count" x="940" y="474">{finished.units} available for allocation</text>
    </g>
    <g className={`factory-zone ${highlight === "dispatch" ? "zone-attention" : ""}`}><rect x="669" y="390" width="214" height="97"/><text className="zone-name" x="683" y="414">DISPATCH</text><text className="zone-detail" x="683" y="435">Customer allocation</text><path className="loading-bay" d="M682 447h181v29H682M721 447v29M760 447v29M799 447v29M838 447v29"/></g>
  </>;
}
