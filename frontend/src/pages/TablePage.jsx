import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { PlayingCard } from '../components/PlayingCard';
import { BettingPanel } from '../components/BettingPanel';
import { Navigation } from '../components/Navigation';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { ArrowLeft, Play, SkipForward, Zap, Crown } from 'lucide-react';
import api from '../lib/api';
import { toast } from 'sonner';

const PHASE_LABELS = {
  waiting: 'Waiting',
  preflop: 'Pre-Flop',
  flop: 'Flop',
  turn: 'Turn',
  river: 'River',
  showdown: 'Showdown',
  complete: 'Complete',
};

export default function TablePage() {
  const { tableId } = useParams();
  const navigate = useNavigate();
  const [table, setTable] = useState(null);
  const [game, setGame] = useState(null);
  const [autoPlay, setAutoPlay] = useState(false);
  const [advancing, setAdvancing] = useState(false);
  const [actions, setActions] = useState([]);

  const fetchTable = useCallback(async () => {
    try {
      const res = await api.get(`/tables/${tableId}`);
      setTable(res.data);
      if (res.data.current_game) {
        setGame(res.data.current_game);
        setActions(res.data.current_game.actions_log || []);
      }
    } catch {
      toast.error('Failed to load table');
    }
  }, [tableId]);

  useEffect(() => { fetchTable(); }, [fetchTable]);

  const startGame = async () => {
    try {
      const res = await api.post(`/tables/${tableId}/start-game`);
      setGame(res.data);
      setActions([]);
      toast.success('Game started!');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to start game');
    }
  };

  const advanceGame = useCallback(async () => {
    if (!game || advancing || game.phase === 'complete') return;
    setAdvancing(true);
    try {
      const res = await api.post(`/games/${game.id}/advance`);
      setGame(res.data);
      setActions(res.data.actions_log || []);
      if (res.data.phase === 'showdown' || res.data.phase === 'complete') {
        setAutoPlay(false);
        if (res.data.winner_name) {
          toast.success(`${res.data.winner_name} wins with ${res.data.winning_hand}!`);
        }
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to advance');
      setAutoPlay(false);
    } finally {
      setAdvancing(false);
    }
  }, [game, advancing]);

  useEffect(() => {
    if (!autoPlay || !game || game.phase === 'complete' || game.phase === 'showdown') return;
    const timer = setTimeout(advanceGame, 2500);
    return () => clearTimeout(timer);
  }, [autoPlay, game, advanceGame]);

  const canBet = game && !['showdown', 'complete', 'waiting'].includes(game.phase);
  const showCards = game && ['showdown', 'complete'].includes(game.phase);
  const lastActions = actions.slice(-6);

  return (
    <div className="main-content" data-testid="table-page">
      {/* Header */}
      <div className="flex items-center justify-between px-4 pt-4 pb-2">
        <button onClick={() => navigate('/lobby')} data-testid="back-to-lobby" className="text-white/50 hover:text-white transition-colors">
          <ArrowLeft size={20} />
        </button>
        <div className="text-center">
          <h2 className="text-sm font-bold text-white">{table?.name || 'Loading...'}</h2>
          {game && (
            <Badge variant="outline" className="text-[10px] mt-1 border-[#FF003C]/30 text-[#FF003C]">
              {PHASE_LABELS[game.phase] || game.phase}
            </Badge>
          )}
        </div>
        <div className="w-5" />
      </div>

      {!game || game.phase === 'complete' ? (
        /* No active game */
        <div className="flex flex-col items-center justify-center px-6 py-20">
          {game?.phase === 'complete' && game.winner_name && (
            <div className="glass rounded-2xl p-6 mb-6 text-center w-full max-w-sm glow-gold">
              <Crown className="text-[#FFE600] mx-auto mb-2" size={32} />
              <h3 className="text-lg font-black text-[#FFE600] mb-1">{game.winner_name}</h3>
              <p className="text-white/50 text-sm">{game.winning_hand}</p>
              <div className="flex justify-center gap-4 mt-4 text-xs">
                <div>
                  <span className="text-white/40">Pot</span>
                  <span className="text-[#FFE600] font-bold ml-1">{game.pot}</span>
                </div>
                <div>
                  <span className="text-white/40">Rake</span>
                  <span className="text-[#FF003C] font-bold ml-1">{game.house_rake}</span>
                </div>
              </div>
            </div>
          )}
          <Button
            onClick={startGame}
            data-testid="start-game-btn"
            className="bg-[#FF003C] hover:bg-[#cc0030] text-white font-bold px-8 py-3 rounded-xl glow-red"
          >
            <Play size={16} className="mr-2" />
            {game?.phase === 'complete' ? 'NEW HAND' : 'START GAME'}
          </Button>
        </div>
      ) : (
        /* Active game */
        <div className="px-4 space-y-4">
          {/* Pot Display */}
          <div className="text-center py-2">
            <span className="text-white/40 text-xs uppercase tracking-widest">Pot</span>
            <div className="text-2xl font-black text-[#FFE600] text-glow-gold mono" data-testid="pot-display">
              {game.pot}
            </div>
          </div>

          {/* Community Cards */}
          <div className="flex justify-center gap-2 min-h-[80px]" data-testid="community-cards">
            {[0, 1, 2, 3, 4].map((i) => (
              <div key={i}>
                {game.community_cards?.[i] ? (
                  <PlayingCard card={game.community_cards[i]} size="md" delay={i * 100} />
                ) : (
                  <div className="w-14 h-20 rounded-md border border-white/5 bg-white/[0.02]" />
                )}
              </div>
            ))}
          </div>

          {/* Agents */}
          <div className="grid grid-cols-2 gap-3" data-testid="agents-grid">
            {game.players?.map((player, idx) => {
              const isWinner = game.phase === 'showdown' && game.winner_id === player.agent_id;
              const ringClass = player.folded ? 'agent-ring-folded' : isWinner ? 'agent-ring-winner' : 'agent-ring-active';
              return (
                <div
                  key={player.agent_id}
                  className={`glass rounded-xl p-3 transition-all ${
                    player.folded ? 'opacity-40' : ''
                  } ${isWinner ? 'glow-gold' : ''}`}
                  data-testid={`agent-card-${player.agent_id}`}
                >
                  <div className="flex items-center gap-2 mb-2">
                    <div className={`agent-ring ${ringClass}`}>
                      <img
                        src={player.avatar_url}
                        alt={player.agent_name}
                        className="w-8 h-8 rounded-full object-cover"
                      />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-xs font-bold text-white truncate">
                        {player.agent_name}
                      </div>
                      <div className="text-[10px] text-white/30 mono">
                        {player.chips} chips
                      </div>
                    </div>
                    {isWinner && <Crown size={14} className="text-[#FFE600]" />}
                  </div>

                  {/* Hole cards */}
                  <div className="flex gap-1">
                    {showCards && player.hole_cards?.[0] ? (
                      <>
                        <PlayingCard card={player.hole_cards[0]} size="sm" delay={idx * 50} />
                        <PlayingCard card={player.hole_cards[1]} size="sm" delay={idx * 50 + 50} />
                      </>
                    ) : (
                      <>
                        <PlayingCard card={null} size="sm" delay={0} />
                        <PlayingCard card={null} size="sm" delay={50} />
                      </>
                    )}
                  </div>

                  {/* Last action */}
                  {!player.folded && player.total_bet > 0 && (
                    <div className="mt-2 text-[10px] text-white/40">
                      Bet: <span className="text-[#FFE600] font-bold">{player.total_bet}</span>
                    </div>
                  )}
                  {player.folded && (
                    <div className="action-badge action-fold mt-2 inline-block">FOLDED</div>
                  )}
                  {showCards && player.hand_name && (
                    <div className="text-[10px] text-[#00F0FF] font-semibold mt-1">
                      {player.hand_name}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Actions Log */}
          {lastActions.length > 0 && (
            <div className="glass rounded-xl p-3" data-testid="actions-log">
              <h4 className="text-[10px] text-white/30 uppercase tracking-widest mb-2">Actions</h4>
              <div className="space-y-1">
                {lastActions.map((a, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs">
                    <span className="text-white/60 truncate flex-1">{a.agent_name}</span>
                    <span className={`action-badge action-${a.action}`}>
                      {a.action} {a.amount > 0 ? a.amount : ''}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Controls */}
          <div className="flex items-center gap-3">
            <Button
              onClick={advanceGame}
              disabled={advancing || game.phase === 'showdown'}
              data-testid="advance-btn"
              className="flex-1 bg-[#FF003C] hover:bg-[#cc0030] text-white font-bold rounded-xl disabled:opacity-40"
            >
              <SkipForward size={14} className="mr-1" />
              {advancing ? 'Dealing...' : 'NEXT'}
            </Button>
            <Button
              onClick={() => setAutoPlay(!autoPlay)}
              data-testid="auto-play-btn"
              variant="outline"
              className={`rounded-xl border-white/10 ${
                autoPlay ? 'bg-[#00F0FF]/10 text-[#00F0FF] border-[#00F0FF]/30' : 'text-white/50'
              }`}
            >
              <Zap size={14} className="mr-1" />
              AUTO
            </Button>
          </div>

          {/* Betting Panel */}
          {canBet && game && (
            <BettingPanel game={game} onBetPlaced={fetchTable} />
          )}
        </div>
      )}

      <Navigation />
    </div>
  );
}
