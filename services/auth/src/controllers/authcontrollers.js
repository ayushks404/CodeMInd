import User from "../models/user.js";
import jwt from "jsonwebtoken";
import bcrypt from "bcryptjs";

// JWT: 7 days. Refresh: 30 days (Phase 2).
// Previously hardcoded to 30d for JWT — fixed.
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

    // bcrypt rounds: 12 (was 10)
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
    // Phase 2 addition:
    // const token = req.headers.authorization.split(" ")[1];
    // await redis.set(`blocklist:${token}`, "1", "EX", 604800);
    return res.json({ message: "Logged out successfully" });
  } catch (err) {
    return res.status(500).json({ message: err.message });
  }
};
