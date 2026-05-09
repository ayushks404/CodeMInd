import Query from "../models/query.js";
import axios from "axios";

export const ask_ques = async (req, res) => {
  try {
    const { project_id, question } = req.body;

    if (!project_id || !question) {
      return res.status(400).json({
        message: "project_id and question are required",
      });
    }

    const AI_SERVICE = process.env.AI_SERVICE_URL;
    const airesponse = await axios.post(`${AI_SERVICE}/query`, {
      project_id,
      question,
    });

    // FIX: single source of truth for response shape.
    // Backend defines the shape. Frontend reads the same keys.
    // No more guess chain on either side.
    const answer     = airesponse.data.answer     ?? "No answer received.";
    const sources    = airesponse.data.sources    ?? [];
    const confidence = airesponse.data.confidence ?? null;
    const trace      = airesponse.data.trace      ?? [];
    const iterations = airesponse.data.iterations ?? 0;

    await Query.create({
      projectId: project_id,
      userId: req.user._id,
      question,
      answer,
      sources,
      confidence,
      iterations,
    });

    // Single consistent response shape — frontend reads exactly these keys
    return res.json({ answer, sources, confidence, trace, iterations });

  } catch (err) {
    console.error("Query error:", err.message);
    return res.status(500).json({ message: "Cannot process query" });
  }
};

export const getQueryHistory = async (req, res) => {
  try {
    const { projectId } = req.params;
    const queries = await Query.find({
      projectId,
      userId: req.user._id,
    }).sort({ createdAt: -1 }).limit(50);

    return res.json({ queries });
  } catch (err) {
    return res.status(500).json({ message: err.message });
  }
};
