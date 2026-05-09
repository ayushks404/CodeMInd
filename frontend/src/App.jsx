import { useContext } from 'react';

import Navbar from './components/Navbar'
import Register from "./pages/register"
import Login from "./pages/login"
import Dashboard from "./pages/dashboard";
import Query from "./pages/query";
import { BrowserRouter, Routes, Route, Navigate  } from "react-router-dom";
import { AuthContext } from './context/AuthContext';

function ProtectedRoute({ children }) {
    const { token } = useContext(AuthContext); 
    if (!token) {
      
      return <Navigate to="/" replace />;
    }
      return children;
  }



export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-100">
        <Navbar />
        <Routes>
          <Route path="/" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/dashboard" element={
            <ProtectedRoute>
              <Dashboard />
            </ProtectedRoute>
          } />


          <Route path="/query/:projectId" element={
            <ProtectedRoute>
              <Query />
            </ProtectedRoute>
          } />


        </Routes>
      </div>
    </BrowserRouter>
  );
}

