import type { PhaseTimings, PhaseStats } from "../types";

interface Props {
  timings: PhaseTimings | null;
  finished: boolean;
}

const PHASE_LABELS: { key: keyof PhaseTimings; label: string; color: string }[] = [
  { key: "client_serialization_sec", label: "Client Serialization", color: "#58a6ff" },
  { key: "network_round_trip_sec", label: "Network Round-Trip", color: "#d29922" },
  { key: "board_deserialization_sec", label: "Board Deserialization", color: "#bc8cff" },
  { key: "board_computation_sec", label: "FPGA Computation", color: "#3fb950" },
  { key: "board_serialization_sec", label: "Board Serialization", color: "#f778ba" },
  { key: "client_deserialization_sec", label: "Client Deserialization", color: "#79c0ff" },
  { key: "accumulation_sec", label: "Accumulation", color: "#ffa657" },
];

function formatMs(sec: number): string {
  if (sec < 0.001) return `${(sec * 1_000_000).toFixed(0)} us`;
  if (sec < 1) return `${(sec * 1000).toFixed(2)} ms`;
  return `${sec.toFixed(3)} s`;
}

export function TimingPanel({ timings, finished }: Props) {
  if (!finished || !timings) return null;

  const phases = PHASE_LABELS
    .filter((p) => timings[p.key] != null)
    .map((p) => ({ ...p, stats: timings[p.key] as PhaseStats }));

  if (phases.length === 0) return null;

  const maxMean = Math.max(...phases.map((p) => p.stats.mean));

  const grandMean = phases.reduce((sum, p) => sum + p.stats.mean, 0);

  return (
    <div className="timing-panel">
      <h3>Phase Timing Breakdown</h3>
      <p className="timing-subtitle">Average per tile</p>
      <div className="timing-bars">
        {phases.map((p) => {
          const pct = maxMean > 0 ? (p.stats.mean / maxMean) * 100 : 0;
          const sharePct = grandMean > 0 ? (p.stats.mean / grandMean) * 100 : 0;
          return (
            <div key={p.key} className="timing-row">
              <span className="timing-label">{p.label}</span>
              <div className="timing-bar-track">
                <div
                  className="timing-bar-fill"
                  style={{ width: `${pct}%`, background: p.color }}
                />
              </div>
              <span className="timing-value">{formatMs(p.stats.mean)}</span>
              <span className="timing-share">{sharePct.toFixed(1)}%</span>
            </div>
          );
        })}
      </div>
      <table className="timing-table" aria-label="Detailed phase timings">
        <thead>
          <tr>
            <th>Phase</th>
            <th>Total</th>
            <th>Mean</th>
            <th>Min</th>
            <th>Max</th>
            <th>Count</th>
          </tr>
        </thead>
        <tbody>
          {phases.map((p) => (
            <tr key={p.key}>
              <td style={{ color: p.color }}>{p.label}</td>
              <td>{formatMs(p.stats.total)}</td>
              <td>{formatMs(p.stats.mean)}</td>
              <td>{formatMs(p.stats.min)}</td>
              <td>{formatMs(p.stats.max)}</td>
              <td>{p.stats.count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
