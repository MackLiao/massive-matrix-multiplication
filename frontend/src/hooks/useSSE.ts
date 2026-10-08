import { useEffect, useRef, useCallback } from "react";

interface UseSSEOptions {
  url: string | null;
  onTile: (data: unknown) => void;
  onComplete: (data: unknown) => void;
  onDone: () => void;
  onError?: () => void;
}

export function useSSE({ url, onTile, onComplete, onDone, onError }: UseSSEOptions) {
  const sourceRef = useRef<EventSource | null>(null);
  const callbacksRef = useRef({ onTile, onComplete, onDone, onError });

  // Keep callbacks ref up-to-date without re-subscribing
  callbacksRef.current = { onTile, onComplete, onDone, onError };

  const close = useCallback(() => {
    if (sourceRef.current) {
      sourceRef.current.close();
      sourceRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (!url) return;

    close();

    const es = new EventSource(url);
    sourceRef.current = es;

    es.addEventListener("tile", (e) => {
      try {
        callbacksRef.current.onTile(JSON.parse(e.data));
      } catch {
        // ignore parse errors
      }
    });

    es.addEventListener("complete", (e) => {
      try {
        callbacksRef.current.onComplete(JSON.parse(e.data));
      } catch {
        // ignore
      }
    });

    es.addEventListener("done", () => {
      callbacksRef.current.onDone();
      close();
    });

    es.onerror = () => {
      // EventSource auto-reconnects; if CLOSED, give up
      if (es.readyState === EventSource.CLOSED) {
        callbacksRef.current.onError?.();
        close();
      }
    };

    return close;
  }, [url, close]);

  return { close };
}
