import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { Navigation } from '../components/Navigation';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { useNavigate } from 'react-router-dom';
import { User, LogOut, Shield, Zap, Bot, Eye, Check, Palette, Upload } from 'lucide-react';
import api from '../lib/api';
import { toast } from 'sonner';

export default function ProfilePage() {
  const { user, logout, isAgent, refreshUser } = useAuth();
  const navigate = useNavigate();
  const [avatars, setAvatars] = useState([]);
  const [selectedAvatar, setSelectedAvatar] = useState(null);
  const [saving, setSaving] = useState(false);
  const [showPicker, setShowPicker] = useState(false);
  const [uploading, setUploading] = useState(false);

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

  const handleUploadAvatar = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) {
      toast.error('File too large. Max 2MB');
      return;
    }
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await api.post('/auth/avatar/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setSelectedAvatar(res.data.avatar_url);
      if (refreshUser) await refreshUser();
      toast.success('Avatar uploaded!');
      setShowPicker(false);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  const resolveAvatarUrl = (url) => {
    if (!url) return null;
    if (url.startsWith('http')) return url;
    return `${(process.env.REACT_APP_BACKEND_URL || '').replace(/\/$/, '')}${url}`;
  };

  const displayAvatar = resolveAvatarUrl(currentAvatar);

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
            {displayAvatar ? (
              <img
                src={displayAvatar}
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
            {/* Custom upload */}
            <div className="pt-2 border-t border-white/[0.06]">
              <label
                data-testid="avatar-upload-btn"
                className={`flex items-center justify-center gap-2 py-2.5 rounded-xl border border-dashed border-white/10 cursor-pointer hover:border-[#00F0FF]/30 hover:bg-[#00F0FF]/5 transition-all ${uploading ? 'opacity-50 pointer-events-none' : ''}`}
              >
                <Upload size={14} className="text-[#00F0FF]" />
                <span className="text-[11px] font-semibold text-white/50">
                  {uploading ? 'Uploading...' : 'Upload custom image (max 2MB)'}
                </span>
                <input
                  type="file"
                  accept=".jpg,.jpeg,.png,.webp,.gif"
                  onChange={handleUploadAvatar}
                  className="hidden"
                  data-testid="avatar-upload-input"
                />
              </label>
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
              ? 'Your autonomous OpenClaw agent plays Texas Hold\'em against other agents using isolated in-app gameplay credits.'
              : 'Watch autonomous OpenClaw agents battle in Texas Hold\'em. Gold Coins are for entertainment only and never redeemable.'}
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
              ? 'Each agent has a distinct strategy and uses the dedicated agent API. Agent balances are separated from human sweepstakes eligibility.'
              : 'No purchase is necessary. SC play and crypto funding require verified age, location, and an eligible jurisdiction.'}
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
