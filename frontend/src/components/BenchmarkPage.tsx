import { useState, useRef, useCallback } from "react";
import type { BenchmarkRun, BenchmarkResult } from "../types";
import { generateMatrix, startMultiply } from "../api/client";
import { waitForJobCompletion } from "../utils/waitForJobCompletion";
import { BenchmarkChart } from "./BenchmarkChart";

const MATRIX_SIZES = [1024, 2048];
const TILE_SIZES = [128, 256, 512, 1024, 2048];
const RUNS_PER_CONFIG = 1;

type BenchmarkStatus = "idle" | "running" | "completed" | "cancelled" | "error";

function buildRuns(): BenchmarkRun[] {
  const runs: BenchmarkRun[] = [];
  for (const matrixSize of MATRIX_SIZES) {
    for (const tileSize of TILE_SIZES) {
      for (let runIndex = 0; runIndex < RUNS_PER_CONFIG; runIndex++) {
        runs.push({
          config: { matrixSize, tileSize },
          runIndex,
          elapsed: null,
          status: "pending",
        });
      }
    }
  }
  return runs;
}

function computeAverages(runs: BenchmarkRun[]): BenchmarkResult[] {
  const grouped = new Map<string, BenchmarkRun[]>();
  for (const run of runs) {
    const key = `${run.config.matrixSize}-${run.config.tileSize}`;
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key)!.push(run);
  }

  const results: BenchmarkResult[] = [];
  for (const [, group] of grouped) {
    const completed = group.filter((r) => r.elapsed !== null);
    if (completed.length === 0) continue;
    const times = completed.map((r) => r.elapsed!);
    const avg = times.reduce((a, b) => a + b, 0) / times.length;
    results.push({
      config: group[0].config,
      avgElapsed: avg,
      runs: times,
    });
  }
  return results;
}

export function BenchmarkPage() {
  const [status, setStatus] = useState<BenchmarkStatus>("idle");
  const [runs, setRuns] = useState<BenchmarkRun[]>([]);
  const [currentRunIndex, setCurrentRunIndex] = useState(0);
  const [results, setResults] = useState<BenchmarkResult[]>([]);
  const [error, setError] = useState<string | null>(null);
  const cancelledRef = useRef(false);

  const runBenchmark = useCallback(async () => {
    cancelledRef.current = false;
    const allRuns = buildRuns();
    setRuns(allRuns);
    setCurrentRunIndex(0);
    setResults([]);
    setError(null);
    setStatus("running");

    let lastMatrixKey = "";
    let matAId = "";
    let matBId = "";

    for (let i = 0; i < allRuns.length; i++) {
      if (cancelledRef.current) {
        setStatus("cancelled");
        return;
      }

      const run = allRuns[i];
      const { matrixSize, tileSize } = run.config;

      // Mark current run
      setCurrentRunIndex(i);
      allRuns[i] = { ...allRuns[i], status: "running" };
      setRuns([...allRuns]);

      try {
        // Generate matrices once per matrix size (reuse across tile sizes and runs)
        const configKey = `${matrixSize}`;
        if (configKey !== lastMatrixKey) {
          const matA = await generateMatrix(matrixSize, matrixSize);
          const matB = await generateMatrix(matrixSize, matrixSize);
          matAId = matA.id;
          matBId = matB.id;
          lastMatrixKey = configKey;
        }

        // Start multiply
        const { job_id } = await startMultiply(matAId, matBId, tileSize);

        // Wait for completion
        const result = await waitForJobCompletion(
          job_id,
          () => cancelledRef.current
        );

        allRuns[i] = {
          ...allRuns[i],
          elapsed: result.elapsed,
          status: "completed",
        };
        setRuns([...allRuns]);
      } catch (err) {
        if (cancelledRef.current) {
          setStatus("cancelled");
          return;
        }
        allRuns[i] = { ...allRuns[i], status: "failed" };
        setRuns([...allRuns]);
        setError(err instanceof Error ? err.message : String(err));
        setStatus("error");
        return;
      }
    }

    // All done
    const averages = computeAverages(allRuns);
    setResults(averages);
    setStatus("completed");
  }, []);

  const handleCancel = useCallback(() => {
    cancelledRef.current = true;
  }, []);

  const totalRuns = runs.length;
  const completedRuns = runs.filter((r) => r.status === "completed").length;

  return (
    <div className="bench-page">
      <p className="bench-description">
        Runs matrix multiplication across all combinations of matrix sizes
        (1024, 2048) and tile sizes (128, 256, 512, 1024, 2048), running each
        configuration once.
      </p>

      <div className="bench-controls">
        <button
          type="button"
          className="btn-bench"
          disabled={status === "running"}
          onClick={runBenchmark}
        >
          {status === "idle" ? "Run Benchmark" : "Re-run Benchmark"}
        </button>
        {status === "running" && (
          <button
            type="button"
            className="btn-bench btn-bench--cancel"
            onClick={handleCancel}
          >
            Cancel
          </button>
        )}
      </div>

      {status === "running" && totalRuns > 0 && (
        <div className="bench-status">
          <h3>Running Benchmark</h3>
          <p className="bench-current">
            Job {currentRunIndex + 1} / {totalRuns} &mdash;{" "}
            <strong>
              {runs[currentRunIndex]?.config.matrixSize}&times;
              {runs[currentRunIndex]?.config.matrixSize}
            </strong>{" "}
            with tile size{" "}
            <strong>{runs[currentRunIndex]?.config.tileSize}</strong> (run{" "}
            {runs[currentRunIndex]?.runIndex + 1}/{RUNS_PER_CONFIG})
          </p>
          <div className="bench-progress-bar">
            <div
              className="bench-progress-fill"
              style={{ width: `${(completedRuns / totalRuns) * 100}%` }}
            />
          </div>
          <p className="bench-progress-text">
            {completedRuns} / {totalRuns} completed (
            {((completedRuns / totalRuns) * 100).toFixed(0)}%)
          </p>
        </div>
      )}

      {error && <p className="error global-error">{error}</p>}

      {status === "cancelled" && (
        <p className="bench-cancelled">Benchmark cancelled.</p>
      )}

      {(status === "running" || status === "completed" || status === "error") &&
        runs.length > 0 && (
          <div className="bench-log">
            {runs.map((run) => (
              <div
                key={`${run.config.matrixSize}-${run.config.tileSize}-${run.runIndex}`}
                className={`bench-log-item bench-log-item--${run.status}`}
              >
                {run.config.matrixSize}&times;{run.config.matrixSize} / tile{" "}
                {run.config.tileSize} / run {run.runIndex + 1}
                {run.elapsed !== null && ` — ${run.elapsed.toFixed(2)}s`}
                {run.status === "running" && " ..."}
              </div>
            ))}
          </div>
        )}

      <BenchmarkChart results={results} />
    </div>
  );
}
