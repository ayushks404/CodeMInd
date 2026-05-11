import Project from "../models/project.js";
import { pushIndexJob } from "../jobs/index_job_producer.js";
import axios from "axios";

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
      owner:   req.user._id,
      indexed: false,
    });

    const userId    = req.user._id.toString();
    const projectId = project._id.toString();

    // Phase 2: Celery index_jobs queue mein push karo
    // user_id zaroori hai taaki WebSocket notification sahi user ko jaaye
    pushIndexJob({
      projectId,
      userId,
      repoUrl: repourl,
    }).catch((err) => {
      console.error("Index job push failed:", err.message);
    });

    // Architecture ke according response shape
    return res.status(201).json({
      project_id: projectId,
      status:     "indexing",
    });

  } catch (err) {
    console.error("Create project error:", err);
    return res.status(500).json({ message: err.message });
  }
};

export const getProjectById = async (req, res) => {
  try {
    const project = await Project.findOne({
      _id:   req.params.id,
      owner: req.user._id,
    });

    if (!project) {
      return res.status(404).json({ message: "Project not found" });
    }

    return res.json({
      id:      project._id,
      name:    project.name,
      repourl: project.repourl,
      indexed: project.indexed,
    });
  } catch (err) {
    return res.status(500).json({ message: err.message });
  }
};

export const getUserProjects = async (req, res) => {
  try {
    const projects = await Project.find({ owner: req.user._id }).sort({ createdAt: -1 });
    return res.json({ projects });
  } catch (err) {
    return res.status(500).json({ message: err.message });
  }
};

export const deleteProject = async (req, res) => {
  try {
    const project = await Project.findOne({
      _id:   req.params.id,
      owner: req.user._id,
    });

    if (!project) {
      return res.status(404).json({ message: "Project not found" });
    }

    const AI_SERVICE = process.env.AI_SERVICE_URL;
    try {
      await axios.post(`${AI_SERVICE}/cleanup`, {
        project_id: project._id.toString(),
      });
    } catch (err) {
      console.error("AI cleanup failed:", err.message);
    }

    await Project.deleteOne({ _id: project._id });
    return res.json({ message: "Project deleted successfully" });
  } catch (err) {
    return res.status(500).json({ message: err.message });
  }
};