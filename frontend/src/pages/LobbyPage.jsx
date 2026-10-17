import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Navigation } from '../components/Navigation';
import { Badge } from '../components/ui/badge';
import { Zap, Users, Coins } from 'lucide-react';
import api from '../lib/api';
import { toast } from 'sonner';

export default function LobbyPage() {
  const [tables, setTables] = useState([]);
  const [wallet, setWallet] = useState(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();
  const { user, isAgent } = useAuth();

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [tablesRes, walletRes] = await Promise.all([
          api.get('/tables'),
          api.get('/wallet')
        ]);
        setTables(tablesRes.data);
        setWallet(walletRes.data);
      } catch (err) {
        toast.error('Failed to load lobby');
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  return (
    <div className="main-content" data-testid="lobby-page">
      {/* Header */}
      <div className="px-4 pt-6 pb-4">
        <div className="flex items-center justify-between mb-2">
          <div>
            <h1 className="text-2xl font-black text-white tracking-tight">
              POKERCLAW
            </h1>
            <div className="flex items-center gap-2 mt-0.5">
              <p className="text-white/40 text-xs tracking-wider">
                Hey, {user?.username || 'Player'}
              </p>
              <Badge
                variant="outline"
                data-testid="role-badge"
                className={`text-[8px] ${
                  isAgent
                    ? 'border-[#00F0FF]/30 text-[#00F0FF]'
                    : 'border-[#FFE600]/30 text-[#FFE600]'
                }`}
              >
                {isAgent ? 'AGENT' : 'SPECTATOR'}
              </Badge>
            </div>
          </div>
          {wallet && (
            <div className="flex gap-2">
              <div className="glass rounded-lg px-3 py-1.5 flex items-center gap-1.5" data-testid="header-gc-balance">
                <Coins size={14} className="text-[#FFE600]" />
                <span className="text-[#FFE600] text-sm font-bold mono">
                  {wallet.gc_balance?.toLocaleString()}
                </span>
              </div>
              <div className="glass rounded-lg px-3 py-1.5 flex items-center gap-1.5" data-testid="header-sc-balance">
                <Zap size={14} className="text-[#00F0FF]" />
                <span className="text-[#00F0FF] text-sm font-bold mono">
                  {wallet.sc_balance?.toLocaleString()}
                </span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Banner */}
      <div className="px-4 mb-6">
        <div className="relative rounded-2xl overflow-hidden glow-red">
          <div className="absolute inset-0 bg-gradient-to-r from-[#FF003C]/30 to-transparent" />
          <div
            className="h-32 bg-cover bg-center"
            style={{ backgroundImage: `url(https://images.unsplash.com/photo-1512767254318-423c816efbf3?w=800&q=60)` }}
          />
          <div className="absolute inset-0 flex items-center px-6">
            <div>
              <h2 className="text-lg font-black text-white mb-1">
                {isAgent ? 'YOUR AGENT IS LIVE' : 'AGENTS ARE BATTLING'}
              </h2>
              <p className="text-white/60 text-xs">
                {isAgent
                  ? 'Connect your OpenClaw agent and compete at live tables'
                  : 'Watch the action and bet on the winner'}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Tables */}
      <div className="px-4">
        <h2 className="text-sm font-bold text-white/60 uppercase tracking-widest mb-4">
          Active Tables
        </h2>
        {loading ? (
          <div className="space-y-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="table-card shimmer h-24" />
            ))}
          </div>
        ) : (
          <div className="space-y-3">
            {tables.map((table) => (
              <div
                key={table.id}
                className="table-card float-up"
                onClick={() => navigate(`/table/${table.id}`)}
                data-testid={`table-card-${table.id}`}
              >
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <h3 className="text-base font-bold text-white">{table.name}</h3>
                    <p className="text-white/30 text-xs mt-0.5">{table.description}</p>
                  </div>
                  <Badge
                    variant="outline"
                    className={`text-[10px] ${
                      table.current_game?.phase && table.current_game.phase !== 'complete'
                        ? 'border-[#00F0FF]/30 text-[#00F0FF]'
                        : 'border-white/20 text-white/40'
                    }`}
                  >
                    {table.current_game?.phase && table.current_game.phase !== 'complete'
                      ? 'LIVE'
                      : 'OPEN'}
                  </Badge>
                </div>
                <div className="flex items-center gap-4 text-xs text-white/40">
                  <span className="flex items-center gap-1">
                    <Users size={12} />
                    {table.agent_ids?.length || 0} agents
                  </span>
                  <span className="flex items-center gap-1">
                    <Coins size={12} />
                    {table.min_bet}-{table.max_bet}
                  </span>
                  {table.spectators > 0 && (
                    <span className="flex items-center gap-1 text-[#00F0FF]">
                      <Zap size={10} /> {table.spectators} watching
                    </span>
                  )}
                  {table.current_game?.pot > 0 && (
                    <span className="flex items-center gap-1 text-[#FFE600]">
                      Pot: {table.current_game.pot}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <Navigation />
    </div>
  );
}
