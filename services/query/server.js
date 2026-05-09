import express from "express";
import cors from "cors";
import dotenv from "dotenv";
import mongoose from "mongoose";
import query_routes from "./src/routes/query_routes.js";

dotenv.config();

const app = express();

app.use(cors({
  origin: process.env.FRONTEND_URL || "http://localhost:5173",
  credentials: true,
}));

app.use(express.json());

app.get("/", (req, res) => res.send("query service running"));
app.use("/api/query", query_routes);

const connectdb = async () => {
  try {
    await mongoose.connect(process.env.MONGO_URI);
    console.log("mongodb connected");
  } catch (err) {
    console.log("db error", err.message);
    process.exit(1);
  }
};

const PORT = process.env.PORT || 3003;
app.listen(PORT, () => console.log(`query service running on port ${PORT}`));
connectdb();
