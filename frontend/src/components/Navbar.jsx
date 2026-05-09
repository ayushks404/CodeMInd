import { useContext } from "react";
import { AuthContext } from "../context/AuthContext";
import { useNavigate } from "react-router-dom";
import API from "../api";
import { Code2, LogOut, Sparkles } from "lucide-react";




export default function Navbar() {

  const { token , logout} = useContext(AuthContext);
  const navigate = useNavigate;
  const handleLogout = async () => {
    

    try {
      
      await API.post("/auth/logout");
      
      
    } catch (err) {
      setError(err.response?.data?.message || "Logout failed");
    } finally {
      logout();
      navigate("/login");
    }
  };

  return (
    <nav className="bg-black border-b border-gray-800 backdrop-blur-xl">
      <div className="max-w-7xl mx-auto px-6 py-4">
        <div className="flex items-center justify-between">
          {/* Logo */}
          <div className="flex items-center gap-3">
            <div className="relative">
              <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-blue-500 to-cyan-500 flex items-center justify-center">
                <Code2 className="text-white" size={20} />
              </div>
              <div className="absolute -top-1 -right-1 w-4 h-4 bg-purple-500 rounded-full flex items-center justify-center">
                <Sparkles className="text-white" size={10} />
              </div>
            </div>
            <div>
              <h1 className="text-xl font-bold text-white tracking-tight">
                AI Contextual Codebase Editor
              </h1>
              <p className="text-xs text-gray-500">Intelligent codebase analysis </p>
            </div>
          </div>

          {/* Logout Button - Only shown when logged in */}
          {token && (
            <button
              onClick={handleLogout}
              className="flex items-center gap-2 px-4 py-2 bg-gray-900 hover:bg-gray-800 border border-gray-700 hover:border-gray-600 rounded-lg text-gray-300 hover:text-white transition-all group"
            >
              <LogOut size={16} className="group-hover:rotate-12 transition-transform" />
              <span className="font-medium">Logout</span>
            </button>
          )}
        </div>
      </div>
    </nav>
  );
}
