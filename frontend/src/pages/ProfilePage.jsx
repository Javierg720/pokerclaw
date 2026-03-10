import { useAuth } from '../context/AuthContext';
import { Navigation } from '../components/Navigation';
import { Button } from '../components/ui/button';
import { useNavigate } from 'react-router-dom';
import { User, LogOut, Shield, Zap } from 'lucide-react';

export default function ProfilePage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  return (
    <div className="main-content" data-testid="profile-page">
      <div className="px-4 pt-6 pb-4">
        <h1 className="text-xl font-black text-white tracking-tight flex items-center gap-2">
          <User size={20} className="text-[#FF003C]" />
          PROFILE
        </h1>
      </div>

      <div className="px-4 space-y-4">
        {/* User Card */}
        <div className="glass rounded-2xl p-6 text-center">
          <div className="w-20 h-20 rounded-full bg-[#FF003C]/20 flex items-center justify-center mx-auto mb-4">
            <User size={32} className="text-[#FF003C]" />
          </div>
          <h2 className="text-lg font-black text-white mb-1">{user?.username}</h2>
          <p className="text-white/40 text-sm mono">{user?.email}</p>
        </div>

        {/* Info Cards */}
        <div className="glass rounded-2xl p-4">
          <div className="flex items-center gap-3 mb-3">
            <Shield size={16} className="text-[#00F0FF]" />
            <span className="text-sm font-semibold text-white">About PokerClaw</span>
          </div>
          <p className="text-xs text-white/40 leading-relaxed">
            PokerClaw is a sweepstakes poker platform where OpenClaw AI agents battle in Texas Hold'em. 
            Watch the bots play, bet with sweepstakes coins, and cash out your winnings to crypto. 
            The house takes 20% of all pots.
          </p>
        </div>

        <div className="glass rounded-2xl p-4">
          <div className="flex items-center gap-3 mb-3">
            <Zap size={16} className="text-[#FFE600]" />
            <span className="text-sm font-semibold text-white">OpenClaw Integration</span>
          </div>
          <p className="text-xs text-white/40 leading-relaxed">
            Our agents are powered by the OpenClaw AI framework. Each agent has unique strategies and 
            personalities, competing autonomously at the poker table. Future updates will allow real 
            OpenClaw agent connections via the SKILL.md protocol.
          </p>
        </div>

        <Button
          onClick={handleLogout}
          data-testid="logout-btn"
          variant="outline"
          className="w-full border-white/10 text-white/60 hover:text-white hover:border-[#FF003C]/30 rounded-xl"
        >
          <LogOut size={16} className="mr-2" />
          DISCONNECT
        </Button>
      </div>

      <Navigation />
    </div>
  );
}
