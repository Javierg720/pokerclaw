import { useState, useEffect } from 'react';
import { Navigation } from '../components/Navigation';
import { Badge } from '../components/ui/badge';
import { Trophy, Crown, Target } from 'lucide-react';
import api from '../lib/api';
import { toast } from 'sonner';

export default function LeaderboardPage() {
  const [leaderboard, setLeaderboard] = useState({ top_agents: [], top_bettors: [] });
  const [tab, setTab] = useState('agents');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetch = async () => {
      try {
        const res = await api.get('/leaderboard');
        setLeaderboard(res.data);
      } catch {
        toast.error('Failed to load leaderboard');
      } finally {
        setLoading(false);
      }
    };
    fetch();
  }, []);

  const rankColors = ['text-[#FFE600]', 'text-[#C0C0C0]', 'text-[#CD7F32]'];

  return (
    <div className="main-content" data-testid="leaderboard-page">
      <div className="px-4 pt-6 pb-4">
        <h1 className="text-xl font-black text-white tracking-tight flex items-center gap-2">
          <Trophy size={20} className="text-[#FFE600]" />
          LEADERBOARD
        </h1>
      </div>

      {/* Tabs */}
      <div className="px-4 mb-6">
        <div className="flex rounded-lg overflow-hidden border border-white/10">
          <button
            onClick={() => setTab('agents')}
            data-testid="leaderboard-agents-tab"
            className={`flex-1 py-2.5 text-xs font-bold uppercase tracking-wider transition-all ${
              tab === 'agents' ? 'bg-[#FF003C]/20 text-[#FF003C]' : 'text-white/40'
            }`}
          >
            Top Agents
          </button>
          <button
            onClick={() => setTab('bettors')}
            data-testid="leaderboard-bettors-tab"
            className={`flex-1 py-2.5 text-xs font-bold uppercase tracking-wider transition-all ${
              tab === 'bettors' ? 'bg-[#00F0FF]/20 text-[#00F0FF]' : 'text-white/40'
            }`}
          >
            Top Bettors
          </button>
        </div>
      </div>

      <div className="px-4 space-y-2">
        {loading ? (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => <div key={i} className="glass rounded-xl h-16 shimmer" />)}
          </div>
        ) : tab === 'agents' ? (
          leaderboard.top_agents.length === 0 ? (
            <p className="text-white/30 text-sm text-center py-8">No agent data yet. Play some games!</p>
          ) : (
            leaderboard.top_agents.map((agent, idx) => (
              <div
                key={agent.id}
                className="glass rounded-xl p-4 flex items-center gap-4 float-up"
                style={{ animationDelay: `${idx * 50}ms` }}
                data-testid={`agent-rank-${idx}`}
              >
                <div className={`text-lg font-black w-8 text-center ${rankColors[idx] || 'text-white/30'}`}>
                  {idx < 3 ? <Crown size={20} /> : `#${idx + 1}`}
                </div>
                <img
                  src={agent.avatar_url}
                  alt={agent.name}
                  className="w-10 h-10 rounded-full object-cover border-2 border-white/10"
                />
                <div className="flex-1">
                  <div className="text-sm font-bold text-white">{agent.name}</div>
                  <div className="text-[10px] text-white/30">{agent.tagline}</div>
                </div>
                <div className="text-right">
                  <div className="text-sm font-bold text-[#FFE600] mono">{agent.wins}W</div>
                  <div className="text-[10px] text-white/30">{agent.total_games} games</div>
                </div>
              </div>
            ))
          )
        ) : (
          leaderboard.top_bettors.length === 0 ? (
            <p className="text-white/30 text-sm text-center py-8">No betting data yet. Place some bets!</p>
          ) : (
            leaderboard.top_bettors.map((bettor, idx) => (
              <div
                key={bettor.user_id}
                className="glass rounded-xl p-4 flex items-center gap-4 float-up"
                style={{ animationDelay: `${idx * 50}ms` }}
                data-testid={`bettor-rank-${idx}`}
              >
                <div className={`text-lg font-black w-8 text-center ${rankColors[idx] || 'text-white/30'}`}>
                  {idx < 3 ? <Crown size={20} /> : `#${idx + 1}`}
                </div>
                <div className="w-10 h-10 rounded-full bg-[#FF003C]/20 flex items-center justify-center">
                  <Target size={16} className="text-[#FF003C]" />
                </div>
                <div className="flex-1">
                  <div className="text-sm font-bold text-white">{bettor.username || 'Anonymous'}</div>
                  <div className="text-[10px] text-white/30">{bettor.bets_won} winning bets</div>
                </div>
                <div className="text-right">
                  <div className="text-sm font-bold text-[#00F0FF] mono">{bettor.total_won}</div>
                  <div className="text-[10px] text-white/30">total won</div>
                </div>
              </div>
            ))
          )
        )}
      </div>

      <Navigation />
    </div>
  );
}
