import { useState, useEffect } from "react";
import API from "../api";
import { Folder, GitBranch, Plus, Sparkles, MessageSquare, Loader2 } from "lucide-react";
import { useNavigate } from "react-router-dom";

export default function Dashboard() {
  const [name, setName] = useState("");
  const [repo, setRepo] = useState("");
  const [loading, setLoading] = useState(false);
  const [projects, setProjects] = useState([]);
  const [fetching, setFetching] = useState(true);
  const navigate = useNavigate();

  // On mount — fetch existing projects
  useEffect(() => {
    const fetchProjects = async () => {
      try {
        const res = await API.get("/project");
        const list = res.data.projects || [];
        setProjects(list);

        // If user has exactly one project, go straight to query page
        if (list.length === 1) {
          navigate(`/query/${list[0]._id}`);
        }
      } catch (err) {
        console.error("Failed to fetch projects", err);
      } finally {
        setFetching(false);
      }
    };
    fetchProjects();
  }, []);

  const createProject = async () => {
    if (!name.trim() || !repo.trim()) {
      alert("Name and repo required");
      return;
    }
    setLoading(true);
    try {
      const res = await API.post("/project", {
        name: name.trim(),
        repourl: repo.trim(),
      });
      const projectId = res.data.project._id;
      navigate(`/query/${projectId}`);
    } catch (e) {
      alert(e.response?.data?.message || "Failed to create project");
    } finally {
      setLoading(false);
    }
  };

  // Loading state while fetching projects
  if (fetching) {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center">
        <Loader2 className="text-blue-500 animate-spin" size={32} />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-black">
      <div className="max-w-4xl mx-auto p-6">

        <div className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <Sparkles className="text-blue-500" size={28} />
            <h1 className="text-3xl font-bold text-white">Dashboard</h1>
          </div>
          <p className="text-gray-400">
            {projects.length > 0
              ? "Your projects"
              : "Create a new project to start analyzing your codebase"}
          </p>
        </div>

        {/* Existing projects list */}
        {projects.length > 0 && (
          <div className="mb-8 space-y-3">
            {projects.map((p) => (
              <div
                key={p._id}
                onClick={() => navigate(`/query/${p._id}`)}
                className="flex items-center justify-between bg-gray-900 border border-gray-800 rounded-xl p-4 cursor-pointer hover:border-blue-500 transition"
              >
                <div className="flex items-center gap-3">
                  <Folder className="text-blue-400" size={20} />
                  <div>
                    <p className="text-white font-medium">{p.name}</p>
                    <p className="text-xs text-gray-500">{p.repourl}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2 text-sm text-gray-400">
                  <MessageSquare size={16} />
                  Open
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Create new project */}
        <div className="bg-gradient-to-b from-gray-900 to-black border border-gray-800 rounded-2xl shadow-2xl p-8">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-blue-500 to-cyan-500 flex items-center justify-center">
              <Plus className="text-white" size={20} />
            </div>
            <h2 className="text-xl font-semibold text-white">New Project</h2>
          </div>

          <div className="space-y-5">
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">
                Project Name
              </label>
              <div className="relative">
                <Folder className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-500" size={18} />
                <input
                  type="text"
                  autoComplete="off"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full pl-12 pr-4 py-3.5 bg-black border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-gray-600 transition"
                  placeholder="My Awesome Project"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">
                Repository URL
              </label>
              <div className="relative">
                <GitBranch className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-500" size={18} />
                <input
                  type="text"
                  autoComplete="off"
                  value={repo}
                  onChange={(e) => setRepo(e.target.value)}
                  className="w-full pl-12 pr-4 py-3.5 bg-black border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-gray-600 transition"
                  placeholder="https://github.com/username/repo"
                />
              </div>
              <p className="mt-2 text-xs text-gray-500">
                Only public GitHub repositories are supported
              </p>
            </div>

            <div className="flex justify-end pt-4">
              <button
                onClick={createProject}
                disabled={loading}
                className="px-6 py-3.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-semibold transition disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {loading ? (
                  <>
                    <Loader2 size={16} className="animate-spin" />
                    Creating...
                  </>
                ) : (
                  <>
                    <Plus size={18} />
                    Create Project
                  </>
                )}
              </button>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}