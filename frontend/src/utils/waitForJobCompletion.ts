import { getProgressUrl } from "../api/client";

export function waitForJobCompletion(
  jobId: string,
  onCancel?: () => boolean
): Promise<{ elapsed: number; status: string }> {
  return new Promise((resolve, reject) => {
    const url = getProgressUrl(jobId);
    const es = new EventSource(url);
    let settled = false;
    let errorCount = 0;

    const cleanup = () => {
      clearInterval(cancelInterval);
      es.close();
    };

    const cancelInterval = setInterval(() => {
      if (onCancel?.()) {
        cleanup();
        if (!settled) {
          settled = true;
          reject(new Error("cancelled"));
        }
      }
    }, 500);

    es.addEventListener("complete", (e: MessageEvent) => {
      cleanup();
      if (settled) return;
      settled = true;
      try {
        const data = JSON.parse(e.data);
        if (typeof data.elapsed !== "number") {
          reject(new Error("Malformed complete payload: missing elapsed"));
          return;
        }
        resolve({ elapsed: data.elapsed, status: data.status ?? "completed" });
      } catch {
        reject(new Error("Failed to parse SSE complete payload"));
      }
    });

    es.addEventListener("done", () => {
      cleanup();
      if (settled) return;
      settled = true;
      reject(new Error("Job ended without a complete event"));
    });

    es.onerror = () => {
      errorCount++;
      if (errorCount >= 3 || es.readyState === EventSource.CLOSED) {
        cleanup();
        if (!settled) {
          settled = true;
          reject(new Error("SSE connection lost"));
        }
      }
    };
  });
}
