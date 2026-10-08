import { useState } from "react";
import type { MatrixInfo } from "../types";
import { generateMatrix, uploadMatrix } from "../api/client";

interface Props {
  label: string;
  onMatrix: (info: MatrixInfo) => void;
}

export function MatrixInput({ label, onMatrix }: Props) {
  const [mode, setMode] = useState<"generate" | "upload">("generate");
  const [rows, setRows] = useState(512);
  const [cols, setCols] = useState(512);
  const [seed, setSeed] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<MatrixInfo | null>(null);

  const handleGenerate = async () => {
    if (rows < 1 || cols < 1) {
      setError("Rows and Cols must be at least 1");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const parsedSeed = parseInt(seed, 10);
      const result = await generateMatrix(
        rows,
        cols,
        seed && !isNaN(parsedSeed) ? parsedSeed : undefined
      );
      setInfo(result);
      onMatrix(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to generate");
    } finally {
      setLoading(false);
    }
  };

  const handleUpload = async (file: File) => {
    setLoading(true);
    setError(null);
    try {
      const result = await uploadMatrix(file);
      setInfo(result);
      onMatrix(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to upload");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={`matrix-input${loading ? " matrix-input--loading" : ""}`}>
      <h3>{label}</h3>
      <div className="mode-toggle">
        <button
          type="button"
          className={mode === "generate" ? "active" : ""}
          onClick={() => setMode("generate")}
        >
          Generate
        </button>
        <button
          type="button"
          className={mode === "upload" ? "active" : ""}
          onClick={() => setMode("upload")}
        >
          Upload CSV
        </button>
      </div>

      {mode === "generate" ? (
        <div className="generate-form">
          <label>
            Rows:
            <input
              type="number"
              value={rows}
              onChange={(e) => setRows(parseInt(e.target.value, 10) || 0)}
              min={1}
              max={16384}
            />
          </label>
          <label>
            Cols:
            <input
              type="number"
              value={cols}
              onChange={(e) => setCols(parseInt(e.target.value, 10) || 0)}
              min={1}
              max={16384}
            />
          </label>
          <label>
            Seed (optional):
            <input
              type="text"
              value={seed}
              onChange={(e) => setSeed(e.target.value)}
              placeholder="Random"
            />
          </label>
          <button type="button" onClick={handleGenerate} disabled={loading}>
            {loading ? "Generating..." : "Generate"}
          </button>
        </div>
      ) : (
        <div className="upload-form">
          <input
            type="file"
            accept=".csv"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) handleUpload(file);
            }}
            disabled={loading}
          />
        </div>
      )}

      {error && <p className="error">{error}</p>}
      {info && (
        <p className="info">
          Matrix {info.id.slice(0, 8)}... ({info.rows} x {info.cols})
        </p>
      )}
    </div>
  );
}
