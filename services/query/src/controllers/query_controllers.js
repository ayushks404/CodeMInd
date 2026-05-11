import Query from "../models/query.js";
import JobStatus from "../models/job_status.js";
import { pushQueryJob } from "../jobs/query_job_producer.js";

// POST /api/query
// Phase 2: job_id return karo turant, LLM background mein chalega
export const ask_ques = async (req, res) => {
  try {
    const { project_id, question } = req.body;

    if (!project_id || !question) {
      return res.status(400).json({
        message: "project_id and question are required",
      });
    }

    const userId = req.user._id.toString();

    // Celery queue mein push karo — turant job_id milega
    const jobId = await pushQueryJob({
      projectId: project_id,
      userId,
      question,
    });

    // Job record save karo tracking ke liye
    await JobStatus.create({
      jobId,
      type:      "query",
      status:    "queued",
      userId:    req.user._id,
      projectId: project_id,
    });

    // Turant return — HTTP timeout nahi hoga
    return res.json({ job_id: jobId });

  } catch (err) {
    console.error("Query error:", err.message);
    return res.status(500).json({ message: "Cannot process query" });
  }
};

// GET /api/query/:jobId
// Polling fallback — useJobPoller yahan call karta hai har 3 seconds
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