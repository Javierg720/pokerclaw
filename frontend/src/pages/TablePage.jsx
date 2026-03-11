import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { PlayingCard } from '../components/PlayingCard';
import { BettingPanel } from '../components/BettingPanel';
import { ChatPanel } from '../components/ChatPanel';
import { Navigation } from '../components/Navigation';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { ArrowLeft, Play, SkipForward, Zap, Crown, Volume2, VolumeX, Eye, TrendingUp } from 'lucide-react';
import api from '../lib/api';
import { toast } from 'sonner';
import { sounds } from '../lib/sounds';
import { useTableSocket } from '../lib/useWebSocket';

const PHASE_LABELS = {
  waiting: 'Waiting',
  preflop: 'Pre-Flop',
  preflop_betting: 'Pre-Flop',
  flop: 'Flop',
  flop_deal: 'Flop',
  flop_betting: 'Flop',
  turn: 'Turn',
  turn_deal: 'Turn',
  turn_betting: 'Turn',
  river: 'River',
  river_deal: 'River',
  river_betting: 'River',
  showdown: 'Showdown',
  complete: 'Complete',
};

/* ── Layout configs ── */
const SEAT_LAYOUTS = {
  4: [
    { cell: 'topCenter', idx: 0 },
    { cell: 'midRight', idx: 1 },
    { cell: 'botCenter', idx: 2 },
    { cell: 'midLeft', idx: 3 },
  ],
  5: [
    { cell: 'topLeft', idx: 0 },
    { cell: 'topRight', idx: 1 },
    { cell: 'midRight', idx: 2 },
    { cell: 'botCenter', idx: 3 },
    { cell: 'midLeft', idx: 4 },
  ],
  6: [
    { cell: 'topLeft', idx: 0 },
    { cell: 'topRight', idx: 1 },
    { cell: 'midRight', idx: 2 },
    { cell: 'botRight', idx: 3 },
    { cell: 'botLeft', idx: 4 },
    { cell: 'midLeft', idx: 5 },
  ],
};

const DEAL_DIRS = {
  topLeft: { x: 55, y: 55 },
  topCenter: { x: 0, y: 60 },
  topRight: { x: -55, y: 55 },
  midLeft: { x: 65, y: 0 },
  midRight: { x: -65, y: 0 },
  botLeft: { x: 55, y: -55 },
  botCenter: { x: 0, y: -60 },
  botRight: { x: -55, y: -55 },
};

const CHIP_DIRS = {
  topLeft: { x: -55, y: -50 },
  topCenter: { x: 0, y: -60 },
  topRight: { x: 55, y: -50 },
  midLeft: { x: -70, y: 0 },
  midRight: { x: 70, y: 0 },
  botLeft: { x: -55, y: 50 },
  botCenter: { x: 0, y: 60 },
  botRight: { x: 55, y: 50 },
};

const BOT_CELLS = new Set(['botLeft', 'botCenter', 'botRight']);

/* ── Seat component ── */
function SeatPlayer({ player, showCards, isWinner, reversed, dealFrom, isActing, timerPct, lastAction }) {
  const ringClass = player.folded
    ? 'agent-ring-folded'
    : isWinner
    ? 'agent-ring-winner'
    : isActing
    ? 'agent-ring-thinking'
    : 'agent-ring-active';

  const avatar = (
    <div className="flex flex-col items-center gap-0.5">
      <div className="relative">
        {/* Timer ring */}
        {isActing && (
          <svg className="absolute -inset-1.5 w-[calc(100%+12px)] h-[calc(100%+12px)]" viewBox="0 0 44 44">
            <circle cx="22" cy="22" r="20" fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="2" />
            <circle
              cx="22" cy="22" r="20" fill="none" stroke="#FF003C"
              strokeWidth="2.5" strokeLinecap="round"
              strokeDasharray={`${2 * Math.PI * 20}`}
              strokeDashoffset={`${2 * Math.PI * 20 * (1 - timerPct)}`}
              transform="rotate(-90 22 22)"
              className="transition-all duration-1000 linear"
            />
          </svg>
        )}
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
        {isActing && (
          <div className="absolute -bottom-1 left-1/2 -translate-x-1/2 bg-[#FF003C] text-white text-[7px] font-black px-1.5 py-0.5 rounded-full animate-pulse" data-testid={`timer-${player.agent_id}`}>
            THINKING
          </div>
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
          <PlayingCard card={player.hole_cards[0]} size="xs" delay={0} dealFrom={dealFrom} />
          <PlayingCard card={player.hole_cards[1]} size="xs" delay={80} dealFrom={dealFrom} />
        </>
      ) : (
        <>
          <PlayingCard card={null} size="xs" delay={0} dealFrom={dealFrom} />
          <PlayingCard card={null} size="xs" delay={80} dealFrom={dealFrom} />
        </>
      )}
    </div>
  );

  const actionBadge = player.folded ? (
    <span className="action-badge action-fold text-[7px]">FOLD</span>
  ) : lastAction && lastAction.agent_id === player.agent_id ? (
    <span className={`action-badge text-[7px] ${
      lastAction.action === 'raise' ? 'action-raise' :
      lastAction.action === 'fold' ? 'action-fold' : 'action-call'
    }`}>
      {lastAction.action.toUpperCase()}{lastAction.amount > 0 ? ` ${lastAction.amount}` : ''}
    </span>
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
function PokerTableVisual({ game, showCards, currentActor, timerPct, lastAction }) {
  const players = game?.players || [];
  const isShowdown = ['showdown', 'complete'].includes(game?.display_phase || game?.phase);
  const count = Math.min(Math.max(players.length, 4), 6);
  const layout = SEAT_LAYOUTS[count] || SEAT_LAYOUTS[4];

  // Build cell -> player mapping
  const cellMap = {};
  layout.forEach(({ cell, idx }) => {
    if (players[idx]) cellMap[cell] = players[idx];
  });

  // Chip fly data
  const chipData = layout
    .filter(({ idx }) => players[idx] && !players[idx].folded && players[idx].total_bet > 0)
    .map(({ cell, idx }, i) => ({
      player: players[idx],
      dir: CHIP_DIRS[cell],
      delay: i * 80,
    }));

  const renderSeat = (cellName, className) => {
    const player = cellMap[cellName];
    return (
      <div className={className} key={cellName}>
        {player && (
          <SeatPlayer
            player={player}
            showCards={showCards}
            isWinner={isShowdown && game.winner_id === player.agent_id}
            reversed={BOT_CELLS.has(cellName)}
            dealFrom={DEAL_DIRS[cellName]}
            isActing={currentActor === player.agent_id}
            timerPct={currentActor === player.agent_id ? timerPct : 0}
            lastAction={lastAction}
          />
        )}
      </div>
    );
  };

  return (
    <div className="poker-table-grid" style={{ height: '420px' }} data-testid="poker-table">
      {/* Row 1 - Top */}
      {renderSeat('topLeft', 'flex items-end justify-center pb-1')}
      {renderSeat('topCenter', 'flex items-end justify-center pb-1')}
      {renderSeat('topRight', 'flex items-end justify-center pb-1')}

      {/* Row 2 - Middle */}
      {renderSeat('midLeft', 'flex items-center justify-center')}

      {/* THE TABLE FELT */}
      <div className="poker-felt rounded-[45%] flex flex-col items-center justify-center gap-1.5 p-2">
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
              <PlayingCard
                key={`cc-${i}-${game.community_cards[i].rank}-${game.community_cards[i].suit}`}
                card={game.community_cards[i]}
                size="sm"
                delay={i * 120}
                dealFrom={{ x: 0, y: -40 }}
              />
            ) : (
              <div
                key={`cc-empty-${i}`}
                className="w-8 h-12 rounded border border-white/[0.06] bg-white/[0.015]"
              />
            )
          )}
        </div>

        {/* Bet chips flying in from seats */}
        <div className="flex flex-wrap gap-1.5 justify-center mt-0.5 z-10">
          {chipData.map(({ player, dir, delay }) => (
            <div
              key={player.agent_id}
              className="table-bet-chip chip-fly"
              style={{
                '--chip-x': `${dir.x}px`,
                '--chip-y': `${dir.y}px`,
                animationDelay: `${delay}ms`,
              }}
              data-testid={`chip-${player.agent_id}`}
            >
              {player.total_bet}
            </div>
          ))}
        </div>
      </div>

      {renderSeat('midRight', 'flex items-center justify-center')}

      {/* Row 3 - Bottom */}
      {renderSeat('botLeft', 'flex items-start justify-center pt-1')}
      {renderSeat('botCenter', 'flex items-start justify-center pt-1')}
      {renderSeat('botRight', 'flex items-start justify-center pt-1')}
    </div>
  );
}

/* ── Main TablePage ── */
export default function TablePage() {
  const { tableId } = useParams();
  const navigate = useNavigate();
  const { isHuman } = useAuth();
  const [table, setTable] = useState(null);
  const [game, setGame] = useState(null);
  const [autoPlay, setAutoPlay] = useState(false);
  const [advancing, setAdvancing] = useState(false);
  const [actions, setActions] = useState([]);
  const [soundOn, setSoundOn] = useState(sounds.isEnabled());
  const [odds, setOdds] = useState(null);
  const [timer, setTimer] = useState(0);
  const [timerMax] = useState(10);
  const prevPhaseRef = useRef(null);
  const timerRef = useRef(null);
  const autoAdvanceRef = useRef(null);

  // WebSocket for real-time updates
  const { gameState: wsGame, spectators, connected, send, chatMessages, reactions } = useTableSocket(tableId);

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

  const fetchOdds = useCallback(async () => {
    if (!game?.id) return;
    try {
      const res = await api.get(`/bets/game/${game.id}/odds`);
      setOdds(res.data);
    } catch {
      // silent
    }
  }, [game?.id]);

  useEffect(() => { fetchTable(); }, [fetchTable]);

  // Fetch odds periodically
  useEffect(() => {
    fetchOdds();
    const interval = setInterval(fetchOdds, 6000);
    return () => clearInterval(interval);
  }, [fetchOdds]);

  // Apply WebSocket game updates
  useEffect(() => {
    if (wsGame) {
      setGame(wsGame);
      setActions(wsGame.actions_log || []);
    }
  }, [wsGame]);

  // Sound effects on phase change
  useEffect(() => {
    if (!game) return;
    const prev = prevPhaseRef.current;
    const curr = game.display_phase || game.phase;
    prevPhaseRef.current = curr;

    if (!prev || prev === curr) return;

    if (curr === 'preflop') sounds.cardDeal();
    if (['flop', 'turn', 'river'].includes(curr)) {
      sounds.cardFlip();
      sounds.notification();
    }
    if (curr === 'showdown' || curr === 'complete') {
      if (game.winner_name) sounds.winFanfare();
    }
  }, [game?.display_phase, game?.phase, game?.winner_name]);

  // Play action sound when last_action changes
  useEffect(() => {
    if (game?.last_action) {
      sounds.actionSound(game.last_action.action);
    }
  }, [game?.last_action]);

  const startGame = async () => {
    try {
      const res = await api.post(`/tables/${tableId}/start-game`);
      setGame(res.data);
      setActions([]);
      sounds.cardDeal();
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
      setTimer(timerMax); // Reset timer for next turn
      if (res.data.phase === 'complete') {
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
  }, [game, advancing, timerMax]);

  // Auto-advance timer: When autoPlay is on AND there's a current_actor,
  // count down from 10s then advance
  useEffect(() => {
    // Clear existing timers
    if (timerRef.current) clearInterval(timerRef.current);
    if (autoAdvanceRef.current) clearTimeout(autoAdvanceRef.current);

    if (!autoPlay || !game || game.phase === 'complete') return;

    // If game is in a deal phase (not betting), advance quickly
    if (game.phase?.endsWith('_deal') || game.phase === 'waiting' || game.phase === 'showdown') {
      autoAdvanceRef.current = setTimeout(advanceGame, 800);
      return () => {
        if (autoAdvanceRef.current) clearTimeout(autoAdvanceRef.current);
      };
    }

    // Betting phase: use 10-second timer
    if (game.is_betting && game.current_actor) {
      // Random decision time: 2-8 seconds to feel natural
      const decisionTime = Math.floor(Math.random() * 6000) + 2000;
      setTimer(timerMax);

      // Countdown ticker
      timerRef.current = setInterval(() => {
        setTimer(prev => {
          if (prev <= 0) return 0;
          return prev - 1;
        });
      }, 1000);

      // Auto-advance after decision time
      autoAdvanceRef.current = setTimeout(advanceGame, decisionTime);

      return () => {
        if (timerRef.current) clearInterval(timerRef.current);
        if (autoAdvanceRef.current) clearTimeout(autoAdvanceRef.current);
      };
    }

    // Fallback: advance after short delay
    autoAdvanceRef.current = setTimeout(advanceGame, 1500);
    return () => {
      if (autoAdvanceRef.current) clearTimeout(autoAdvanceRef.current);
    };
  }, [autoPlay, game?.phase, game?.current_actor, game?.turn_index, advanceGame, timerMax]);

  const toggleSound = () => {
    const on = sounds.toggle();
    setSoundOn(on);
  };

  const chatUsername = (() => {
    try {
      const token = localStorage.getItem('pokerclaw_token');
      if (token) {
        const payload = JSON.parse(atob(token.split('.')[1]));
        return payload.username || 'Spectator';
      }
    } catch { /* ignore */ }
    return 'Spectator';
  })();

  const handleSendChat = (text) => {
    send({ type: 'chat', username: chatUsername, text });
  };

  const handleSendReaction = (emoji) => {
    send({ type: 'reaction', emoji, username: chatUsername });
  };

  const displayPhase = game?.display_phase || game?.phase;
  const canBet = game && !['showdown', 'complete', 'waiting'].includes(displayPhase);
  const showCards = game && ['showdown', 'complete'].includes(displayPhase);
  const lastActions = actions.slice(-6);
  const currentActor = game?.current_actor;
  const timerPct = timerMax > 0 ? timer / timerMax : 0;

  return (
    <div className="main-content" data-testid="table-page">
      {/* Header */}
      <div className="flex items-center justify-between px-4 pt-3 pb-1">
        <button onClick={() => navigate('/lobby')} data-testid="back-to-lobby" className="text-white/50 hover:text-white transition-colors">
          <ArrowLeft size={20} />
        </button>
        <div className="text-center">
          <h2 className="text-sm font-bold text-white">{table?.name || 'Loading...'}</h2>
          <div className="flex items-center justify-center gap-2 mt-0.5">
            {game && (
              <Badge variant="outline" className="text-[10px] border-[#FF003C]/30 text-[#FF003C]">
                {PHASE_LABELS[displayPhase] || displayPhase}
              </Badge>
            )}
            <span className="flex items-center gap-1 text-[10px] text-white/30">
              <Eye size={10} />
              {spectators}
            </span>
            {connected && <span className="w-1.5 h-1.5 rounded-full bg-[#00F0FF]" title="Live" />}
          </div>
        </div>
        <button onClick={toggleSound} data-testid="sound-toggle" className="text-white/40 hover:text-white transition-colors">
          {soundOn ? <Volume2 size={18} /> : <VolumeX size={18} />}
        </button>
      </div>

      {/* Live Odds Ticker */}
      {odds && odds.total_pool > 0 && canBet && (
        <div className="mx-4 mb-2 glass rounded-lg p-2 flex items-center gap-3 overflow-x-auto" data-testid="odds-ticker">
          <TrendingUp size={12} className="text-[#FFE600] flex-shrink-0" />
          <span className="text-[9px] text-white/30 flex-shrink-0">LIVE ODDS</span>
          {odds.odds.filter(o => !o.folded).map(o => (
            <div key={o.agent_id} className="flex items-center gap-1.5 flex-shrink-0">
              <img src={o.avatar_url} alt="" className="w-4 h-4 rounded-full" />
              <span className="text-[9px] text-white/50 truncate max-w-[50px]">{o.agent_name}</span>
              <span className="text-[10px] font-black text-[#FFE600] mono">{o.multiplier}x</span>
            </div>
          ))}
        </div>
      )}

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
              {odds && odds.total_pool > 0 && (
                <div className="mt-3 pt-3 border-t border-white/[0.05] text-xs text-white/30">
                  Side bet pool: {odds.total_pool} SC ({odds.total_bets} bets)
                </div>
              )}
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
          <PokerTableVisual
            game={game}
            showCards={showCards}
            currentActor={currentActor}
            timerPct={timerPct}
            lastAction={game?.last_action}
          />

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

          {/* Timer Display */}
          {autoPlay && game?.is_betting && currentActor && (
            <div className="flex items-center justify-center gap-2 mx-2" data-testid="decision-timer">
              <div className="glass rounded-lg px-3 py-1.5 flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-[#FF003C] animate-pulse" />
                <span className="text-[10px] text-white/50">
                  {game.players?.find(p => p.agent_id === currentActor)?.agent_name || 'Agent'} deciding...
                </span>
                <span className="text-xs font-black text-[#FF003C] mono">{timer}s</span>
              </div>
            </div>
          )}

          {/* Controls */}
          <div className="flex items-center gap-3 mx-2">
            <Button
              onClick={advanceGame}
              disabled={advancing || game.phase === 'complete'}
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

      <ChatPanel
        chatMessages={chatMessages}
        reactions={reactions}
        onSendChat={handleSendChat}
        onSendReaction={handleSendReaction}
        username={chatUsername}
      />

      <Navigation />
    </div>
  );
}
