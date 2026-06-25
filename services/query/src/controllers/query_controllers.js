// FIX: "import crypto from 'crypto'" fails in some ES module contexts.
// Named import is the correct pattern for Node.js built-ins with "type": "module".
import { createHash } from "crypto";
import Query from "../models/query.js";
import JobStatus from "../models/job_status.js";
import { pushQueryJob } from "../jobs/query_job_producer.js";
import Redis from "ioredis";

const redis = new Redis(process.env.REDIS_URL || "redis://redis:6379/0");

// POST /api/query
export const ask_ques = async (req, res) => {
  try {
    const { project_id, question } = req.body;

    if (!project_id || !question) {
      return res.status(400).json({
        message: "project_id and question are required",
      });
    }

    const userId = req.user._id.toString();

    // SHA256 hash of project_id:question — identical questions skip the queue entirely.
    const cacheKey = createHash("sha256")
      .update(`${project_id}:${question}`)
      .digest("hex");

    const cached = await redis.get(`cache:query:${cacheKey}`);
    if (cached) {
      const parsed = JSON.parse(cached);
      return res.json({
        job_id:     null,
        cached:     true,
        answer:     parsed.answer,
        sources:    parsed.sources,
        confidence: parsed.confidence,
      });
    }

    // Not cached — push to Celery queue
    const jobId = await pushQueryJob({
      projectId: project_id,
      userId,
      question,
    });

    // Store cache_key on the job so query_worker can write the result back to cache.
    await JobStatus.create({
      jobId,
      type:      "query",
      status:    "queued",
      userId:    req.user._id,
      projectId: project_id,
      cacheKey,
    });

    // jobId → cacheKey mapping so the worker can look it up on completion.
    await redis.set(`job:cache_key:${jobId}`, cacheKey, "EX", 86400);

    return res.json({ job_id: jobId });

  } catch (err) {
    console.error("Query error:", err.message);
    return res.status(500).json({ message: "Cannot process query" });
  }
};

// GET /api/query/:jobId — polling fallback
export const getJobStatus = async (req, res) => {
  try {
    const { jobId } = req.params;

    const job = await JobStatus.findOne({
      jobId,
      userId: req.user._id,
    });

    if (!job) {
      return res.status(404).json({ message: "Job not found" });
    }

    if (job.status === "completed") {
      return res.json({
        status:     "completed",
        answer:     job.answer,
        confidence: job.confidence,
        sources:    job.sources,
        trace:      job.trace,
      });
    }

    if (job.status === "failed_final") {
      return res.json({
        status:    "failed",
        reason:    job.error,
        retryable: true,
      });
    }

    return res.json({ status: job.status });

  } catch (err) {
    return res.status(500).json({ message: err.message });
  }
};

// GET /api/query/history/:projectId
export const getQueryHistory = async (req, res) => {
  try {
    const { projectId } = req.params;
    const queries = await Query.find({
      projectId,
      userId: req.user._id,
    }).sort({ createdAt: -1 }).limit(50);

    return res.json({ queries });
  } catch (err) {
    return res.status(500).json({ message: err.message });
  }
};