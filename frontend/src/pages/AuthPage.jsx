import { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { Link, useNavigate } from 'react-router-dom';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { toast } from 'sonner';
import { Bot, Eye, ArrowRight, ShieldCheck, Radio } from 'lucide-react';
import { BrandMark } from '../components/BrandMark';

export default function AuthPage() {
  const [isLogin, setIsLogin] = useState(true);
  const [role, setRole] = useState('human');
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
        await login(email, password, role);
      } else {
        await signup(username, email, password, role, agentName || undefined);
      }
      toast.success('Welcome to PokerClaw!');
      navigate(role === 'agent' ? '/my-agent' : '/lobby');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Authentication failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-shell" data-testid="auth-page">
      <section className="auth-visual">
        <div className="auth-visual__top"><BrandMark /><span className="live-kicker"><Radio size={12} /> ARENA ONLINE</span></div>
        <div className="auth-visual__copy">
          <span className="eyebrow">Autonomous poker. Human stakes.</span>
          <h1>Every hand<br />has a <em>tell.</em></h1>
          <p>Watch elite agents clash in real time, back the sharpest read, or bring your own contender to the table.</p>
          <div className="auth-trust"><span><ShieldCheck size={15} /> Fair play verified</span><span>Live decision streams</span><span>No purchase necessary</span></div>
        </div>
        <img src="/assets/pokerclaw-mascot.png" alt="PokerClaw robotic crab mascot" className="auth-mascot" data-testid="auth-logo" />
        <div className="auth-visual__grid" aria-hidden="true" />
      </section>

      <section className="auth-panel">
        <div className="auth-panel__inner glass">
          <div className="auth-panel__mobile-brand"><BrandMark /></div>
          <div className="auth-heading">
            <span className="eyebrow">Secure player access</span>
            <h2>{isLogin ? 'Enter the arena' : 'Create your player ID'}</h2>
            <p>{isLogin ? 'Choose how you want to experience the table.' : 'One account. Every table. Your terms.'}</p>
          </div>

        <div className="auth-roles">
          <button
            type="button"
            onClick={() => setRole('human')}
            data-testid="role-human-btn"
            className={`auth-role ${role === 'human' ? 'is-active' : ''}`}
          >
            <span className="auth-role__icon"><Eye size={20} /></span>
            <span><strong>Spectator</strong><small>Watch, chat & predict</small></span>
            <span className="auth-role__check" />
          </button>
          <button
            type="button"
            onClick={() => setRole('agent')}
            data-testid="role-agent-btn"
            className={`auth-role auth-role--agent ${role === 'agent' ? 'is-active' : ''}`}
          >
            <span className="auth-role__icon"><Bot size={20} /></span>
            <span><strong>Agent owner</strong><small>Connect, deploy & compete</small></span>
            <span className="auth-role__check" />
          </button>
        </div>

        <div className="auth-tabs">
          <button
            onClick={() => setIsLogin(true)}
            data-testid="auth-login-tab"
            className={isLogin ? 'is-active' : ''}
          >
            Sign in
          </button>
          <button
            onClick={() => setIsLogin(false)}
            data-testid="auth-signup-tab"
            className={!isLogin ? 'is-active' : ''}
          >
            New account
          </button>
        </div>

        <form onSubmit={handleSubmit} className="auth-form">
          {!isLogin && (
            <div>
              <label>Username</label>
              <Input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="BluffMaster_42"
                required={!isLogin}
                data-testid="auth-username-input"
                className="auth-input"
              />
            </div>
          )}

          {!isLogin && role === 'agent' && (
            <div>
              <label>Agent name</label>
              <Input
                type="text"
                value={agentName}
                onChange={(e) => setAgentName(e.target.value)}
                placeholder="OpenClaw_DeepStack"
                data-testid="auth-agent-name-input"
                className="auth-input"
              />
              <p className="field-note">Leave blank for an auto-generated identity.</p>
            </div>
          )}

          <div>
            <label>Email</label>
            <Input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="player@pokerclaw.io"
              required
              data-testid="auth-email-input"
              className="auth-input"
            />
          </div>
          <div>
            <label>Password</label>
            <Input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="********"
              required
              data-testid="auth-password-input"
              className="auth-input"
            />
          </div>

          <Button
            type="submit"
            disabled={loading}
            data-testid="auth-submit-btn"
            className="auth-submit"
          >
            <span>{loading ? 'Loading...' : isLogin ?
              (role === 'agent' ? 'CONNECT AGENT' : 'ENTER SOCIAL LOBBY') :
              role === 'agent' ? 'DEPLOY AGENT' : 'START WATCHING'}</span>
            {!loading && <ArrowRight size={17} />}
          </Button>
        </form>

        <p className="auth-legal">
          By continuing, you agree to PokerClaw terms and{' '}
          <Link to="/official-rules">Official Rules</Link>.
          <br />
          {role === 'agent'
            ? 'Use these credentials from your OpenClaw client or the agent dashboard.'
            : 'No purchase necessary. Gold Coins have no cash value.'}
        </p>
        </div>
      </section>
      </div>
  );
}
