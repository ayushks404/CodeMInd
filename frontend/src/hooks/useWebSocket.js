import { useEffect, useRef, useCallback } from "react";

const WS_URL = import.meta.env.VITE_WS_URL || "ws://localhost:5004";

/**
 * useWebSocket — stable WebSocket connection that never reconnects
 * just because the message handler changed.
 *
 * Fixes:
 *  1. onMessage stored in a ref → ws.onmessage always calls the LATEST
 *     handler without needing to re-run connect(). This kills the
 *     stale-closure / reconnect-on-every-query bug.
 *
 *  2. connect() only depends on userId → useEffect only fires once per
 *     user session, not on every render / state change.
 *
 *  3. onConnect / onDisconnect callbacks let query.jsx track real WS
 *     status so the fallback poller activates correctly.
 *
 *  4. JWT token sent in connection URL so the WS server can verify the
 *     user (architecture Section 12 requirement).
 *
 * @param {string|null}  userId
 * @param {function}     onMessage    - called with parsed JSON on every message
 * @param {object}       [callbacks]
 * @param {function}     [callbacks.onConnect]    - called when WS opens
 * @param {function}     [callbacks.onDisconnect] - called when WS closes/errors
 */
export function useWebSocket(userId, onMessage, { onConnect, onDisconnect } = {}) {
  const wsRef          = useRef(null);

  // Always point to the latest handler — no re-connect needed when it changes
  const onMessageRef    = useRef(onMessage);
  const onConnectRef    = useRef(onConnect);
  const onDisconnectRef = useRef(onDisconnect);

  // Keep refs current every render (cheap, no effect needed)
  onMessageRef.current    = onMessage;
  onConnectRef.current    = onConnect;
  onDisconnectRef.current = onDisconnect;

  const connect = useCallback(() => {
    if (!userId) return;

    // Architecture Section 12: connection must carry JWT for server-side auth
    const token = localStorage.getItem("cp_token") || "";
    const ws = new WebSocket(`${WS_URL}?user_id=${userId}&token=${token}`);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log("[ws] Connected");
      onConnectRef.current?.();
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        // Always calls the latest handler — ref is never stale
        onMessageRef.current(data);
      } catch (err) {
        console.error("[ws] Failed to parse message:", err);
      }
    };

    ws.onclose = () => {
      console.log("[ws] Disconnected — reconnecting in 3s");
      onDisconnectRef.current?.();
      // Auto-reconnect — connect() is stable (userId-only dep) so this is safe
      setTimeout(connect, 3000);
    };

    ws.onerror = (err) => {
      console.error("[ws] Error:", err);
      // onclose fires after onerror, so onDisconnect is called there
      ws.close();
    };
  }, [userId]); // ← userId ONLY. onMessage is NOT a dep — that's the whole fix.

  useEffect(() => {
    connect();
    return () => {
      if (wsRef.current) {
        // Prevent the onclose handler from scheduling a reconnect on unmount
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
  }, [connect]);
}