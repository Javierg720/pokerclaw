import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import api from '../lib/api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchUser = useCallback(async () => {
    const token = localStorage.getItem('pokerclaw_token');
    if (!token) {
      setLoading(false);
      return;
    }
    try {
      const res = await api.get('/auth/me');
      setUser(res.data);
    } catch (err) {
      if (err.response?.status === 401) {
        localStorage.removeItem('pokerclaw_token');
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchUser(); }, [fetchUser]);

  const login = async (email, password) => {
    const res = await api.post('/auth/login', { email, password });
    localStorage.setItem('pokerclaw_token', res.data.token);
    setUser(res.data.user);
    return res.data;
  };

  const signup = async (username, email, password, role = 'human', agentName = null) => {
    const payload = { username, email, password, role };
    if (agentName) payload.agent_name = agentName;
    const res = await api.post('/auth/signup', payload);
    localStorage.setItem('pokerclaw_token', res.data.token);
    setUser(res.data.user);
    return res.data;
  };

  const logout = () => {
    localStorage.removeItem('pokerclaw_token');
    setUser(null);
  };

  const isAgent = user?.role === 'agent';
  const isHuman = user?.role === 'human' || (!user?.role);
  const refreshUser = fetchUser;

  return (
    <AuthContext.Provider value={{ user, loading, login, signup, logout, isAgent, isHuman, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
