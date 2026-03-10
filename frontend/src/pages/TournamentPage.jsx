import { useState, useEffect, useCallback } from 'react';
import { Navigation } from '../components/Navigation';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Slider } from '../components/ui/slider';
import { Trophy, Swords, Crown, ChevronRight, Plus, Zap, Coins } from 'lucide-react';
import api from '../lib/api';
import { toast } from 'sonner';
import { sounds } from '../lib/sounds';

function BracketCard({ title, agents, winnerId, runnerUpId, status, gamePhase }) {
  return (
    <div className="glass rounded-xl p-3 w-full" data-testid={`bracket-${title}`}>
      <div className="flex items-center justify-between mb-2">
        <h4 className="text-[10px] font-bold text-white/50 uppercase tracking-widest">{title}</h4>
        <Badge
          variant="outline"
          className={`text-[8px] ${
            status === 'complete' ? 'border-[#FFE600]/30 text-[#FFE600]' :
            status === 'active' ? 'border-[#00F0FF]/30 text-[#00F0FF]' :
            'border-white/20 text-white/30'
          }`}
        >
          {status === 'complete' ? 'DONE' : status === 'active' ? (gamePhase || 'LIVE') : 'PENDING'}
        </Badge>
      </div>
      <div className="space-y-1.5">
        {agents.map((agent) => {
          const isWinner = winnerId === agent.id;
          const isRunner = runnerUpId === agent.id;
          return (
            <div
              key={agent.id}
              className={`flex items-center gap-2 px-2 py-1.5 rounded-lg transition-all ${
                isWinner ? 'bg-[#FFE600]/10 border border-[#FFE600]/20' :
                isRunner ? 'bg-[#00F0FF]/5 border border-[#00F0FF]/10' :
                status === 'complete' ? 'opacity-30' : 'bg-white/[0.02]'
              }`}
              data-testid={`bracket-agent-${agent.id}`}
            >
              <img src={agent.avatar_url} alt={agent.name} className="w-6 h-6 rounded-full object-cover" />
              <span className="text-xs font-semibold text-white flex-1 truncate">{agent.name}</span>
              {isWinner && <Crown size={12} className="text-[#FFE600]" />}
              {isRunner && <ChevronRight size={12} className="text-[#00F0FF]" />}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function TournamentPage() {
  const [tournaments, setTournaments] = useState([]);
  const [selected, setSelected] = useState(null);
  const [agents, setAgents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [advancing, setAdvancing] = useState(false);
  const [betAgent, setBetAgent] = useState(null);
  const [betAmount, setBetAmount] = useState([50]);
  const [betCurrency, setBetCurrency] = useState('gc');

  const fetchData = useCallback(async () => {
    try {
      const [tRes, aRes] = await Promise.all([
        api.get('/tournaments'),
        api.get('/agents')
      ]);
      setTournaments(tRes.data);
      setAgents(aRes.data);
      if (selected) {
        const updated = tRes.data.find(t => t.id === selected.id);
        if (updated) setSelected(updated);
      }
    } catch {
      toast.error('Failed to load tournaments');
    } finally {
      setLoading(false);
    }
  }, [selected]);

  useEffect(() => { fetchData(); }, []);

  const createTournament = async () => {
    try {
      const res = await api.post('/tournaments');
      toast.success('Tournament created!');
      setSelected(res.data);
      fetchData();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to create');
    }
  };

  const advanceRound = async () => {
    if (!selected || advancing) return;
    setAdvancing(true);
    try {
      const res = await api.post(`/tournaments/${selected.id}/advance`);
      setSelected(res.data);
      sounds.notification();
      if (res.data.status === 'complete') {
        sounds.winFanfare();
        toast.success(`${res.data.champion_name} is the champion!`);
      } else {
        toast.success(`Round advanced!`);
      }
      fetchData();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to advance');
    } finally {
      setAdvancing(false);
    }
  };

  const placeTournamentBet = async () => {
    if (!betAgent || !selected) return;
    try {
      await api.post('/tournament-bets', {
        tournament_id: selected.id,
        agent_id: betAgent,
        amount: betAmount[0],
        currency: betCurrency,
      });
      sounds.betPlaced();
      toast.success(`Bet placed on tournament winner!`);
      setBetAgent(null);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Bet failed');
    }
  };

  const getAgentById = (id) => agents.find(a => a.id === id) || { id, name: '???', avatar_url: '' };

  // Build bracket agents
  const getBracketAgents = (agentIds) => (agentIds || []).map(getAgentById);

  if (loading) {
    return (
      <div className="main-content flex items-center justify-center">
        <div className="text-white/30 neon-pulse">Loading...</div>
        <Navigation />
      </div>
    );
  }

  return (
    <div className="main-content" data-testid="tournament-page">
      <div className="px-4 pt-6 pb-4">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-black text-white tracking-tight flex items-center gap-2">
            <Swords size={20} className="text-[#FF003C]" />
            TOURNAMENTS
          </h1>
          <Button
            onClick={createTournament}
            data-testid="create-tournament-btn"
            size="sm"
            className="bg-[#FF003C] hover:bg-[#cc0030] text-white font-bold rounded-lg text-xs"
          >
            <Plus size={12} className="mr-1" /> NEW
          </Button>
        </div>
      </div>

      {!selected ? (
        /* Tournament List */
        <div className="px-4 space-y-3">
          {tournaments.length === 0 ? (
            <div className="text-center py-12">
              <Swords size={40} className="text-white/10 mx-auto mb-4" />
              <p className="text-white/30 text-sm">No tournaments yet. Create one!</p>
            </div>
          ) : (
            tournaments.map((t) => (
              <div
                key={t.id}
                onClick={() => setSelected(t)}
                className="table-card float-up"
                data-testid={`tournament-card-${t.id}`}
              >
                <div className="flex items-start justify-between mb-2">
                  <div>
                    <h3 className="text-sm font-bold text-white">{t.name}</h3>
                    <p className="text-white/30 text-[10px] mono mt-0.5">8 agents bracket</p>
                  </div>
                  <Badge
                    variant="outline"
                    className={`text-[10px] ${
                      t.status === 'complete' ? 'border-[#FFE600]/30 text-[#FFE600]' :
                      t.status === 'lobby' ? 'border-white/20 text-white/40' :
                      'border-[#00F0FF]/30 text-[#00F0FF]'
                    }`}
                  >
                    {t.status === 'complete' ? 'FINISHED' : t.status === 'lobby' ? 'OPEN' : 'LIVE'}
                  </Badge>
                </div>
                {t.champion_name && (
                  <div className="flex items-center gap-1.5 text-xs text-[#FFE600]">
                    <Crown size={12} /> {t.champion_name}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      ) : (
        /* Tournament Detail / Bracket */
        <div className="px-4 space-y-4">
          <button
            onClick={() => setSelected(null)}
            data-testid="back-to-tournaments"
            className="text-white/40 text-xs hover:text-white transition-colors"
          >
            &larr; All Tournaments
          </button>

          <div className="text-center mb-4">
            <h2 className="text-base font-black text-white">{selected.name}</h2>
            <Badge
              variant="outline"
              className={`text-[10px] mt-1 ${
                selected.status === 'complete' ? 'border-[#FFE600]/30 text-[#FFE600]' :
                'border-[#00F0FF]/30 text-[#00F0FF]'
              }`}
            >
              {selected.status?.toUpperCase()}
            </Badge>
          </div>

          {/* Bracket */}
          <div className="space-y-3">
            {/* Semi-finals */}
            <div className="grid grid-cols-2 gap-3">
              <BracketCard
                title="Semi 1"
                agents={getBracketAgents(selected.bracket?.semi_1?.agent_ids)}
                winnerId={selected.bracket?.semi_1?.winners?.[0]}
                runnerUpId={selected.bracket?.semi_1?.winners?.[1]}
                status={selected.bracket?.semi_1?.complete ? 'complete' : selected.status === 'semis' ? 'active' : 'pending'}
                gamePhase={selected.bracket?.semi_1?.game_phase}
              />
              <BracketCard
                title="Semi 2"
                agents={getBracketAgents(selected.bracket?.semi_2?.agent_ids)}
                winnerId={selected.bracket?.semi_2?.winners?.[0]}
                runnerUpId={selected.bracket?.semi_2?.winners?.[1]}
                status={selected.bracket?.semi_2?.complete ? 'complete' : selected.status === 'semis' ? 'active' : 'pending'}
                gamePhase={selected.bracket?.semi_2?.game_phase}
              />
            </div>

            {/* Connector */}
            <div className="flex justify-center">
              <div className="w-px h-6 bg-gradient-to-b from-[#00F0FF]/30 to-[#FFE600]/30" />
            </div>

            {/* Final */}
            <BracketCard
              title="FINAL"
              agents={getBracketAgents(selected.bracket?.final?.agent_ids)}
              winnerId={selected.bracket?.final?.winner}
              status={
                selected.bracket?.final?.complete ? 'complete' :
                selected.status === 'final' ? 'active' : 'pending'
              }
              gamePhase={selected.bracket?.final?.game_phase}
            />

            {/* Champion */}
            {selected.champion_name && (
              <div className="glass rounded-2xl p-5 text-center glow-gold">
                <Crown size={28} className="text-[#FFE600] mx-auto mb-2" />
                <h3 className="text-lg font-black text-[#FFE600]">{selected.champion_name}</h3>
                <p className="text-white/40 text-xs mt-1">Tournament Champion</p>
              </div>
            )}
          </div>

          {/* Advance Button */}
          {selected.status !== 'complete' && (
            <Button
              onClick={advanceRound}
              disabled={advancing}
              data-testid="advance-tournament-btn"
              className="w-full bg-[#FF003C] hover:bg-[#cc0030] text-white font-bold rounded-xl py-3 disabled:opacity-40"
            >
              {advancing ? 'Processing...' :
                selected.status === 'lobby' ? 'START TOURNAMENT' :
                'ADVANCE ROUND'}
            </Button>
          )}

          {/* Tournament Betting */}
          {selected.status !== 'complete' && (
            <div className="glass rounded-2xl p-4 space-y-3" data-testid="tournament-betting">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold text-white/60 uppercase tracking-widest">
                  Bet on Champion
                </h4>
                <div className="sweep-toggle">
                  <button
                    onClick={() => setBetCurrency('gc')}
                    className={`sweep-toggle-btn ${betCurrency === 'gc' ? 'active-gc' : ''}`}
                  >GC</button>
                  <button
                    onClick={() => setBetCurrency('sc')}
                    className={`sweep-toggle-btn ${betCurrency === 'sc' ? 'active-sc' : ''}`}
                  >SC</button>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-1.5">
                {(selected.bracket?.semi_1?.agent_ids || [])
                  .concat(selected.bracket?.semi_2?.agent_ids || [])
                  .map((aid) => {
                    const agent = getAgentById(aid);
                    return (
                      <button
                        key={aid}
                        onClick={() => setBetAgent(aid)}
                        data-testid={`tourney-bet-agent-${aid}`}
                        className={`rounded-lg p-1.5 text-left transition-all border flex items-center gap-1.5 ${
                          betAgent === aid
                            ? 'border-[#FF003C]/50 bg-[#FF003C]/10'
                            : 'border-white/5 bg-white/[0.02]'
                        }`}
                      >
                        <img src={agent.avatar_url} alt="" className="w-5 h-5 rounded-full object-cover" />
                        <span className="text-[10px] font-semibold text-white truncate">{agent.name}</span>
                      </button>
                    );
                  })}
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-white/40">Amount</span>
                <span className={`font-bold mono ${betCurrency === 'gc' ? 'text-[#FFE600]' : 'text-[#00F0FF]'}`}>
                  {betAmount[0]} {betCurrency.toUpperCase()}
                </span>
              </div>
              <Slider value={betAmount} onValueChange={setBetAmount} min={10} max={500} step={10} />
              <Button
                onClick={placeTournamentBet}
                disabled={!betAgent}
                data-testid="place-tourney-bet-btn"
                className="w-full bg-[#FF003C] hover:bg-[#cc0030] text-white font-bold rounded-xl disabled:opacity-40 text-sm"
              >
                BET {betAmount[0]} {betCurrency.toUpperCase()}
              </Button>
            </div>
          )}
        </div>
      )}

      <Navigation />
    </div>
  );
}
