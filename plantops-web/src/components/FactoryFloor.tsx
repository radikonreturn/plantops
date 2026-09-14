import type { BufferLevels, MachineMetric } from "../types";
import { MachineStation } from "./MachineStation";

interface FactoryFloorProps {
  machineMetrics: Record<string, MachineMetric>;
  bufferLevels: BufferLevels;
  finishedGoodsAvailable: number;
  selectedMachineId: string;
  onSelectMachine: (machineId: string) => void;
}

const machines = [
  { id: "cnc_01", name: "CNC-01" },
  { id: "wash_01", name: "Wash-01" },
  { id: "assembly_01", name: "Assembly-01" },
  { id: "quality_01", name: "Quality-01" },
] as const;

const buffers = [
  "after_cnc_01",
  "after_wash_01",
  "after_assembly_01",
  "finished",
] as const;

function Warehouse({
  label,
  value,
  detail,
  kind,
}: {
  label: string;
  value: number;
  detail: string;
  kind: "raw" | "finished";
}) {
  return (
    <section className={`warehouse warehouse--${kind}`} aria-label={label}>
      <div className="warehouse__label">{label}</div>
      <svg viewBox="0 0 152 108" role="img" aria-label={`${label} storage racks`}>
        <rect className="rack-frame" x="10" y="8" width="132" height="92" />
        <path className="rack-lines" d="M10 38h132M10 69h132M45 8v92M78 8v92M111 8v92" />
        {[22, 55, 88, 121].map((x) => (
          <g key={x} className="rack-load">
            <rect x={x - 9} y="16" width="18" height="14" />
            <rect x={x - 9} y="47" width="18" height="14" />
            <rect x={x - 9} y="78" width="18" height="14" />
          </g>
        ))}
      </svg>
      <div className="warehouse__count">
        <strong>{value}</strong>
        <span>{detail}</span>
      </div>
    </section>
  );
}

function FlowConnector({ count, running }: { count: number; running: boolean }) {
  return (
    <div className={`flow-connector ${running ? "is-moving" : ""}`}>
      <div className="buffer-counter" title="Work-in-process buffer">
        <span>WIP</span>
        <strong>{count}</strong>
      </div>
      <svg viewBox="0 0 104 42" aria-hidden="true">
        <path className="conveyor-rail" d="M2 13h84M2 29h84" />
        <path className="conveyor-ties" d="M12 13v16M28 13v16M44 13v16M60 13v16M76 13v16" />
        <path className="flow-arrow" d="M72 4l28 17-28 17z" />
      </svg>
    </div>
  );
}

export function FactoryFloor({
  machineMetrics,
  bufferLevels,
  finishedGoodsAvailable,
  selectedMachineId,
  onSelectMachine,
}: FactoryFloorProps) {
  return (
    <section className="factory-floor panel-frame" aria-labelledby="factory-floor-title">
      <div className="section-heading">
        <div>
          <span className="section-code">AREA A / SINGLE PRODUCT LINE</span>
          <h2 id="factory-floor-title">Factory floor</h2>
        </div>
        <div className="floor-legend" aria-label="Machine state legend">
          <span className="legend-running">Running</span>
          <span className="legend-constrained">Starved / blocked</span>
          <span className="legend-maintenance">Maintenance</span>
          <span className="legend-down">Down</span>
        </div>
      </div>

      <div className="factory-floor__viewport">
        <div className="factory-floor__plan">
          <svg className="floor-markings" viewBox="0 0 1680 430" preserveAspectRatio="none" aria-hidden="true">
            <defs>
              <pattern id="floor-grid" width="32" height="32" patternUnits="userSpaceOnUse">
                <path d="M32 0H0V32" />
              </pattern>
              <pattern id="hazard-stripe" width="20" height="20" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                <rect width="5" height="20" />
              </pattern>
            </defs>
            <rect className="floor-grid" width="1680" height="430" fill="url(#floor-grid)" />
            <rect className="work-cell-boundary" x="205" y="32" width="1265" height="336" />
            <rect className="safety-walkway" x="0" y="378" width="1680" height="20" fill="url(#hazard-stripe)" />
            <path className="forklift-route" d="M18 404h1640" />
          </svg>

          <div className="line-flow-grid">
            <Warehouse
              label="Raw Material Warehouse"
              value={bufferLevels.raw ?? 0}
              detail="steel blanks on hand"
              kind="raw"
            />

            {machines.map((machine, index) => {
              const metric = machineMetrics[machine.id];
              if (!metric) return null;
              const bufferId = buffers[index];
              return (
                <div className="line-flow-segment" key={machine.id}>
                  <FlowConnector
                    count={index === 0 ? 0 : bufferLevels[buffers[index - 1]] ?? 0}
                    running={metric.state === "RUNNING"}
                  />
                  <MachineStation
                    machineId={machine.id}
                    displayName={machine.name}
                    metric={metric}
                    selected={selectedMachineId === machine.id}
                    onSelect={onSelectMachine}
                  />
                  {index === machines.length - 1 ? (
                    <FlowConnector
                      count={bufferLevels[bufferId] ?? 0}
                      running={metric.state === "RUNNING"}
                    />
                  ) : null}
                </div>
              );
            })}

            <Warehouse
              label="Finished Goods Warehouse"
              value={finishedGoodsAvailable}
              detail={`${bufferLevels.finished ?? 0} total produced`}
              kind="finished"
            />
          </div>

          <div className="floor-note floor-note--inbound">INBOUND / RM-01</div>
          <div className="floor-note floor-note--outbound">OUTBOUND / FG-01</div>
        </div>
      </div>
    </section>
  );
}
