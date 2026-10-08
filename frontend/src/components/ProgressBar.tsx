interface Props {
  completed: number;
  total: number;
  elapsed: number;
  tileTimes: number[];
}

export function ProgressBar({ completed, total, elapsed, tileTimes }: Props) {
  if (total === 0) return null;

  const pct = ((completed / total) * 100).toFixed(1);

  // ETA based on rolling average of last 10 tile times
  let eta = "—";
  if (tileTimes.length > 0) {
    const recent = tileTimes.slice(-10);
    const avgTime = recent.reduce((a, b) => a + b, 0) / recent.length;
    const remaining = total - completed;
    const etaSeconds = Math.round(avgTime * remaining);
    const mins = Math.floor(etaSeconds / 60);
    const secs = etaSeconds % 60;
    eta = `${mins}m ${secs}s`;
  }

  return (
    <div className="progress-bar">
      <div className="progress-track">
        <div
          className="progress-fill"
          style={{ width: `${(completed / total) * 100}%` }}
        />
      </div>
      <div className="progress-stats">
        <span>
          {completed}/{total} tiles ({pct}%)
        </span>
        <span>Elapsed: {Math.round(elapsed)}s</span>
        <span>ETA: {eta}</span>
      </div>
    </div>
  );
}
