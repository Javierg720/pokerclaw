import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Slider } from '../components/ui/slider';
import { Badge } from '../components/ui/badge';
import { toast } from 'sonner';
import { TrendingUp, Zap, Users, Trophy } from 'lucide-react';
import api from '../lib/api';
import { sounds } from '../lib/sounds';

export function BettingPanel({ game, onBetPlaced }) {
  const { isHuman } = useAuth();
  const [selectedAgent, setSelectedAgent] = useState(null);
  const [betAmount, setBetAmount] = useState([50]);
  const [currency, setCurrency] = useState('gc');
  const [placing, setPlacing] = useState(false);
  const [odds, setOdds] = useState(null);
  const [myBets, setMyBets] = useState([]);

  const fetchOdds = useCallback(async () => {
    if (!game?.id) return;
    try {
      const [oddsRes, betsRes] = await Promise.all([
        api.get(`/bets/game/${game.id}/odds?currency=${currency}`),
        api.get('/bets/my-bets'),
      ]);
      setOdds(oddsRes.data);
      setMyBets(betsRes.data.filter(b => b.game_id === game.id));
    } catch {
      // silent
    }
  }, [game?.id, currency]);

  useEffect(() => {
    fetchOdds();
    const interval = setInterval(fetchOdds, 5000);
    return () => clearInterval(interval);
  }, [fetchOdds]);

  const activePlayers = game.players?.filter((p) => !p.folded) || [];

  const placeBet = async () => {
    if (!selectedAgent) {
      toast.error('Select an agent to bet on');
      return;
    }
    setPlacing(true);
    try {
      await api.post('/bets', {
        game_id: game.id,
        agent_id: selectedAgent,
        amount: betAmount[0],
        currency,
      });
      sounds.betPlaced();
      toast.success(`Bet placed: ${betAmount[0]} ${currency.toUpperCase()}`);
      setSelectedAgent(null);
      fetchOdds();
      onBetPlaced?.();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Bet failed');
    } finally {
      setPlacing(false);
    }
  };

  const selectedOdds = odds?.odds?.find(o => o.agent_id === selectedAgent);
  const potentialWin = selectedOdds ? Math.floor(betAmount[0] * selectedOdds.multiplier) : 0;

  return (
    <div className="glass rounded-2xl p-4 space-y-3" data-testid="betting-panel">
      {/* Header with pool info */}
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-bold text-white/60 uppercase tracking-widest flex items-center gap-1.5">
          <TrendingUp size={12} className="text-[#FFE600]" />
          {isHuman ? 'BET ON WINNER' : 'SIDE BET'}
        </h3>
        {odds && odds.total_pool > 0 && (
          <Badge variant="outline" className="text-[9px] border-[#FFE600]/20 text-[#FFE600]" data-testid="bet-pool-badge">
            <Users size={8} className="mr-1" />
            {odds.total_bets} bets / {odds.total_pool} {currency.toUpperCase()} pool
          </Badge>
        )}
      </div>

      {/* Live Odds - Agent Selection */}
      <div className="space-y-1.5">
        {activePlayers.map((player) => {
          const agentOdds = odds?.odds?.find(o => o.agent_id === player.agent_id);
          const isSelected = selectedAgent === player.agent_id;
          const myBet = myBets.find(b => b.agent_id === player.agent_id && b.status === 'pending');

          return (
            <button
              key={player.agent_id}
              onClick={() => setSelectedAgent(player.agent_id)}
              data-testid={`bet-agent-${player.agent_id}`}
              className={`w-full rounded-xl p-2.5 text-left transition-all border ${
                isSelected
                  ? 'border-[#FF003C]/50 bg-[#FF003C]/10'
                  : 'border-white/5 bg-white/[0.02] hover:border-white/10'
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <img
                    src={player.avatar_url}
                    alt={player.agent_name}
                    className="w-7 h-7 rounded-full object-cover"
                  />
                  <div>
                    <span className="text-xs font-bold text-white block">{player.agent_name}</span>
                    {myBet && (
                      <span className="text-[8px] text-[#00F0FF]/60 mono">You bet {myBet.amount} {myBet.currency?.toUpperCase()}</span>
                    )}
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-xs font-black text-[#FFE600] mono" data-testid={`odds-multiplier-${player.agent_id}`}>
                    {agentOdds ? `${agentOdds.multiplier}x` : '--'}
                  </div>
                  {agentOdds && agentOdds.pct > 0 && (
                    <div className="text-[8px] text-white/20 mono">{agentOdds.pct}% pool</div>
                  )}
                </div>
              </div>

              {/* Odds bar */}
              {agentOdds && odds?.total_pool > 0 && (
                <div className="mt-1.5 h-0.5 rounded-full bg-white/[0.05] overflow-hidden">
                  <div
                    className="h-full rounded-full bg-[#FFE600]/40 transition-all"
                    style={{ width: `${Math.max(agentOdds.pct, 2)}%` }}
                  />
                </div>
              )}
            </button>
          );
        })}
      </div>

      {/* Amount Slider */}
      <div>
        <div className="grid grid-cols-2 gap-2 mb-3">
          <button
            type="button"
            onClick={() => setCurrency('gc')}
            className={`rounded-lg py-2 text-[10px] font-bold border ${currency === 'gc' ? 'border-[#FFE600]/50 bg-[#FFE600]/10 text-[#FFE600]' : 'border-white/5 text-white/30'}`}
          >
            GOLD COINS
          </button>
          <button
            type="button"
            onClick={() => setCurrency('sc')}
            className={`rounded-lg py-2 text-[10px] font-bold border ${currency === 'sc' ? 'border-[#00F0FF]/50 bg-[#00F0FF]/10 text-[#00F0FF]' : 'border-white/5 text-white/30'}`}
          >
            SWEEPSTAKES COINS
          </button>
        </div>
        <div className="flex justify-between text-xs mb-2">
          <span className="text-white/40">Bet Amount</span>
          <span className={`font-bold mono ${currency === 'gc' ? 'text-[#FFE600]' : 'text-[#00F0FF]'}`}>
            {betAmount[0]} {currency.toUpperCase()}
          </span>
        </div>
        <Slider
          value={betAmount}
          onValueChange={setBetAmount}
          min={10}
          max={1000}
          step={10}
          className="w-full"
          data-testid="bet-slider"
        />
        <div className="flex justify-between text-[9px] text-white/15 mt-1 mono">
          <span>10 {currency.toUpperCase()}</span>
          <span>1,000 {currency.toUpperCase()}</span>
        </div>
      </div>

      {/* Potential Win Display */}
      {selectedAgent && potentialWin > 0 && (
        <div className="flex items-center justify-center gap-2 py-1.5 rounded-lg bg-[#FFE600]/5 border border-[#FFE600]/10" data-testid="potential-win">
          <Trophy size={12} className="text-[#FFE600]" />
          <span className="text-xs text-white/50">Win</span>
          <span className="text-sm font-black text-[#FFE600] mono">{potentialWin} {currency.toUpperCase()}</span>
          <span className="text-[9px] text-white/20">({selectedOdds?.multiplier}x)</span>
        </div>
      )}

      <Button
        onClick={placeBet}
        disabled={!selectedAgent || placing}
        data-testid="place-bet-btn"
        className="w-full bg-[#FF003C] hover:bg-[#cc0030] text-white font-bold rounded-xl disabled:opacity-40"
      >
        <Zap size={14} className="mr-1.5" />
        {placing ? 'Placing...' : selectedAgent ? `BET ${betAmount[0]} ${currency.toUpperCase()}` : 'SELECT AN AGENT'}
      </Button>

      {/* My Bets on this game */}
      {myBets.length > 0 && (
        <div className="pt-2 border-t border-white/[0.04]">
          <p className="text-[9px] text-white/30 uppercase tracking-wider mb-1.5">Your Bets</p>
          <div className="space-y-1">
            {myBets.map(b => {
              const agent = game.players?.find(p => p.agent_id === b.agent_id);
              return (
                <div key={b.id} className="flex items-center justify-between text-[10px]" data-testid={`my-bet-${b.id}`}>
                  <span className="text-white/50">{agent?.agent_name || 'Agent'}</span>
                  <div className="flex items-center gap-2">
                    <span className="text-[#00F0FF] mono font-bold">{b.amount} {b.currency?.toUpperCase()}</span>
                    <Badge
                      variant="outline"
                      className={`text-[7px] ${
                        b.status === 'won' ? 'border-green-500/30 text-green-400' :
                        b.status === 'lost' ? 'border-red-500/30 text-red-400' :
                        'border-[#FFE600]/20 text-[#FFE600]'
                      }`}
                    >
                      {b.status === 'won' ? `WON +${b.payout}` : b.status === 'lost' ? 'LOST' : 'LIVE'}
                    </Badge>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
