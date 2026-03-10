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

/* ── Seat component ── */
function SeatPlayer({ player, showCards, isWinner, reversed }) {
  const ringClass = player.folded
    ? 'agent-ring-folded'
    : isWinner
    ? 'agent-ring-winner'
    : 'agent-ring-active';

  const avatar = (
    <div className="flex flex-col items-center gap-0.5">
      <div className="relative">
        <div className={`agent-ring ${ringClass}`}>
          <img
            src={player.avatar_url}
            alt={player.agent_name}
            className="w-9 h-9 rounded-full object-cover"
          />
        </div>
        {player.is_dealer && (
          <div className="dealer-btn absolute -bottom-0.5 -right-0.5">D</div>
        )}
        {isWinner && (
          <Crown size={12} className="text-[#FFE600] absolute -top-1 -right-1" />
        )}
      </div>
      <div className={`seat-nameplate ${isWinner ? 'is-winner' : ''} ${player.folded ? 'is-folded' : ''}`}>
        <div className="text-[9px] font-bold text-white truncate max-w-[68px]">
          {player.agent_name}
        </div>
        <div className="text-[8px] text-white/40 mono">{player.chips}</div>
      </div>
    </div>
  );

  const cards = (
    <div className="flex gap-0.5 justify-center" data-testid={`seat-cards-${player.agent_id}`}>
      {showCards && player.hole_cards?.[0] ? (
        <>
          <PlayingCard card={player.hole_cards[0]} size="xs" delay={0} />
          <PlayingCard card={player.hole_cards[1]} size="xs" delay={60} />
        </>
      ) : (
        <>
          <PlayingCard card={null} size="xs" />
          <PlayingCard card={null} size="xs" />
        </>
      )}
    </div>
  );

  const actionBadge = player.folded ? (
    <span className="action-badge action-fold text-[7px]">FOLD</span>
  ) : showCards && player.hand_name ? (
    <span className="text-[8px] text-[#00F0FF] font-bold">{player.hand_name}</span>
  ) : null;

  return (
    <div className={`flex flex-col items-center gap-1 ${player.folded ? 'opacity-40' : ''}`}>
      {reversed ? (
        <>
          {actionBadge}
          {cards}
          {avatar}
        </>
      ) : (
        <>
          {avatar}
          {cards}
          {actionBadge}
        </>
      )}
    </div>
  );
}

/* ── Poker Table Visual ── */
function PokerTableVisual({ game, showCards }) {
  const players = game?.players || [];
  const isShowdown = ['showdown', 'complete'].includes(game?.phase);

  // Positions: 0=top, 1=right, 2=bottom, 3=left
  // For 5-6 players, add top-left / top-right splits
  const getPlayers = () => {
    if (players.length <= 4) return { top: players[0], right: players[1], bottom: players[2], left: players[3] };
    if (players.length === 5) return { top: players[0], topRight: players[1], right: players[2], bottom: players[3], left: players[4] };
    return { topLeft: players[0], topRight: players[1], right: players[2], bottomRight: players[3], bottomLeft: players[4], left: players[5] };
  };

  const seats = getPlayers();

  return (
    <div className="poker-table-grid" style={{ height: '420px' }} data-testid="poker-table">
      {/* Row 1 - Top */}
      <div /> {/* top-left empty */}
      <div className="flex items-end justify-center pb-1">
        {seats.top && (
          <SeatPlayer
            player={seats.top}
            showCards={showCards}
            isWinner={isShowdown && game.winner_id === seats.top.agent_id}
          />
        )}
      </div>
      <div /> {/* top-right empty */}

      {/* Row 2 - Middle: Left player | TABLE | Right player */}
      <div className="flex items-center justify-center">
        {seats.left && (
          <SeatPlayer
            player={seats.left}
            showCards={showCards}
            isWinner={isShowdown && game.winner_id === seats.left.agent_id}
          />
        )}
      </div>

      {/* THE TABLE FELT */}
      <div className="poker-felt rounded-[45%] flex flex-col items-center justify-center gap-2 p-2">
        {/* Pot */}
        <div className="text-center z-10">
          <span className="text-[10px] text-white/30 uppercase tracking-widest">Pot</span>
          <div className="text-lg font-black text-[#FFE600] text-glow-gold mono leading-tight" data-testid="pot-display">
            {game?.pot || 0}
          </div>
        </div>

        {/* Community cards */}
        <div className="flex gap-1 justify-center z-10" data-testid="community-cards">
          {[0, 1, 2, 3, 4].map((i) =>
            game?.community_cards?.[i] ? (
              <PlayingCard key={i} card={game.community_cards[i]} size="sm" delay={i * 80} />
            ) : (
              <div
                key={i}
                className="w-8 h-12 rounded border border-white/[0.06] bg-white/[0.015]"
              />
            )
          )}
        </div>

        {/* Bet chips on table */}
        <div className="flex gap-2 mt-1 z-10">
          {players
            .filter((p) => !p.folded && p.total_bet > 0)
            .map((p) => (
              <div key={p.agent_id} className="table-bet-chip chip-bounce">
                {p.total_bet}
              </div>
            ))}
        </div>
      </div>

      <div className="flex items-center justify-center">
        {seats.right && (
          <SeatPlayer
            player={seats.right}
            showCards={showCards}
            isWinner={isShowdown && game.winner_id === seats.right.agent_id}
          />
        )}
      </div>

      {/* Row 3 - Bottom */}
      <div /> {/* bottom-left empty */}
      <div className="flex items-start justify-center pt-1">
        {seats.bottom && (
          <SeatPlayer
            player={seats.bottom}
            showCards={showCards}
            isWinner={isShowdown && game.winner_id === seats.bottom.agent_id}
            reversed
          />
        )}
      </div>
      <div /> {/* bottom-right empty */}
    </div>
  );
}

/* ── Main TablePage ── */
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
      <div className="flex items-center justify-between px-4 pt-3 pb-1">
        <button onClick={() => navigate('/lobby')} data-testid="back-to-lobby" className="text-white/50 hover:text-white transition-colors">
          <ArrowLeft size={20} />
        </button>
        <div className="text-center">
          <h2 className="text-sm font-bold text-white">{table?.name || 'Loading...'}</h2>
          {game && (
            <Badge variant="outline" className="text-[10px] mt-0.5 border-[#FF003C]/30 text-[#FF003C]">
              {PHASE_LABELS[game.phase] || game.phase}
            </Badge>
          )}
        </div>
        <div className="w-5" />
      </div>

      {!game || game.phase === 'complete' ? (
        /* No active game / Game complete */
        <div className="flex flex-col items-center justify-center px-6 py-16">
          {game?.phase === 'complete' && game.winner_name && (
            <div className="glass rounded-2xl p-6 mb-6 text-center w-full max-w-sm glow-gold">
              <Crown className="text-[#FFE600] mx-auto mb-2" size={28} />
              <h3 className="text-lg font-black text-[#FFE600] mb-1">{game.winner_name}</h3>
              <p className="text-white/50 text-sm">{game.winning_hand}</p>
              <div className="flex justify-center gap-4 mt-3 text-xs">
                <div>
                  <span className="text-white/40">Pot</span>
                  <span className="text-[#FFE600] font-bold ml-1">{game.pot}</span>
                </div>
                <div>
                  <span className="text-white/40">Rake (20%)</span>
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
        /* Active game - Poker Table View */
        <div className="px-2 space-y-3">
          {/* THE POKER TABLE */}
          <PokerTableVisual game={game} showCards={showCards} />

          {/* Actions Log */}
          {lastActions.length > 0 && (
            <div className="glass rounded-xl p-3 mx-2" data-testid="actions-log">
              <h4 className="text-[10px] text-white/30 uppercase tracking-widest mb-2">Actions</h4>
              <div className="flex flex-wrap gap-x-3 gap-y-1">
                {lastActions.map((a, i) => (
                  <div key={i} className="flex items-center gap-1.5 text-[11px]">
                    <span className="text-white/50 truncate max-w-[80px]">{a.agent_name}</span>
                    <span className={`action-badge action-${a.action}`}>
                      {a.action} {a.amount > 0 ? a.amount : ''}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Controls */}
          <div className="flex items-center gap-3 mx-2">
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
          <div className="mx-2">
            {canBet && game && (
              <BettingPanel game={game} onBetPlaced={fetchTable} />
            )}
          </div>
        </div>
      )}

      <Navigation />
    </div>
  );
}
