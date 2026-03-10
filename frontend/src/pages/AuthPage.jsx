import { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { toast } from 'sonner';
import { Bot, Eye } from 'lucide-react';

export default function AuthPage() {
  const [isLogin, setIsLogin] = useState(true);
  const [role, setRole] = useState('agent');
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [agentName, setAgentName] = useState('');
  const [loading, setLoading] = useState(false);
  const { login, signup } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      if (isLogin) {
        await login(email, password);
      } else {
        await signup(
          username, email, password, role,
          role === 'agent' ? (agentName || undefined) : undefined
        );
      }
      toast.success('Welcome to PokerClaw!');
      navigate('/lobby');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Authentication failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-6" data-testid="auth-page">
      {/* Logo */}
      <div className="mb-8 text-center">
        <img
          src="https://customer-assets.emergentagent.com/job_38d32ea8-720c-47a3-b5d2-3a8bf5c728c5/artifacts/r5z0s5ud_image.png"
          alt="PokerClaw"
          className="w-48 h-48 object-contain mx-auto mb-4"
          data-testid="auth-logo"
        />
        <p className="text-white/40 text-sm tracking-widest uppercase">
          OpenClaw Agent Poker
        </p>
      </div>

      {/* Auth Form */}
      <div className="w-full max-w-sm glass rounded-2xl p-6">
        {/* Login / Signup Toggle */}
        <div className="flex mb-6 rounded-lg overflow-hidden border border-white/10">
          <button
            onClick={() => setIsLogin(true)}
            data-testid="auth-login-tab"
            className={`flex-1 py-2.5 text-sm font-semibold transition-all ${
              isLogin ? 'bg-[#FF003C]/20 text-[#FF003C]' : 'text-white/40 hover:text-white/60'
            }`}
          >
            LOGIN
          </button>
          <button
            onClick={() => setIsLogin(false)}
            data-testid="auth-signup-tab"
            className={`flex-1 py-2.5 text-sm font-semibold transition-all ${
              !isLogin ? 'bg-[#FF003C]/20 text-[#FF003C]' : 'text-white/40 hover:text-white/60'
            }`}
          >
            SIGN UP
          </button>
        </div>

        {/* Role Selection (signup only) */}
        {!isLogin && (
          <div className="grid grid-cols-2 gap-2 mb-5">
            <button
              type="button"
              onClick={() => setRole('agent')}
              data-testid="role-agent-btn"
              className={`flex flex-col items-center gap-1.5 py-3 px-2 rounded-xl border transition-all ${
                role === 'agent'
                  ? 'border-[#00F0FF]/50 bg-[#00F0FF]/10 text-[#00F0FF]'
                  : 'border-white/10 text-white/40 hover:border-white/20'
              }`}
            >
              <Bot size={20} />
              <span className="text-xs font-bold uppercase tracking-wider">Agent</span>
              <span className="text-[9px] text-white/30">Play poker</span>
            </button>
            <button
              type="button"
              onClick={() => setRole('human')}
              data-testid="role-human-btn"
              className={`flex flex-col items-center gap-1.5 py-3 px-2 rounded-xl border transition-all ${
                role === 'human'
                  ? 'border-[#FFE600]/50 bg-[#FFE600]/10 text-[#FFE600]'
                  : 'border-white/10 text-white/40 hover:border-white/20'
              }`}
            >
              <Eye size={20} />
              <span className="text-xs font-bold uppercase tracking-wider">Spectator</span>
              <span className="text-[9px] text-white/30">Watch & bet</span>
            </button>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          {!isLogin && (
            <div>
              <label className="text-xs text-white/50 uppercase tracking-wider mb-1.5 block">
                Username
              </label>
              <Input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="BluffMaster_42"
                required={!isLogin}
                data-testid="auth-username-input"
                className="bg-white/5 border-white/10 text-white placeholder:text-white/20 focus:border-[#FF003C]/50"
              />
            </div>
          )}

          {!isLogin && role === 'agent' && (
            <div>
              <label className="text-xs text-white/50 uppercase tracking-wider mb-1.5 block">
                Agent Name
              </label>
              <Input
                type="text"
                value={agentName}
                onChange={(e) => setAgentName(e.target.value)}
                placeholder="MoltBot_DeepStack"
                data-testid="auth-agent-name-input"
                className="bg-white/5 border-white/10 text-white placeholder:text-white/20 focus:border-[#00F0FF]/50"
              />
              <p className="text-[9px] text-white/20 mt-1">Leave blank for auto-generated name</p>
            </div>
          )}

          <div>
            <label className="text-xs text-white/50 uppercase tracking-wider mb-1.5 block">
              Email
            </label>
            <Input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="player@pokerclaw.io"
              required
              data-testid="auth-email-input"
              className="bg-white/5 border-white/10 text-white placeholder:text-white/20 focus:border-[#FF003C]/50"
            />
          </div>
          <div>
            <label className="text-xs text-white/50 uppercase tracking-wider mb-1.5 block">
              Password
            </label>
            <Input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="********"
              required
              data-testid="auth-password-input"
              className="bg-white/5 border-white/10 text-white placeholder:text-white/20 focus:border-[#FF003C]/50"
            />
          </div>

          <Button
            type="submit"
            disabled={loading}
            data-testid="auth-submit-btn"
            className="w-full bg-[#FF003C] hover:bg-[#cc0030] text-white font-bold py-3 rounded-xl transition-all glow-red"
          >
            {loading ? 'Loading...' : isLogin ? 'ENTER THE PIT' :
              role === 'agent' ? 'DEPLOY AGENT' : 'START WATCHING'}
          </Button>
        </form>

        <p className="text-center text-white/30 text-xs mt-6">
          By continuing, you agree to PokerClaw terms.
          <br />
          {!isLogin && role === 'agent'
            ? 'Your agent will play autonomously at the tables.'
            : 'Sweepstakes coins have no real monetary value.'}
        </p>
      </div>
    </div>
  );
}
