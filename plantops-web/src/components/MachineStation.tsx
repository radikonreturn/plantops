import type { AssetConfig, MachineMetric } from "../types";
import { label, percent } from "../format";

function Equipment({role}: {role: AssetConfig["stage_role"]}) {
  switch (role) {
    case "laser": return <>
      <rect className="machine-body" y="8" width="148" height="78"/>
      <rect className="machine-bed" x="9" y="17" width="126" height="58"/>
      <path className="equipment-line" d="M17 21v50m12-50v50m12-50v50m12-50v50m12-50v50m12-50v50m12-50v50m12-50v50m12-50v50m12-50v50"/>
      <rect className="control-box" x="54" width="13" height="94"/><circle className="spindle-inner" cx="60" cy="43" r="6"/>
      <path className="equipment-line" d="M74 30h42v26H89V43H74z"/>
    </>;
    case "cnc": return <>
      <path className="machine-body" d="M0 0h112v10h36v84H0z"/>
      <rect className="machine-bed" x="10" y="12" width="85" height="68"/><path className="equipment-line" d="M22 18v56M83 18v56M22 46h61"/>
      <circle className="spindle" cx="52" cy="46" r="19"/><circle className="spindle-inner" cx="52" cy="46" r="7"/>
      <rect className="control-box" x="106" y="22" width="31" height="30"/><path className="equipment-line" d="M111 31h20m-20 8h12M110 68h22"/>
    </>;
    case "wash": return <>
      <rect className="machine-body" y="8" width="118" height="78" rx="18"/>
      <rect className="wash-tank" x="9" y="17" width="100" height="60" rx="13"/>
      <path className="equipment-line" d="M30 17v60M55 17v60M80 17v60M15 34h88M15 59h88M118 27h20v44h-20"/>
      <circle className="wash-tank" cx="137" cy="48" r="11"/>
    </>;
    case "assembly": return <>
      <path className="machine-body" d="M0 0h148v25H95v43h53v26H0V68h53V25H0z"/>
      <rect className="machine-bed" x="55" y="27" width="38" height="38"/>
      <path className="equipment-line" d="M7 12h36m61 0h36M7 81h36m61 0h36M65 34l18 24m-18 0l18-24"/>
      <circle className="control-box" cx="25" cy="47" r="10"/><circle className="control-box" cx="124" cy="47" r="10"/>
    </>;
    case "test": return <>
      <rect className="inspection-bed" x="8" y="8" width="103" height="78"/>
      <path className="machine-body" d="M0 0h16v80H0zM102 0h16v80h-16zM16 10h86v13H16z"/>
      <path className="equipment-line" d="M60 23v29l12 8M28 64h56M40 38h37v28H40z"/>
      <rect className="control-box" x="125" y="48" width="23" height="36"/>
    </>;
    case "quality": return <>
      <path className="machine-body" d="M0 10h95v73H0zM105 10h43v35h-43zM105 57h43v26h-43z"/>
      <rect className="inspection-bed" x="9" y="20" width="76" height="52"/>
      <circle className="spindle-inner" cx="42" cy="43" r="15"/><path className="equipment-line" d="M53 54l20 15M111 27l8 8 19-18M112 65l24 11m-24 0l24-11"/>
    </>;
  }
}

export function MachineStation({asset, metric, x, y, selected, highlighted, bottleneck, onSelect}: {
  asset: AssetConfig; metric: MachineMetric; x: number; y: number; selected: boolean;
  highlighted: boolean; bottleneck: boolean; onSelect: () => void;
}) {
  return <g transform={`translate(${x},${y})`} className={`machine-node state-${metric.state.toLowerCase()} ${selected ? "selected" : ""} ${highlighted ? "highlighted" : ""}`}
    role="button" tabIndex={0} aria-label={`Inspect ${asset.name}, ${label(metric.state)}${asset.attention_reason ? `, ${asset.attention_reason}` : ""}`} onClick={onSelect}
    onKeyDown={e => {if (e.key === "Enter" || e.key === " ") {e.preventDefault(); onSelect();}}}>
    <title>{asset.fault_mode}{asset.attention_reason ? ` — ${asset.attention_reason}` : ""}</title>
    <rect className="machine-hit" x="-8" y="-38" width="166" height="217" rx="2" />
    <text className="machine-name" y="-18">{asset.name}</text><circle className="machine-lamp" cx="144" cy="-27" r="5" />
    <Equipment role={asset.stage_role}/>
    <text className="machine-state-label" y="114">{metric.state === "PLANNED_MAINTENANCE" ? "Planned stop" : label(metric.state)}</text>
    <text className="machine-readout" y="132">{metric.processed} processed · {metric.health.toFixed(0)} health</text>
    <text className="machine-readout" y="148">{asset.ideal_cycle_minutes} min/unit · {percent(asset.failure_risk)} risk</text>
    <text className={`machine-readout ${bottleneck ? "capacity-limit" : ""}`} y="164">{bottleneck ? "CAPACITY LIMIT" : asset.fault_mode.split(" / ")[0]}</text>
  </g>;
}
