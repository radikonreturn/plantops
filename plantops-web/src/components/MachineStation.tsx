import type { MachineMetric, MachineState } from "../types";

interface MachineStationProps {
  machineId: string;
  displayName: string;
  metric: MachineMetric;
  selected: boolean;
  onSelect: (machineId: string) => void;
}

const stateLabels: Record<MachineState, string> = {
  IDLE: "Idle / ready",
  RUNNING: "Running",
  STARVED: "Starved",
  BLOCKED: "Blocked",
  DOWN: "Down / fault",
  PLANNED_MAINTENANCE: "Planned maintenance",
};

export function MachineStation({
  machineId,
  displayName,
  metric,
  selected,
  onSelect,
}: MachineStationProps) {
  return (
    <button
      type="button"
      className={`machine-station state-${metric.state.toLowerCase()} ${selected ? "is-selected" : ""}`}
      onClick={() => onSelect(machineId)}
      aria-pressed={selected}
      aria-label={`${displayName}, ${stateLabels[metric.state]}`}
    >
      <div className="machine-station__topline">
        <span className="asset-tag">{displayName}</span>
        <span className="machine-state">
          <i aria-hidden="true" />
          {stateLabels[metric.state]}
        </span>
      </div>

      <svg
        className="machine-symbol"
        viewBox="0 0 160 92"
        role="img"
        aria-label={`${displayName} top-down equipment footprint`}
      >
        <rect className="machine-symbol__base" x="12" y="12" width="136" height="68" rx="2" />
        <path className="machine-symbol__housing" d="M22 22h74v48H22z" />
        <circle className="machine-symbol__spindle" cx="59" cy="46" r="14" />
        <path className="machine-symbol__guard" d="M104 22h33v19h-33zM104 47h33v23h-33z" />
        <path className="machine-symbol__route" d="M0 46h22M96 46h8M137 46h23" />
      </svg>

      <div className="machine-station__metrics">
        <span>Processed<strong>{metric.processed}</strong></span>
        <span>Health<strong>{metric.health.toFixed(1)}</strong></span>
        <span>Availability<strong>{(metric.availability * 100).toFixed(1)}%</strong></span>
        <span>Failures<strong>{metric.failures}</strong></span>
        <span className="metric-wide">Planned maintenance<strong>{metric.planned_maintenance_minutes.toFixed(1)} min</strong></span>
      </div>
    </button>
  );
}
