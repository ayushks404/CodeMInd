import { useEffect, useRef, useCallback } from "react";

const WS_URL = import.meta.env.VITE_WS_URL || "ws://localhost:5004";

export function useWebSocket(userId, onMessage) {
  const wsRef = useRef(null);

  const connect = useCallback(() => {
    if (!userId) return;

    const ws = new WebSocket(`${WS_URL}?user_id=${userId}`);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log("[ws] Connected");
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessage(data);
      } catch (err) {
        console.error("[ws] Failed to parse message:", err);
      }
    };

    ws.onclose = () => {
      console.log("[ws] Disconnected — reconnecting in 3s");
      // Auto reconnect after 3 seconds
      setTimeout(connect, 3000);
    };

    ws.onerror = (err) => {
      console.error("[ws] Error:", err);
      ws.close();
    };
  }, [userId, onMessage]);

  useEffect(() => {
    connect();
    return () => {
      if (wsRef.current) {
        wsRef.current.onclose = null; // prevent reconnect on unmount
        wsRef.current.close();
      }
    };
  }, [connect]);
}