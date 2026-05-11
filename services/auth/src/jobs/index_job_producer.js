import Redis from "ioredis";
import { v4 as uuidv4 } from "uuid";

const redis = new Redis(process.env.REDIS_URL || "redis://redis:6379/0");

export async function pushIndexJob({ projectId, userId, repoUrl }) {
  const jobId = uuidv4();

  const body = Buffer.from(JSON.stringify([
    [],
    { job_id: jobId, project_id: projectId, user_id: userId, repo_url: repoUrl },
    { callbacks: null, errbacks: null, chain: null, chord: null },
  ])).toString("base64");

  const task = {
    body,
    "content-type": "application/json",
    "content-encoding": "utf-8",
    headers: {
      lang: "py",
      task: "workers.index_worker.run_index",
      id: jobId,
      retries: 0,
      root_id: jobId,
      parent_id: null,
      group: null,
    },
    properties: {
      correlation_id: jobId,
      reply_to: "",
      delivery_mode: 2,
      delivery_info: { exchange: "", routing_key: "index_jobs" },
      priority: 0,
      body_encoding: "base64",
      delivery_tag: uuidv4(),
    },
  };

  await redis.lpush("index_jobs", JSON.stringify(task));
  return jobId;
}
