import type { AssetConfig, MachineMetric } from "../types";
import { label, percent } from "../format";

export function MachineStation({asset, metric, x, selected, onSelect}: {
  asset: AssetConfig; metric: MachineMetric; x: number; selected: boolean; onSelect: () => void;
}) {
  return <g transform={`translate(${x},165)`} className={`machine-node state-${metric.state.toLowerCase()} ${selected ? "selected" : ""}`}
    role="button" tabIndex={0} aria-label={`Inspect ${asset.name}, ${label(metric.state)}`} onClick={onSelect}
    onKeyDown={e => {if (e.key === "Enter" || e.key === " ") {e.preventDefault(); onSelect();}}}>
    <rect className="machine-hit" x="-8" y="-35" width="168" height="200" rx="2" />
    <text className="machine-name" y="-17">{asset.name}</text>
    <circle className="machine-lamp" cx="140" cy="-22" r="5" />
    <rect className="machine-body" width="148" height="94" rx="2" />
    {asset.id === "cnc_01" ? <>
      <rect className="machine-bed" x="10" y="12" width="85" height="68"/><path className="equipment-line" d="M22 18v56M83 18v56M22 46h61"/>
      <circle className="spindle" cx="52" cy="46" r="19"/><circle className="spindle-inner" cx="52" cy="46" r="7"/>
      <rect className="control-box" x="106" y="12" width="31" height="30"/><path className="equipment-line" d="M111 21h20m-20 8h12M110 58h22m-22 9h22"/>
    </> : asset.id === "wash_01" ? <>
      <rect className="wash-tank" x="12" y="14" width="123" height="64" rx="9"/><path className="equipment-line" d="M35 14v64M58 14v64M81 14v64M104 14v64M18 28h110M18 64h110"/>
    </> : asset.id === "assembly_01" ? <>
      <rect className="machine-bed" x="10" y="15" width="128" height="60"/><path className="equipment-line" d="M16 28h114M16 63h114M42 16v58M106 16v58"/><rect className="control-box" x="59" y="34" width="28" height="23"/>
    </> : <>
      <rect className="inspection-bed" x="12" y="15" width="81" height="63"/><path className="equipment-line" d="M25 47h53M52 23v46"/><circle className="spindle-inner" cx="52" cy="47" r="9"/><rect className="control-box" x="106" y="21" width="28" height="34"/><path className="equipment-line" d="M112 29h16m-16 8h16M108 69h24"/>
    </>}
    <text className="machine-state-label" y="114">{label(metric.state)}</text>
    <text className="machine-readout" y="134">{metric.processed} processed · {metric.health.toFixed(0)} health</text>
    <text className="machine-readout" y="152">Avail {percent(metric.availability)} · {metric.failures} faults</text>
  </g>;
}
