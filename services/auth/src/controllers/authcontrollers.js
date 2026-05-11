import User from "../models/user.js";
import jwt from "jsonwebtoken";
import bcrypt from "bcryptjs";

// JWT: 7 days. Refresh: 30 days (Phase 2).
const generateToken = (id) => {
  return jwt.sign({ id }, process.env.JWT_SECRET, { expiresIn: "7d" });
};

export const register = async (req, res) => {
  try {
    const { name, email, password } = req.body;

    if (!name || !email || !password) {
      return res.status(400).json({ message: "Please provide all fields" });
    }

    const userExists = await User.findOne({ email });
    if (userExists) {
      return res.status(400).json({ message: "User already exists" });
    }

    const hashpassword = await bcrypt.hash(password, 12);
    const user = await User.create({ name, email, password: hashpassword });

    return res.status(201).json({
      _id: user.id,
      name: user.name,
      email: user.email,
      token: generateToken(user.id),
    });
  } catch (err) {
    return res.status(500).json({ message: err.message });
  }
};

export const login = async (req, res) => {
  try {
    const { email, password } = req.body;

    if (!email || !password) {
      return res.status(400).json({ message: "Please provide email and password" });
    }

    const user = await User.findOne({ email });
    if (!user) {
      return res.status(401).json({ message: "Invalid email or password" });
    }

    const match = await bcrypt.compare(password, user.password);
    if (!match) {
      return res.status(401).json({ message: "Invalid email or password" });
    }

    return res.json({
      _id: user.id,
      name: user.name,
      email: user.email,
      token: generateToken(user.id),
    });
  } catch (err) {
    return res.status(500).json({ message: err.message });
  }
};

// CRITICAL FIX: old logout did deleteMany on all user data.
// Logout must ONLY invalidate the session.
// Phase 2 will add Redis token blocklist here.
export const logout = async (req, res) => {
  try {
    return res.json({ message: "Logged out successfully" });
  } catch (err) {
    return res.status(500).json({ message: err.message });
  }
};

/**
 * POST /api/auth/verify  — internal endpoint, called by WebSocket service
 * to validate a JWT without sharing the JWT_SECRET across services.
 *
 * NOT exposed through Nginx (architecture Section 9.1).
 * Body: { token: "Bearer eyJ..." }  OR  { token: "eyJ..." }
 * Returns: { valid: true, user_id: "..." } | { valid: false }
 */
export const verify = async (req, res) => {
  try {
    let { token } = req.body;

    if (!token) {
      return res.json({ valid: false });
    }

    // Strip "Bearer " prefix if present — WS sends raw token, some callers may prefix it
    if (token.startsWith("Bearer ")) {
      token = token.slice(7);
    }

    const decoded = jwt.verify(token, process.env.JWT_SECRET);

    // Confirm user still exists in DB — catches deleted accounts
    const user = await User.findById(decoded.id).select("_id");
    if (!user) {
      return res.json({ valid: false });
    }

    return res.json({ valid: true, user_id: user._id.toString() });
  } catch (err) {
    // jwt.verify throws on expired / tampered tokens — treat as invalid
    return res.json({ valid: false });
  }
};