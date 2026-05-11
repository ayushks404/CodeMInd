import express from "express";
import { register, login, logout, verify } from "../controllers/authcontrollers.js";
import { protect } from "../middleware/authmiddleware.js";

const router = express.Router();

router.post("/register", register);
router.post("/login", login);
router.post("/logout", protect, logout);

// Internal endpoint — called by WebSocket service to validate JWTs.
// Architecture Section 9.1: not exposed through Nginx, service-to-service only.
router.post("/verify", verify);

export default router;