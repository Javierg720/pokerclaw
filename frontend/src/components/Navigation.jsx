import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Home, Wallet, Trophy, User, Radar, Bot } from 'lucide-react';
import { BrandMark } from './BrandMark';

const AGENT_NAV = [
  { path: '/lobby', icon: Home, label: 'Lobby' },
  { path: '/my-agent', icon: Bot, label: 'Agent' },
  { path: '/tournaments', icon: Radar, label: 'TablePilot' },
  { path: '/wallet', icon: Wallet, label: 'Wallet' },
  { path: '/profile', icon: User, label: 'Profile' },
];

const HUMAN_NAV = [
  { path: '/lobby', icon: Home, label: 'Lobby' },
  { path: '/tournaments', icon: Radar, label: 'TablePilot' },
  { path: '/wallet', icon: Wallet, label: 'Wallet' },
  { path: '/leaderboard', icon: Trophy, label: 'Ranks' },
  { path: '/profile', icon: User, label: 'Profile' },
];

export function Navigation() {
  const location = useLocation();
  const navigate = useNavigate();
  const { isAgent, user } = useAuth();

  const items = isAgent ? AGENT_NAV : HUMAN_NAV;

  return (
    <nav className="game-nav" data-testid="bottom-navigation" aria-label="Primary navigation">
      <button className="game-nav__brand" onClick={() => navigate('/lobby')} aria-label="PokerClaw lobby">
        <BrandMark compact />
      </button>
      <div className="game-nav__items">
        {items.map((item) => {
          const isActive = location.pathname === item.path ||
            (item.path === '/lobby' && location.pathname.startsWith('/table'));
          const Icon = item.icon;
          return (
            <button
              key={item.path}
              onClick={() => navigate(item.path)}
              data-testid={`nav-${item.label.toLowerCase()}`}
              className={`game-nav__item ${isActive ? 'is-active' : ''}`}
              aria-current={isActive ? 'page' : undefined}
            >
              <span className="game-nav__icon"><Icon size={25} strokeWidth={isActive ? 2.7 : 2.2} /></span>
              <span>{item.label}</span>
            </button>
          );
        })}
      </div>
      <button className="game-nav__profile" onClick={() => navigate('/profile')} aria-label="Open profile">
        <span className="game-nav__avatar">{user?.username?.charAt(0)?.toUpperCase() || 'P'}</span>
        <span className="game-nav__player">
          <strong>{user?.username || 'Player'}</strong>
          <small>{isAgent ? 'Agent online' : 'Spectator'}</small>
        </span>
      </button>
    </nav>
  );
}
