import React, { createContext, useState, useContext, useEffect } from "react";

export const AuthContext = createContext(null);

const STORAGE_KEY = "cp_token";

// JWT ko decode karne ka helper — base64 decode karta hai
function decodeToken(token) {
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    return { _id: payload.id, id: payload.id };
  } catch {
    return null;
  }
}

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem(STORAGE_KEY));
  const [user,  setUser]  = useState(() => {
    const t = localStorage.getItem(STORAGE_KEY);
    return t ? decodeToken(t) : null;
  });

  useEffect(() => {
    if (token) {
      localStorage.setItem(STORAGE_KEY, token);
      setUser(decodeToken(token));
    } else {
      localStorage.removeItem(STORAGE_KEY);
      setUser(null);
    }
  }, [token]);

  const login  = (newToken) => setToken(newToken);
  const logout = () => setToken(null);

  return (
    <AuthContext.Provider value={{ token, user, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

// Convenience hook — import { useAuth } from "../context/AuthContext"
export function useAuth() {
  return useContext(AuthContext);
}