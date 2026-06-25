import express from "express";
import cors from "cors";
import dotenv from "dotenv";
import mongoose from "mongoose";
import project_routes from "./src/routes/project_routes.js";

dotenv.config();

const app = express();

app.use(cors({
  origin: process.env.FRONTEND_URL || "http://localhost:5173",
  credentials: true,
}));

app.use(express.json());

app.get("/", (req, res) => res.send("project service running"));

// Health endpoint — checked by Docker
app.get("/health", (req, res) => res.json({ status: "ok" }));

app.use("/api/project", project_routes);

const connectdb = async () => {
  try {
    await mongoose.connect(process.env.MONGO_URI);
    console.log("mongodb connected");
  } catch (err) {
    console.log("db error", err.message);
    process.exit(1);
  }
};

// FIX: was defaulting to 3002. Architecture specifies port 5002.
const PORT = process.env.PORT || 5002;
app.listen(PORT, () => console.log(`project service running on port ${PORT}`));
connectdb();