import { useState } from 'react';
import { Button } from '../components/ui/button';
import { Slider } from '../components/ui/slider';
import { toast } from 'sonner';
import api from '../lib/api';
import { sounds } from '../lib/sounds';

export function BettingPanel({ game, onBetPlaced }) {
  const [selectedAgent, setSelectedAgent] = useState(null);
  const [betAmount, setBetAmount] = useState([50]);
  const [currency, setCurrency] = useState('gc');
  const [placing, setPlacing] = useState(false);

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
      onBetPlaced?.();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Bet failed');
    } finally {
      setPlacing(false);
    }
  };

  return (
    <div className="glass rounded-2xl p-4 space-y-4" data-testid="betting-panel">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-bold text-white/60 uppercase tracking-widest">
          Place Your Bet
        </h3>
        <div className="sweep-toggle">
          <button
            onClick={() => setCurrency('gc')}
            data-testid="bet-gc-toggle"
            className={`sweep-toggle-btn ${currency === 'gc' ? 'active-gc' : ''}`}
          >
            GC
          </button>
          <button
            onClick={() => setCurrency('sc')}
            data-testid="bet-sc-toggle"
            className={`sweep-toggle-btn ${currency === 'sc' ? 'active-sc' : ''}`}
          >
            SC
          </button>
        </div>
      </div>

      {/* Agent Selection */}
      <div className="grid grid-cols-2 gap-2">
        {activePlayers.map((player) => (
          <button
            key={player.agent_id}
            onClick={() => setSelectedAgent(player.agent_id)}
            data-testid={`bet-agent-${player.agent_id}`}
            className={`rounded-lg p-2 text-left transition-all border ${
              selectedAgent === player.agent_id
                ? 'border-[#FF003C]/50 bg-[#FF003C]/10'
                : 'border-white/5 bg-white/[0.02] hover:border-white/10'
            }`}
          >
            <div className="flex items-center gap-2">
              <img
                src={player.avatar_url}
                alt={player.agent_name}
                className="w-6 h-6 rounded-full object-cover"
              />
              <span className="text-xs font-semibold text-white truncate">
                {player.agent_name}
              </span>
            </div>
          </button>
        ))}
      </div>

      {/* Amount Slider */}
      <div>
        <div className="flex justify-between text-xs mb-2">
          <span className="text-white/40">Amount</span>
          <span className={`font-bold mono ${currency === 'gc' ? 'text-[#FFE600]' : 'text-[#00F0FF]'}`}>
            {betAmount[0]} {currency.toUpperCase()}
          </span>
        </div>
        <Slider
          value={betAmount}
          onValueChange={setBetAmount}
          min={10}
          max={500}
          step={10}
          className="w-full"
          data-testid="bet-slider"
        />
      </div>

      <Button
        onClick={placeBet}
        disabled={!selectedAgent || placing}
        data-testid="place-bet-btn"
        className="w-full bg-[#FF003C] hover:bg-[#cc0030] text-white font-bold rounded-xl disabled:opacity-40"
      >
        {placing ? 'Placing...' : `BET ${betAmount[0]} ${currency.toUpperCase()}`}
      </Button>
    </div>
  );
}
