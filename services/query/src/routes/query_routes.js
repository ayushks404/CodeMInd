import express from "express";
import { protect } from "../middleware/authmiddleware.js";
import {
  ask_ques,
  getJobStatus,
  getQueryHistory,
} from "../controllers/query_controllers.js";

const router = express.Router();

// POST /api/query — question submit karo, job_id milega turant
router.post("/", protect, ask_ques);

// GET /api/query/history/:projectId — PEHLE yeh route hona chahiye
// warna "history" ko jobId samjh lega Express
router.get("/history/:projectId", protect, getQueryHistory);

// GET /api/query/:jobId — polling fallback
router.get("/:jobId", protect, getJobStatus);

export default router;