import axios from "axios";

// Single base URL — Vite proxy (dev) and Nginx (prod) route /api/auth, /api/project,
// /api/query to the correct backend services. The frontend never needs to know which
// port each service lives on.
const API = axios.create({
  baseURL: "/api",
  headers: { "Content-Type": "application/json" },
});

API.interceptors.request.use((config) => {
  const token = localStorage.getItem("cp_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export default API;