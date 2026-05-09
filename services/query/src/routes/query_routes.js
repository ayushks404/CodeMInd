import express from "express";
import { protect } from "../middleware/authmiddleware.js";
import { ask_ques, getQueryHistory } from "../controllers/query_controllers.js";

const router = express.Router();

router.post("/", protect, ask_ques);
router.get("/history/:projectId", protect, getQueryHistory);

export default router;
