import express from "express";
import { protect } from "../middleware/authmiddleware.js";
import {
  createproject,
  getProjectById,
  getUserProjects,
  deleteProject,
} from "../controllers/project_controllers.js";

const router = express.Router();

router.post("/", protect, createproject);
router.get("/", protect, getUserProjects);
router.get("/:id", protect, getProjectById);
router.delete("/:id", protect, deleteProject);

export default router;
