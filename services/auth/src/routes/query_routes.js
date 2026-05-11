import express from "express";
import { protect } from "../middleware/authmiddleware.js";
import {
  ask_ques,
  getJobStatus,
  getQueryHistory,
} from "../controllers/query_controllers.js";

const router = express.Router();

// POST /api/query — submit question, get job_id immediately
router.post("/", protect, ask_ques);

// GET /api/query/history/:projectId — past queries
// IMPORTANT: this route must be before /:jobId
// otherwise "history" gets treated as a jobId
router.get("/history/:projectId", protect, getQueryHistory);

// GET /api/query/:jobId — poll job status
router.get("/:jobId", protect, getJobStatus);

export default router;