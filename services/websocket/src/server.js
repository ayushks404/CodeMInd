import { WebSocketServer } from "ws";
import dotenv from "dotenv";
import { startRedisSubscriber } from "./redis_subscriber.js";

dotenv.config();

const PORT = process.env.WS_PORT || 5004;

// Map of user_id → WebSocket connection
// When Redis message arrives for a user, we look them up here
const clients = new Map();

const wss = new WebSocketServer({ port: PORT });

wss.on("connection", (ws, req) => {
  // Frontend connects as: ws://localhost:5004?user_id=abc
  const url    = new URL(req.url, `http://localhost:${PORT}`);
  const userId = url.searchParams.get("user_id");

  if (!userId) {
    ws.close(1008, "user_id required");
    return;
  }

  // Store connection
  clients.set(userId, ws);
  console.log(`[ws] User ${userId} connected`);

  // Send confirmation to frontend
  ws.send(JSON.stringify({ event: "connected", user_id: userId }));

  // Remove connection when browser closes
  ws.on("close", () => {
    clients.delete(userId);
    console.log(`[ws] User ${userId} disconnected`);
  });

  ws.on("error", (err) => {
    console.error(`[ws] Error for user ${userId}:`, err.message);
    clients.delete(userId);
  });
});

// This function is called by redis_subscriber.js
// when a message arrives for a user
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

// Start Redis subscriber
startRedisSubscriber(pushToUser);

console.log(`[ws] WebSocket service running on port ${PORT}`);