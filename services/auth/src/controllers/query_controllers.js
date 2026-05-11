import Query from "../models/query.js";
import JobStatus from "../models/job_status.js";
import { pushQueryJob } from "../jobs/query_job_producer.js";
import { createHash } from "crypto";
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

    // ─── Cache Check ───────────────────────────────────────────
    // Same question pehle poochi ja chuki hai?
    // Hash banao question se — exact match ke liye
    const questionHash = createHash("sha256")
      .update(`${project_id}:${question.trim().toLowerCase()}`)
      .digest("hex");

    const cacheKey    = `cache:query:${questionHash}`;
    const cachedValue = await redis.get(cacheKey);

    if (cachedValue) {
      // Cache hit — LLM call skip karo, turant return karo
      const cached = JSON.parse(cachedValue);
      console.log(`[cache] HIT for question: ${question.substring(0, 50)}`);
      return res.json({
        ...cached,
        cached: true,
      });
    }
    // ─── Cache Miss ────────────────────────────────────────────

    const userId = req.user._id.toString();

    // Celery queue mein push karo — job_id turant milega
    const jobId = await pushQueryJob({
      projectId: project_id,
      userId,
      question,
    });

    // job_id → questionHash mapping Redis mein store karo
    // Jab job complete hoga, answer cache karna hai
    // Worker ko pata nahi hota cacheKey, isliye yahan store karte hain
    await redis.set(
      `job:cache_key:${jobId}`,
      cacheKey,
      "EX",
      7200  // 2 hours — job itne time mein complete ho jaayega
    );

    // Job status MongoDB mein track karo
    await JobStatus.create({
      jobId,
      type:      "query",
      status:    "queued",
      userId:    req.user._id,
      projectId: project_id,
    });

    console.log(`[query] Job ${jobId} queued for: ${question.substring(0, 50)}`);

    // Turant return — user ko spinner dikhega
    return res.json({ job_id: jobId, cached: false });

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