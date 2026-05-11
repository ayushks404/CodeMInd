import { WebSocketServer } from "ws";
import dotenv from "dotenv";
import fetch from "node-fetch";
import { startRedisSubscriber } from "./redis_subscriber.js";

dotenv.config();

const PORT         = process.env.WS_PORT      || 5004;
const AUTH_SERVICE = process.env.AUTH_SERVICE_URL || "http://auth-service:5001";

// Map of user_id → WebSocket connection
const clients = new Map();

const wss = new WebSocketServer({ port: PORT });

/**
 * Verify the JWT token with the Auth Service.
 * Architecture Section 9.1: every service validates tokens by calling
 * POST /auth/verify on the Auth Service — never by sharing the JWT secret.
 *
 * Returns user_id string on success, null on failure.
 */
async function verifyToken(token) {
  if (!token) return null;
  try {
    const res  = await fetch(`${AUTH_SERVICE}/api/auth/verify`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ token }),
    });
    const body = await res.json();
    if (body.valid && body.user_id) return body.user_id;
    return null;
  } catch (err) {
    console.error("[ws] Auth service verification failed:", err.message);
    return null;
  }
}

wss.on("connection", async (ws, req) => {
  const url    = new URL(req.url, `http://localhost:${PORT}`);
  const userId = url.searchParams.get("user_id");
  const token  = url.searchParams.get("token");

  // 1. Reject if no user_id in URL
  if (!userId) {
    ws.close(1008, "user_id required");
    return;
  }

  // 2. Verify JWT — architecture requires it (Section 9.1 + Section 12)
  const verifiedUserId = await verifyToken(token);
  if (!verifiedUserId) {
    console.warn(`[ws] Rejected unauthenticated connection for user_id=${userId}`);
    ws.close(1008, "invalid or missing token");
    return;
  }

  // 3. Sanity check: token's user must match the user_id in the URL
  //    Prevents user A spoofing user B's connection.
  if (verifiedUserId !== userId) {
    console.warn(`[ws] user_id mismatch — token=${verifiedUserId} url=${userId}`);
    ws.close(1008, "user_id mismatch");
    return;
  }

  // Store connection (one connection per user — latest wins)
  clients.set(userId, ws);
  console.log(`[ws] User ${userId} connected and verified`);

  // Confirm connection to frontend so it sets wsConnected = true
  ws.send(JSON.stringify({ event: "connected", user_id: userId }));

  ws.on("close", () => {
    clients.delete(userId);
    console.log(`[ws] User ${userId} disconnected`);
  });

  ws.on("error", (err) => {
    console.error(`[ws] Error for user ${userId}:`, err.message);
    clients.delete(userId);
  });
});

/**
 * Push a message to a connected user.
 * Called by redis_subscriber.js when a Python worker publishes to
 * ws:notify:{user_id}.
 */
export function pushToUser(userId, message) {
  const ws = clients.get(userId);

  if (!ws) {
    console.log(`[ws] No connection for user ${userId} — skipping push`);
    return;
  }

  if (ws.readyState !== ws.OPEN) {
    console.log(`[ws] Connection for user ${userId} not open — removing`);
    clients.delete(userId);
    return;
  }

  ws.send(JSON.stringify(message));
  console.log(`[ws] Pushed ${message.event} to user ${userId}`);
}

startRedisSubscriber(pushToUser);

console.log(`[ws] WebSocket service running on port ${PORT}`);