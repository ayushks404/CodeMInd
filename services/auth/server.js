import express from "express";
import cors from "cors";
import dotenv from "dotenv";
import mongoose from "mongoose";
import auth_routes from "./src/routes/auth_routes.js";

dotenv.config();

const app = express();

app.use(cors({
  origin: process.env.FRONTEND_URL || "http://localhost:5173",
  credentials: true,
}));

app.use(express.json());

app.get("/", (req, res) => res.send("auth service running"));

// FIX: /health was missing — project/query middleware calls auth:5001/api/auth/verify
// on every request; Docker needs this endpoint to know auth is ready before
// starting dependent services.
app.get("/health", (req, res) => res.json({ status: "ok" }));

app.use("/api/auth", auth_routes);

const connectdb = async () => {
  try {
    await mongoose.connect(process.env.MONGO_URI);
    console.log("mongodb connected");
  } catch (err) {
    console.log("db error", err.message);
    process.exit(1);
  }
};

const PORT = process.env.PORT || 5001;
app.listen(PORT, () => console.log(`auth service running on port ${PORT}`));

connectdb();