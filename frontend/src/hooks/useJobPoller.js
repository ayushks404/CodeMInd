import { useEffect, useRef } from "react";
import API from "../api";

/**
 * useJobPoller — polls /query/:jobId every 3s as fallback when WS is down.
 *
 * Fixes:
 *  1. onComplete stored in a ref so changing the callback in query.jsx
 *     doesn't restart the interval (same stale-closure family of bugs
 *     as useWebSocket).
 *
 *  2. Effect only depends on jobId and enabled — the two things that
 *     actually mean "start/stop polling".
 *
 * @param {string|null} jobId      - null = do nothing
 * @param {function}    onComplete - called with { success, data?, reason? }
 * @param {boolean}     enabled    - set false when WS is connected
 */
export function useJobPoller(jobId, onComplete, enabled = true) {
  const intervalRef   = useRef(null);
  const onCompleteRef = useRef(onComplete);

  // Keep ref current — no effect re-run needed
  onCompleteRef.current = onComplete;

  useEffect(() => {
    if (!jobId || !enabled) return;

    intervalRef.current = setInterval(async () => {
      try {
        const res    = await API.get(`/query/${jobId}`);
        const { status } = res.data;

        if (status === "completed") {
          clearInterval(intervalRef.current);
          onCompleteRef.current({ success: true, data: res.data });
        }

        if (status === "failed") {
          clearInterval(intervalRef.current);
          onCompleteRef.current({ success: false, reason: res.data.reason });
        }

      } catch (err) {
        console.error("[poller] Error:", err.message);
        // Don't clear interval on network error — keep retrying
      }
    }, 3000);

    return () => clearInterval(intervalRef.current);
  }, [jobId, enabled]); // ← onComplete intentionally excluded (it's in a ref)
}