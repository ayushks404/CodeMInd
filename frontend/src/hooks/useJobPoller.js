import { useEffect, useRef } from "react";
import API from "../api";

export function useJobPoller(jobId, onComplete, enabled = true) {
  const intervalRef = useRef(null);

  useEffect(() => {
    if (!jobId || !enabled) return;

    intervalRef.current = setInterval(async () => {
      try {
        const res = await API.get(`/query/${jobId}`);
        const { status } = res.data;

        if (status === "completed") {
          clearInterval(intervalRef.current);
          onComplete({ success: true, data: res.data });
        }

        if (status === "failed") {
          clearInterval(intervalRef.current);
          onComplete({ success: false, reason: res.data.reason });
        }

      } catch (err) {
        console.error("[poller] Error:", err.message);
      }
    }, 3000); // poll every 3 seconds

    return () => clearInterval(intervalRef.current);
  }, [jobId, enabled]);
}