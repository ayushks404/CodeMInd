
import { useState } from "react";
import API from "../api";
import { Folder, GitBranch, Plus, Sparkles } from "lucide-react";
import { useNavigate } from "react-router-dom";

export default function Dashboard() {
  const [name, setName] = useState("");
  const [repo, setRepo] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

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

      // redirect to query page
      navigate(`/query/${projectId}`);

    } catch (e) {
      alert(e.response?.data?.message || "Failed to create project");
    } finally {
      setLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      createProject();
    }
  };

  return (
    <div className="min-h-screen bg-black">
      <div className="max-w-4xl mx-auto p-6">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <Sparkles className="text-blue-500" size={28} />
            <h1 className="text-3xl font-bold text-white">Dashboard</h1>
          </div>
          <p className="text-gray-400">Create a new project to start analyzing your codebase</p>
        </div>

        {/* Create Project Card */}
        <div className="bg-gradient-to-b from-gray-900 to-black border border-gray-800 rounded-2xl shadow-2xl p-8">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-blue-500 to-cyan-500 flex items-center justify-center">
              <Plus className="text-white" size={20} />
            </div>
            <h2 className="text-xl font-semibold text-white">New Project</h2>
          </div>

          <div className="space-y-5">
            {/* Project Name Input */}
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">
                Project Name
              </label>
              <div className="relative">
                <Folder className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-500" size={18} />
                <input
                  type="text"
                  id="projectName"
                  name="projectName"
                  autoComplete="off"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  onKeyPress={handleKeyPress}
                  className="w-full pl-12 pr-4 py-3.5 bg-black border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-gray-600 transition"
                  placeholder="My Awesome Project"
                />
              </div>
            </div>

            {/* Repository URL Input */}
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">
                Repository URL
              </label>
              <div className="relative">
                <GitBranch className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-500" size={18} />
                <input
                  type="text"
                  id="repoUrl"
                  name="repoUrl"
                  autoComplete="off"
                  value={repo}
                  onChange={(e) => setRepo(e.target.value)}
                  onKeyPress={handleKeyPress}
                  className="w-full pl-12 pr-4 py-3.5 bg-black border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-gray-600 transition"
                  placeholder="https://github.com/username/repo"
                />
              </div>
              <p className="mt-2 text-xs text-gray-500">
                Enter the full URL of your GitHub repository
              </p>
            </div>

            {/* Create Button */}
            <div className="flex justify-end pt-4">
              <button
                onClick={createProject}
                disabled={loading}
                className="px-6 py-3.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-semibold transition disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {loading ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                    <span>Creating...</span>
                  </>
                ) : (
                  <>
                    <Plus size={18} />
                    <span>Create Project</span>
                  </>
                )}
              </button>
            </div>

            {/* Keyboard Shortcut Hint */}
            <div className="text-xs text-gray-500 text-center pt-2">
              Press <span className="px-2 py-1 bg-gray-900 border border-gray-800 rounded">Ctrl/⌘ + Enter</span> to create
            </div>
          </div>
        </div>

        {/* Info Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-8">
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
            <div className="text-blue-400 text-2xl font-bold mb-1">01</div>
            <h3 className="text-white font-medium mb-1">Create Project</h3>
            <p className="text-xs text-gray-500">Enter your repository details</p>
          </div>
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
            <div className="text-cyan-400 text-2xl font-bold mb-1">02</div>
            <h3 className="text-white font-medium mb-1">AI Analysis</h3>
            <p className="text-xs text-gray-500">Let AI analyze your codebase</p>
          </div>
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
            <div className="text-purple-400 text-2xl font-bold mb-1">03</div>
            <h3 className="text-white font-medium mb-1">Query & Learn</h3>
            <p className="text-xs text-gray-500">Ask questions about your code</p>
          </div>
        </div>
      </div>
    </div>
  );
}