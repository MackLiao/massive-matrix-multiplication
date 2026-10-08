import { useState, useCallback, useRef } from "react";
import type { JobState, JobCompleteEvent, TileStatusEvent, TileStatus } from "../types";
import { useSSE } from "./useSSE";
import { getProgressUrl } from "../api/client";

const INITIAL_STATE: JobState = {
  jobId: null,
  tileGrid: [],
  currentTile: null,
  completed: 0,
  total: 0,
  elapsed: 0,
  finished: false,
  tileTimes: [],
  phaseTimings: null,
};

export function useJob() {
  const [state, setState] = useState<JobState>(INITIAL_STATE);
  const lastTileTime = useRef<number>(0);
  // Track how many k-tiles have completed per (i,j) block
  const kDone = useRef<number[][]>([]);
  const kTotalRef = useRef<number>(1);

  const sseUrl =
    state.jobId && !state.finished
      ? getProgressUrl(state.jobId)
      : null;

  const startJob = useCallback(
    (jobId: string, gridI: number, gridJ: number, kTotal: number) => {
      const grid: TileStatus[][] = Array.from({ length: gridI }, () =>
        Array.from({ length: gridJ }, () => "pending" as TileStatus)
      );
      kDone.current = Array.from({ length: gridI }, () =>
        Array.from({ length: gridJ }, () => 0)
      );
      kTotalRef.current = kTotal;
      lastTileTime.current = Date.now();
      setState({
        jobId,
        tileGrid: grid,
        currentTile: null,
        completed: 0,
        total: 0,
        elapsed: 0,
        finished: false,
        tileTimes: [],
      });
    },
    []
  );

  const onTile = useCallback((data: unknown) => {
    if (
      typeof data !== "object" || data === null ||
      typeof (data as Record<string, unknown>).i !== "number" ||
      typeof (data as Record<string, unknown>).j !== "number" ||
      typeof (data as Record<string, unknown>).k !== "number" ||
      typeof (data as Record<string, unknown>).status !== "string"
    ) {
      return;
    }
    const event = data as TileStatusEvent;
    setState((prev) => {
      const grid = prev.tileGrid.map((row) => [...row]);

      if (event.status === "in_flight") {
        if (grid[event.i] && grid[event.i][event.j] !== "completed") {
          grid[event.i][event.j] = "in_flight";
        }
        return {
          ...prev,
          tileGrid: grid,
          currentTile: { i: event.i, j: event.j, k: event.k },
          elapsed: event.elapsed,
          total: event.total,
        };
      }

      // completed or failed
      if (event.status === "completed" || event.status === "failed") {
        if (grid[event.i]) {
          if (event.status === "failed") {
            grid[event.i][event.j] = "failed";
          } else {
            // Only mark "completed" when ALL k-tiles for this (i,j) are done
            kDone.current[event.i][event.j]++;
            if (kDone.current[event.i][event.j] >= kTotalRef.current) {
              grid[event.i][event.j] = "completed";
            }
          }
        }

        const now = Date.now();
        const tileTime = (now - lastTileTime.current) / 1000;
        lastTileTime.current = now;

        return {
          ...prev,
          tileGrid: grid,
          completed: event.completed,
          total: event.total,
          elapsed: event.elapsed,
          tileTimes:
            event.status === "completed"
              ? [...prev.tileTimes, tileTime]
              : prev.tileTimes,
        };
      }

      return prev;
    });
  }, []);

  const onComplete = useCallback((data: unknown) => {
    const event = data as JobCompleteEvent;
    setState((prev) => ({
      ...prev,
      finished: true,
      phaseTimings: event.phase_timings ?? null,
    }));
  }, []);

  const onDone = useCallback(() => {
    setState((prev) => ({ ...prev, finished: true, currentTile: null }));
  }, []);

  const onError = useCallback(() => {
    setState((prev) => ({ ...prev, finished: true, currentTile: null }));
  }, []);

  useSSE({ url: sseUrl, onTile, onComplete, onDone, onError });

  const reset = useCallback(() => {
    setState(INITIAL_STATE);
    kDone.current = [];
    kTotalRef.current = 1;
  }, []);

  return { state, startJob, reset };
}
