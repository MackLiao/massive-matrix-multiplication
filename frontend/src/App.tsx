import { useState } from "react";
import type { MatrixInfo } from "./types";
import { MatrixInput } from "./components/MatrixInput";
import { ConfigPanel } from "./components/ConfigPanel";
import { JobControls } from "./components/JobControls";
import { TileGrid } from "./components/TileGrid";
import { ProgressBar } from "./components/ProgressBar";
import { ResultPanel } from "./components/ResultPanel";
import { TimingPanel } from "./components/TimingPanel";
import { BenchmarkPage } from "./components/BenchmarkPage";
import { useJob } from "./hooks/useJob";
import { startMultiply, cancelJob } from "./api/client";
import "./App.css";

function App() {
  const [page, setPage] = useState<"main" | "benchmark">("main");
  const [matrixA, setMatrixA] = useState<MatrixInfo | null>(null);
  const [matrixB, setMatrixB] = useState<MatrixInfo | null>(null);
  const [tileSize, setTileSize] = useState(256);
  const [error, setError] = useState<string | null>(null);

  const { state: jobState, startJob, reset } = useJob();

  const isRunning = jobState.jobId !== null && !jobState.finished;
  const canStart = matrixA !== null && matrixB !== null && !isRunning;

  const kTotal =
    matrixA && matrixB ? Math.ceil(matrixA.cols / tileSize) : 0;

  const handleStart = async () => {
    if (!matrixA || !matrixB) return;
    setError(null);

    try {
      const gridI = Math.ceil(matrixA.rows / tileSize);
      const gridJ = Math.ceil(matrixB.cols / tileSize);
      const { job_id } = await startMultiply(
        matrixA.id,
        matrixB.id,
        tileSize
      );
      startJob(job_id, gridI, gridJ, kTotal);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start job");
    }
  };

  const handleCancel = async () => {
    if (!jobState.jobId) return;
    try {
      await cancelJob(jobState.jobId);
    } catch {
      // ignore cancel errors
    }
    reset();
  };

  const handleNewJob = () => {
    reset();
    setMatrixA(null);
    setMatrixB(null);
    setError(null);
  };

  return (
    <div className="app">
      <header>
        <h1>FPGA Matrix Multiplication</h1>
        <p className="subtitle">
          Large matrix multiplication via tiled FPGA dispatch
        </p>
        <nav className="tab-bar" role="tablist" aria-label="Page navigation">
          <button
            role="tab"
            aria-selected={page === "main"}
            aria-controls="panel-main"
            className={`tab ${page === "main" ? "tab--active" : ""}`}
            onClick={() => setPage("main")}
          >
            Multiply
          </button>
          <button
            role="tab"
            aria-selected={page === "benchmark"}
            aria-controls="panel-benchmark"
            className={`tab ${page === "benchmark" ? "tab--active" : ""}`}
            onClick={() => setPage("benchmark")}
          >
            Benchmark
          </button>
        </nav>
      </header>

      <main>
        {page === "main" && (
          <div role="tabpanel" id="panel-main">
            <section className="input-section">
              <MatrixInput label="Matrix A" onMatrix={setMatrixA} />
              <MatrixInput label="Matrix B" onMatrix={setMatrixB} />
              <ConfigPanel tileSize={tileSize} onTileSizeChange={setTileSize} />
            </section>

            {error && <p className="error global-error">{error}</p>}

            <section className="controls-section">
              <JobControls
                canStart={canStart}
                isRunning={isRunning}
                onStart={handleStart}
                onCancel={handleCancel}
              />
              {jobState.finished && (
                <button type="button" className="btn-new" onClick={handleNewJob}>
                  New Job
                </button>
              )}
            </section>

            {jobState.jobId && (
              <section className="progress-section">
                <ProgressBar
                  completed={jobState.completed}
                  total={jobState.total}
                  elapsed={jobState.elapsed}
                  tileTimes={jobState.tileTimes}
                />
                <TileGrid
                  grid={jobState.tileGrid}
                  currentTile={jobState.currentTile}
                  kTotal={kTotal}
                />
              </section>
            )}

            <ResultPanel
              jobId={jobState.jobId}
              finished={jobState.finished}
              matrixA={matrixA}
              matrixB={matrixB}
            />
            <TimingPanel timings={jobState.phaseTimings} finished={jobState.finished} />
          </div>
        )}

        {page === "benchmark" && (
          <div role="tabpanel" id="panel-benchmark">
            <BenchmarkPage />
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
