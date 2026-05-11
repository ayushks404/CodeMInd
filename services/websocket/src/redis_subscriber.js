import Redis from "ioredis";

const REDIS_URL = process.env.REDIS_URL || "redis://redis:6379/0";

export function startRedisSubscriber(pushToUser) {
  // Separate Redis connection for pub/sub
  // pub/sub connection cannot be used for other commands
  const subscriber = new Redis(REDIS_URL);

  // Subscribe to all ws:notify:* channels
  // psubscribe = pattern subscribe
  subscriber.psubscribe("ws:notify:*", (err, count) => {
    if (err) {
      console.error("[redis] Failed to subscribe:", err.message);
      return;
    }
    console.log(`[redis] Subscribed to ws:notify:* — ${count} pattern(s)`);
  });

  // When a message arrives on any ws:notify:* channel
  subscriber.on("pmessage", (pattern, channel, message) => {
    // channel = "ws:notify:abc123"
    // user_id = "abc123"
    const userId = channel.replace("ws:notify:", "");

    try {
      const parsed = JSON.parse(message);
      pushToUser(userId, parsed);
    } catch (err) {
      console.error("[redis] Failed to parse message:", err.message);
    }
  });

  subscriber.on("error", (err) => {
    console.error("[redis] Subscriber error:", err.message);
  });
}