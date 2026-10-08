import type { MatrixInfo, JobInfo, VerificationResult } from "../types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function generateMatrix(
  rows: number,
  cols: number,
  seed?: number
): Promise<MatrixInfo> {
  return request<MatrixInfo>("/matrix/generate", {
    method: "POST",
    body: JSON.stringify({ rows, cols, seed }),
  });
}

export async function uploadMatrix(file: File): Promise<MatrixInfo> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${BASE_URL}/matrix/upload`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function getMatrixInfo(id: string): Promise<MatrixInfo> {
  return request<MatrixInfo>(`/matrix/${id}/info`);
}

export async function startMultiply(
  matrixAId: string,
  matrixBId: string,
  tileSize: number
): Promise<JobInfo> {
  return request<JobInfo>("/multiply", {
    method: "POST",
    body: JSON.stringify({
      matrix_a_id: matrixAId,
      matrix_b_id: matrixBId,
      tile_size: tileSize,
    }),
  });
}

export async function cancelJob(jobId: string): Promise<void> {
  await request(`/jobs/${jobId}`, { method: "DELETE" });
}

export async function verifyJob(
  jobId: string,
  tolerance?: number
): Promise<VerificationResult> {
  return request<VerificationResult>(`/jobs/${jobId}/verify`, {
    method: "POST",
    body: JSON.stringify(tolerance !== undefined ? { tolerance } : {}),
  });
}

export const LARGE_MATRIX_THRESHOLD = 1024;
export const TOLERANCE_DEFAULT = 0.1;
export const TOLERANCE_LARGE = 0.5;

export function toleranceForSize(maxDim: number): number {
  return maxDim > LARGE_MATRIX_THRESHOLD ? TOLERANCE_LARGE : TOLERANCE_DEFAULT;
}

export function getProgressUrl(jobId: string): string {
  return `${BASE_URL}/jobs/${jobId}/progress`;
}
