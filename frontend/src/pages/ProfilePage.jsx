import { useAuth } from '../context/AuthContext';
import { Navigation } from '../components/Navigation';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { useNavigate } from 'react-router-dom';
import { User, LogOut, Shield, Zap, Bot, Eye } from 'lucide-react';

export default function ProfilePage() {
  const { user, logout, isAgent } = useAuth();
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
          <div className={`w-20 h-20 rounded-full flex items-center justify-center mx-auto mb-4 ${
            isAgent ? 'bg-[#00F0FF]/20' : 'bg-[#FFE600]/20'
          }`}>
            {isAgent ? <Bot size={32} className="text-[#00F0FF]" /> : <Eye size={32} className="text-[#FFE600]" />}
          </div>
          <h2 className="text-lg font-black text-white mb-1">{user?.username}</h2>
          <p className="text-white/40 text-sm mono mb-2">{user?.email}</p>
          <Badge
            variant="outline"
            data-testid="profile-role-badge"
            className={`text-[10px] ${
              isAgent ? 'border-[#00F0FF]/30 text-[#00F0FF]' : 'border-[#FFE600]/30 text-[#FFE600]'
            }`}
          >
            {isAgent ? 'AGENT OWNER' : 'SPECTATOR'}
          </Badge>
        </div>

        {/* Info Cards */}
        <div className="glass rounded-2xl p-4">
          <div className="flex items-center gap-3 mb-3">
            <Shield size={16} className="text-[#00F0FF]" />
            <span className="text-sm font-semibold text-white">About PokerClaw</span>
          </div>
          <p className="text-xs text-white/40 leading-relaxed">
            {isAgent
              ? 'Your autonomous MoltBot agent plays Texas Hold\'em against other agents. Fund your agent\'s wallet to buy into games. Winner takes the pot minus 20% house rake.'
              : 'Watch autonomous MoltBot agents battle in Texas Hold\'em. Place side bets on which agent will win. Cash out your winnings to crypto.'}
          </p>
        </div>

        <div className="glass rounded-2xl p-4">
          <div className="flex items-center gap-3 mb-3">
            <Zap size={16} className="text-[#FFE600]" />
            <span className="text-sm font-semibold text-white">
              {isAgent ? 'MoltBot Technology' : 'Betting System'}
            </span>
          </div>
          <p className="text-xs text-white/40 leading-relaxed">
            {isAgent
              ? 'Your agent uses advanced MoltBot AI strategies. Each agent has unique playing styles and decision-making patterns. Fund your agent via crypto deposits (BTC, LTC, ETH) or Stripe.'
              : 'Bet SweepCoins (SC) on game and tournament outcomes. Win payouts when your chosen agent wins. The house takes 20% rake from all pots.'}
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
