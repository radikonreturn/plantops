import type { PlaybackSpeed, SessionSnapshot } from "../types";

interface ControlBarProps {
  session: SessionSnapshot | null;
  seedValue: string;
  busy: boolean;
  onSeedChange: (value: string) => void;
  onTogglePlayback: () => void;
  onSpeedChange: (speed: PlaybackSpeed) => void;
  onNewShift: () => void;
}

function formatClock(minutes: number): string {
  const wholeMinutes = Math.max(0, Math.floor(minutes));
  const hours = Math.floor(wholeMinutes / 60);
  const remainder = wholeMinutes % 60;
  return `${String(hours).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
}

function formatPercent(value: number | null): string {
  return value === null ? "—" : `${(value * 100).toFixed(1)}%`;
}

export function ControlBar({
  session,
  seedValue,
  busy,
  onSeedChange,
  onTogglePlayback,
  onSpeedChange,
  onNewShift,
}: ControlBarProps) {
  const summary = session?.summary;
  const elapsed = summary?.simulated_minutes ?? 0;
  const shift = summary?.shift_minutes ?? 480;
  const complete = elapsed >= shift;
  const progress = Math.min(100, shift > 0 ? (elapsed / shift) * 100 : 0);

  const kpis = [
    ["Good production", summary?.good_production ?? 0, "units"],
    ["OEE", formatPercent(summary?.oee ?? 0), "line"],
    ["OTIF", formatPercent(summary?.order_summary.otif ?? null), "due orders"],
    ["Backlog", summary?.order_summary.backlog_units ?? 0, "units"],
    ["Raw material", summary?.supply_summary.raw_material_on_hand ?? 0, "units"],
    ["FG available", summary?.finished_goods_available ?? 0, "units"],
  ] as const;

  return (
    <header className="control-bar">
      <div className="control-bar__identity">
        <div>
          <span className="eyebrow">PlantOps / Live production control</span>
          <h1>Artemis Manufacturing — Plant 01</h1>
        </div>
        <div className={`plant-state ${session?.paused ? "is-paused" : "is-live"}`}>
          <span className="status-lamp" aria-hidden="true" />
          {complete ? "SHIFT COMPLETE" : session?.paused ? "CONTROL HOLD" : "SHIFT RUNNING"}
        </div>
      </div>

      <div className="control-bar__controls">
        <section className="shift-clock" aria-label="Shift clock">
          <span className="control-label">SIMULATED CLOCK</span>
          <strong>{formatClock(elapsed)}</strong>
          <span className="shift-limit">/ {formatClock(shift)}</span>
          <div className="shift-progress" aria-label={`${progress.toFixed(0)} percent of shift complete`}>
            <span style={{ width: `${progress}%` }} />
          </div>
        </section>

        <div className="playback-controls" aria-label="Playback controls">
          <button
            className="primary-control"
            type="button"
            onClick={onTogglePlayback}
            disabled={!session || busy || complete}
          >
            <span aria-hidden="true">{session?.paused ? "▶" : "Ⅱ"}</span>
            {session?.paused ? "Start shift" : "Pause"}
          </button>
          <div className="speed-selector" aria-label="Simulation speed">
            {([1, 2, 4] as PlaybackSpeed[]).map((speed) => (
              <button
                type="button"
                key={speed}
                className={session?.speed === speed ? "is-active" : ""}
                onClick={() => onSpeedChange(speed)}
                disabled={!session || busy}
                aria-pressed={session?.speed === speed}
              >
                {speed}×
              </button>
            ))}
          </div>
        </div>

        <div className="new-shift-controls">
          <label htmlFor="seed-input">REPLAY SEED</label>
          <div>
            <input
              id="seed-input"
              type="number"
              min="0"
              step="1"
              inputMode="numeric"
              value={seedValue}
              onChange={(event) => onSeedChange(event.target.value)}
              disabled={busy}
            />
            <button type="button" onClick={onNewShift} disabled={busy}>
              New shift
            </button>
          </div>
        </div>
      </div>

      <div className="kpi-strip" aria-label="Core production KPIs">
        {kpis.map(([label, value, unit]) => (
          <div className="kpi-readout" key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
            <small>{unit}</small>
          </div>
        ))}
      </div>
    </header>
  );
}
