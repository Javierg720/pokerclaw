import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Home, Wallet, Trophy, User, Swords, Bot, Eye } from 'lucide-react';

const AGENT_NAV = [
  { path: '/lobby', icon: Home, label: 'Lobby' },
  { path: '/my-agent', icon: Bot, label: 'Agent' },
  { path: '/tournaments', icon: Swords, label: 'Tourney' },
  { path: '/wallet', icon: Wallet, label: 'Wallet' },
  { path: '/profile', icon: User, label: 'Profile' },
];

const HUMAN_NAV = [
  { path: '/lobby', icon: Home, label: 'Lobby' },
  { path: '/tournaments', icon: Swords, label: 'Tourney' },
  { path: '/wallet', icon: Wallet, label: 'Wallet' },
  { path: '/leaderboard', icon: Trophy, label: 'Ranks' },
  { path: '/profile', icon: User, label: 'Profile' },
];

export function Navigation() {
  const location = useLocation();
  const navigate = useNavigate();
  const { isAgent } = useAuth();

  const items = isAgent ? AGENT_NAV : HUMAN_NAV;

  return (
    <nav className="bottom-nav" data-testid="bottom-navigation">
      <div className="flex items-center justify-around py-2 px-4 max-w-lg mx-auto">
        {items.map((item) => {
          const isActive = location.pathname === item.path ||
            (item.path === '/lobby' && location.pathname.startsWith('/table'));
          const Icon = item.icon;
          return (
            <button
              key={item.path}
              onClick={() => navigate(item.path)}
              data-testid={`nav-${item.label.toLowerCase()}`}
              className={`flex flex-col items-center gap-1 px-4 py-1 rounded-lg transition-all duration-200 ${
                isActive
                  ? 'text-[#FF003C]'
                  : 'text-white/40 hover:text-white/70'
              }`}
            >
              <Icon size={20} strokeWidth={isActive ? 2.5 : 1.5} />
              <span className="text-[10px] font-medium tracking-wide">
                {item.label}
              </span>
              {isActive && (
                <div className="w-1 h-1 rounded-full bg-[#FF003C] mt-0.5" />
              )}
            </button>
          );
        })}
      </div>
    </nav>
  );
}
