import Project from "../models/project.js";
import axios from "axios";

// GitHub URL validator — same regex as Python app.py
const GITHUB_URL_PATTERN = /^https:\/\/github\.com\/[\w\-]+\/[\w\-\.]+\/?$/;

function validateGithubUrl(url) {
  return GITHUB_URL_PATTERN.test(url);
}

export const createproject = async (req, res) => {
  try {
    const { name, repourl } = req.body;

    if (!name || !repourl) {
      return res.status(400).json({ message: "Name and repo URL required" });
    }

    // FIX: validate GitHub URL before touching the database
    if (!validateGithubUrl(repourl)) {
      return res.status(400).json({
        message: "Only public GitHub URLs are supported. Format: https://github.com/owner/repo",
      });
    }

    const exists = await Project.findOne({ repourl, owner: req.user._id });
    if (exists) {
      return res.status(400).json({ message: "Project already exists" });
    }

    const project = await Project.create({
      name,
      repourl,
      owner: req.user._id,
      indexed: false,
    });

    // Fire-and-forget — do not await, do not block the response
    const AI_SERVICE = process.env.AI_SERVICE_URL;
    axios
      .post(`${AI_SERVICE}/index-repo`, {
        project_id: project._id.toString(),
        repo_url: repourl,
      })
      .catch((err) => {
        console.error("AI indexing trigger failed:", err.message);
      });

    return res.status(201).json({ project });
  } catch (err) {
    console.error("Create project error:", err);
    return res.status(500).json({ message: err.message });
  }
};

export const getProjectById = async (req, res) => {
  try {
    const project = await Project.findOne({
      _id: req.params.id,
      owner: req.user._id,
    });

    if (!project) {
      return res.status(404).json({ message: "Project not found" });
    }

    return res.json({
      name: project.name,
      repourl: project.repourl,
      // FIX: was project.index (undefined) — field in schema is `indexed`
      indexed: project.indexed,
    });
  } catch (err) {
    console.error("Get project error:", err);
    return res.status(500).json({ message: err.message });
  }
};

export const getUserProjects = async (req, res) => {
  try {
    const projects = await Project.find({ owner: req.user._id }).sort({
      createdAt: -1,
    });
    return res.json({ projects });
  } catch (err) {
    return res.status(500).json({ message: err.message });
  }
};

export const deleteProject = async (req, res) => {
  try {
    const project = await Project.findOne({
      _id: req.params.id,
      owner: req.user._id,
    });

    if (!project) {
      return res.status(404).json({ message: "Project not found" });
    }

    // Trigger AI cleanup before deleting from DB
    const AI_SERVICE = process.env.AI_SERVICE_URL;
    try {
      await axios.post(`${AI_SERVICE}/cleanup`, {
        project_id: project._id.toString(),
      });
    } catch (err) {
      console.error("AI cleanup failed:", err.message);
      // Continue with deletion even if AI cleanup fails
    }

    await Project.deleteOne({ _id: project._id });

    return res.json({ message: "Project deleted successfully" });
  } catch (err) {
    return res.status(500).json({ message: err.message });
  }
};
