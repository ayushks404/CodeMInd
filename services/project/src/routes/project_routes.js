import express from "express";
import { protect } from "../middleware/authmiddleware.js";
import {
  createproject,
  getProjectById,
  getUserProjects,
  deleteProject,
  markProjectIndexed,
} from "../controllers/project_controllers.js";

const router = express.Router();

/**
 * internalOnly — guards routes that must only be called by trusted internal services.
 * Checks the x-internal-secret header against INTERNAL_SECRET env var.
 * This route is never reachable from Nginx / the browser.
 */
const internalOnly = (req, res, next) => {
  const secret = process.env.INTERNAL_SECRET;
  if (!secret || req.headers["x-internal-secret"] !== secret) {
    return res.status(403).json({ message: "Forbidden" });
  }
  next();
};

router.post("/",        protect,       createproject);
router.get("/",         protect,       getUserProjects);
router.get("/:id",      protect,       getProjectById);
router.delete("/:id",   protect,       deleteProject);

// Called by index_worker.py after indexing finishes — not by the browser.
router.patch("/:id/indexed", internalOnly, markProjectIndexed);

export default router;