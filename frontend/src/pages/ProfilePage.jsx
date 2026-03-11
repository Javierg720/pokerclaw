import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { Navigation } from '../components/Navigation';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { useNavigate } from 'react-router-dom';
import { User, LogOut, Shield, Zap, Bot, Eye, Check, Palette } from 'lucide-react';
import api from '../lib/api';
import { toast } from 'sonner';

export default function ProfilePage() {
  const { user, logout, isAgent, refreshUser } = useAuth();
  const navigate = useNavigate();
  const [avatars, setAvatars] = useState([]);
  const [selectedAvatar, setSelectedAvatar] = useState(null);
  const [saving, setSaving] = useState(false);
  const [showPicker, setShowPicker] = useState(false);

  useEffect(() => {
    api.get('/auth/avatars').then(res => setAvatars(res.data.avatars || [])).catch(() => {});
  }, []);

  const currentAvatar = selectedAvatar || user?.avatar_url;

  const handleSaveAvatar = async () => {
    if (!selectedAvatar) return;
    setSaving(true);
    try {
      await api.put('/auth/profile', { avatar_url: selectedAvatar });
      if (refreshUser) await refreshUser();
      toast.success('Avatar updated!');
      setShowPicker(false);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to update');
    } finally {
      setSaving(false);
    }
  };

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
          <div className="relative inline-block">
            {currentAvatar ? (
              <img
                src={currentAvatar}
                alt="Avatar"
                className="w-20 h-20 rounded-full object-cover mx-auto mb-2 border-2 border-white/10"
                data-testid="profile-avatar"
              />
            ) : (
              <div className={`w-20 h-20 rounded-full flex items-center justify-center mx-auto mb-2 ${
                isAgent ? 'bg-[#00F0FF]/20' : 'bg-[#FFE600]/20'
              }`}>
                {isAgent ? <Bot size={32} className="text-[#00F0FF]" /> : <Eye size={32} className="text-[#FFE600]" />}
              </div>
            )}
            <button
              onClick={() => setShowPicker(!showPicker)}
              data-testid="avatar-edit-btn"
              className="absolute -bottom-1 -right-1 w-7 h-7 rounded-full bg-[#FF003C] flex items-center justify-center shadow-lg hover:scale-110 transition-transform"
            >
              <Palette size={12} className="text-white" />
            </button>
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

        {/* Avatar Picker */}
        {showPicker && (
          <div className="glass rounded-2xl p-4 space-y-3" data-testid="avatar-picker">
            <div className="flex items-center justify-between">
              <h4 className="text-xs font-bold text-white/60 uppercase tracking-widest flex items-center gap-1.5">
                <Palette size={12} className="text-[#FF003C]" />
                CHOOSE AVATAR
              </h4>
              {selectedAvatar && (
                <Button
                  onClick={handleSaveAvatar}
                  disabled={saving}
                  data-testid="save-avatar-btn"
                  size="sm"
                  className="bg-[#FF003C] hover:bg-[#cc0030] text-white font-bold rounded-lg text-[10px] h-7 px-3"
                >
                  <Check size={10} className="mr-1" />
                  {saving ? 'Saving...' : 'SAVE'}
                </Button>
              )}
            </div>
            <div className="grid grid-cols-4 gap-2.5">
              {avatars.map((url, idx) => (
                <button
                  key={idx}
                  onClick={() => setSelectedAvatar(url)}
                  data-testid={`avatar-option-${idx}`}
                  className={`relative rounded-xl overflow-hidden border-2 transition-all hover:scale-105 ${
                    (selectedAvatar || user?.avatar_url) === url
                      ? 'border-[#FF003C] ring-2 ring-[#FF003C]/30 scale-105'
                      : 'border-white/[0.06] hover:border-white/20'
                  }`}
                >
                  <img
                    src={url}
                    alt={`Avatar ${idx + 1}`}
                    className="w-full aspect-square object-cover bg-[#0a0a0f]"
                  />
                  {(selectedAvatar || user?.avatar_url) === url && (
                    <div className="absolute inset-0 flex items-center justify-center bg-[#FF003C]/20">
                      <Check size={16} className="text-white" />
                    </div>
                  )}
                </button>
              ))}
            </div>
          </div>
        )}

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
