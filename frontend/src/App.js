import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { Toaster } from "./components/ui/sonner";
import AuthPage from "./pages/AuthPage";
import LobbyPage from "./pages/LobbyPage";
import TablePage from "./pages/TablePage";
import WalletPage from "./pages/WalletPage";
import LeaderboardPage from "./pages/LeaderboardPage";
import ProfilePage from "./pages/ProfilePage";
import TournamentPage from "./pages/TournamentPage";

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-[#FF003C] text-sm neon-pulse">Loading...</div>
      </div>
    );
  }
  return user ? children : <Navigate to="/" replace />;
}

function AppRoutes() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-[#FF003C] text-sm neon-pulse">Loading...</div>
      </div>
    );
  }

  return (
    <Routes>
      <Route
        path="/"
        element={user ? <Navigate to="/lobby" replace /> : <AuthPage />}
      />
      <Route
        path="/lobby"
        element={<ProtectedRoute><LobbyPage /></ProtectedRoute>}
      />
      <Route
        path="/table/:tableId"
        element={<ProtectedRoute><TablePage /></ProtectedRoute>}
      />
      <Route
        path="/wallet"
        element={<ProtectedRoute><WalletPage /></ProtectedRoute>}
      />
      <Route
        path="/leaderboard"
        element={<ProtectedRoute><LeaderboardPage /></ProtectedRoute>}
      />
      <Route
        path="/tournaments"
        element={<ProtectedRoute><TournamentPage /></ProtectedRoute>}
      />
      <Route
        path="/profile"
        element={<ProtectedRoute><ProfilePage /></ProtectedRoute>}
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <div className="App dark">
          <AppRoutes />
          <Toaster position="top-center" richColors />
        </div>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
