export interface MatrixInfo {
  id: string;
  rows: number;
  cols: number;
}

export interface JobInfo {
  job_id: string;
}

export type TileStatus = "pending" | "in_flight" | "completed" | "failed";

export interface TileStatusEvent {
  i: number;
  j: number;
  k: number;
  status: TileStatus;
  completed: number;
  total: number;
  elapsed: number;
}

export interface PhaseStats {
  total: number;
  mean: number;
  min: number;
  max: number;
  count: number;
}

export interface PhaseTimings {
  client_serialization_sec?: PhaseStats;
  network_round_trip_sec?: PhaseStats;
  client_deserialization_sec?: PhaseStats;
  board_deserialization_sec?: PhaseStats;
  board_computation_sec?: PhaseStats;
  board_serialization_sec?: PhaseStats;
  accumulation_sec?: PhaseStats;
}

export interface JobCompleteEvent {
  status: string;
  completed: number;
  total: number;
  elapsed: number;
  phase_timings?: PhaseTimings;
}

export interface VerificationResult {
  max_abs_error: number;
  mean_abs_error: number;
  passed: boolean;
  tolerance: number;
}

export interface JobState {
  jobId: string | null;
  tileGrid: TileStatus[][];  // [I][J] — shows aggregate status for (i,j) block
  currentTile: { i: number; j: number; k: number } | null;
  completed: number;
  total: number;
  elapsed: number;
  finished: boolean;
  tileTimes: number[];  // for ETA calculation
  phaseTimings: PhaseTimings | null;
}

export interface BenchmarkConfig {
  matrixSize: number;
  tileSize: number;
}

export interface BenchmarkRun {
  config: BenchmarkConfig;
  runIndex: number;
  elapsed: number | null;
  status: "pending" | "running" | "completed" | "failed";
}

export interface BenchmarkResult {
  config: BenchmarkConfig;
  avgElapsed: number;
  runs: number[];
}
