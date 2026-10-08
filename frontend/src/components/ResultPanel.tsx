import { useState, useEffect } from "react";
import type { MatrixInfo, VerificationResult } from "../types";
import { toleranceForSize, verifyJob } from "../api/client";

interface Props {
  jobId: string | null;
  finished: boolean;
  matrixA: MatrixInfo | null;
  matrixB: MatrixInfo | null;
}

export function ResultPanel({ jobId, finished, matrixA, matrixB }: Props) {
  const [result, setResult] = useState<VerificationResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset stale verification data when a new job starts
  useEffect(() => {
    setResult(null);
    setError(null);
  }, [jobId]);

  if (!jobId || !finished) return null;

  const maxDim = Math.max(
    matrixA?.rows ?? 0,
    matrixA?.cols ?? 0,
    matrixB?.rows ?? 0,
    matrixB?.cols ?? 0,
  );
  const tolerance = toleranceForSize(maxDim);

  const handleVerify = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await verifyJob(jobId, tolerance);
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Verification failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="result-panel">
      <h3>Results</h3>
      {!result ? (
        loading ? (
          <div className="skeleton-bar" />
        ) : (
          <button type="button" onClick={handleVerify}>Verify Against NumPy</button>
        )
      ) : (
        <div className={`verification ${result.passed ? "passed" : "failed"}`}>
          <p className="verdict">
            {result.passed ? "PASSED" : "FAILED"}
          </p>
          <table aria-label="Verification results">
            <tbody>
              <tr>
                <td>Max Absolute Error:</td>
                <td>{result.max_abs_error.toExponential(4)}</td>
              </tr>
              <tr>
                <td>Mean Absolute Error:</td>
                <td>{result.mean_abs_error.toExponential(4)}</td>
              </tr>
              <tr>
                <td>Tolerance:</td>
                <td>{result.tolerance}</td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
      {error && <p className="error">{error}</p>}
    </div>
  );
}
