import type { BenchmarkResult } from "../types";

interface Props {
  results: BenchmarkResult[];
}

export function BenchmarkChart({ results }: Props) {
  if (results.length === 0) return null;

  const maxElapsed = Math.max(...results.map((r) => r.avgElapsed));
  const grouped: Record<number, BenchmarkResult[]> = {};
  for (const r of results) {
    const key = r.config.matrixSize;
    if (!grouped[key]) grouped[key] = [];
    grouped[key].push(r);
  }

  return (
    <div className="bench-chart">
      <h3>Benchmark Results</h3>
      {[1024, 2048].map((size) => {
        const group = grouped[size];
        if (!group) return null;
        const sorted = [...group].sort(
          (a, b) => a.config.tileSize - b.config.tileSize
        );
        return (
          <div key={size} className="bench-chart-group">
            <h4 className="bench-chart-group-label">
              {size} &times; {size}
            </h4>
            {sorted.map((r) => {
              const pct = (r.avgElapsed / maxElapsed) * 100;
              return (
                <div key={r.config.tileSize} className="bench-bar-row">
                  <span className="bench-bar-label">
                    Tile {r.config.tileSize}
                  </span>
                  <div className="bench-bar-track">
                    <div
                      className={`bench-bar-fill bench-bar-fill--${size}`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <span className="bench-bar-value">
                    {r.avgElapsed.toFixed(2)}s
                  </span>
                </div>
              );
            })}
            <div className="bench-runs-detail">
              {sorted.map((r) => (
                <div key={r.config.tileSize} className="bench-run-times">
                  <span>Tile {r.config.tileSize}:</span>{" "}
                  {r.runs.map((t, idx) => (
                    <span
                      key={`${r.config.tileSize}-${idx}`}
                      className="bench-run-time"
                    >
                      {t.toFixed(2)}s
                    </span>
                  ))}
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
