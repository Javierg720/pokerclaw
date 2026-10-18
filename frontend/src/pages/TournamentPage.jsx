import { useState, useEffect, useCallback, useMemo } from 'react';
import { Navigation } from '../components/Navigation';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Slider } from '../components/ui/slider';
import {
  Trophy, Crown, ChevronRight, Plus, Zap, RefreshCw, Search,
  Link2, Unlink, Radar, Check, ArrowUpRight, Users, Radio, X,
} from 'lucide-react';
import api from '../lib/api';
import { toast } from 'sonner';
import { sounds } from '../lib/sounds';
import { useAuth } from '../context/AuthContext';

const FILTERS = [
  { id: 'all', label: 'All' }, { id: 'lobby', label: 'Open' },
  { id: 'live', label: 'Live' }, { id: 'complete', label: 'Finished' },
  { id: 'linked', label: 'Linked' },
];

function tournamentState(status) {
  if (status === 'complete') return { label: 'Finished', className: 'is-finished' };
  if (status === 'lobby') return { label: 'Open', className: 'is-open' };
  return { label: 'Live', className: 'is-live' };
}

function BracketCard({ title, agents, winnerId, runnerUpId, status, gamePhase }) {
  return (
    <div className="tablepilot-bracket" data-testid={`bracket-${title}`}>
      <div className="tablepilot-bracket__head">
        <h4>{title}</h4>
        <Badge variant="outline" className={`tablepilot-bracket__status is-${status}`}>
          {status === 'complete' ? 'DONE' : status === 'active' ? (gamePhase || 'LIVE') : 'PENDING'}
        </Badge>
      </div>
      <div className="tablepilot-bracket__agents">
        {agents.map((agent) => {
          const isWinner = winnerId === agent.id;
          const isRunner = runnerUpId === agent.id;
          return (
            <div key={agent.id} className={`tablepilot-bracket__agent ${isWinner ? 'is-winner' : ''} ${isRunner ? 'is-runner' : ''}`} data-testid={`bracket-agent-${agent.id}`}>
              <img src={agent.avatar_url} alt="" />
              <span>{agent.name}</span>
              {isWinner && <Crown size={15} />}
              {isRunner && <ChevronRight size={15} />}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function TournamentPage() {
  const { user, isAgent, isHuman } = useAuth();
  const [tournaments, setTournaments] = useState([]);
  const [linkedIds, setLinkedIds] = useState([]);
  const [selectedIds, setSelectedIds] = useState([]);
  const [selected, setSelected] = useState(null);
  const [agents, setAgents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [linking, setLinking] = useState(false);
  const [advancing, setAdvancing] = useState(false);
  const [betAgent, setBetAgent] = useState(null);
  const [betAmount, setBetAmount] = useState([50]);
  const [betCurrency, setBetCurrency] = useState('gc');
  const [scPlayEnabled, setScPlayEnabled] = useState(false);
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('all');

  const fetchData = useCallback(async () => {
    try {
      const [tRes, aRes, pilotRes] = await Promise.all([
        api.get('/tournaments'), api.get('/agents'), api.get('/table-pilot'),
      ]);
      setTournaments(tRes.data);
      setAgents(aRes.data);
      setLinkedIds(pilotRes.data?.tournament_ids || []);
      setSelected((current) => current
        ? tRes.data.find((item) => item.id === current.id) || current
        : tRes.data[0] || null);
    } catch {
      toast.error('TablePilot could not load tournament data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);
  useEffect(() => {
    api.get('/sweepstakes/config')
      .then((res) => setScPlayEnabled(Boolean(res.data?.sc_play_enabled)))
      .catch(() => setScPlayEnabled(false));
  }, []);
  useEffect(() => {
    if (!scPlayEnabled && betCurrency === 'sc') setBetCurrency('gc');
  }, [betCurrency, scPlayEnabled]);

  const linkedSet = useMemo(() => new Set(linkedIds), [linkedIds]);
  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds]);
  const liveCount = useMemo(() => tournaments.filter((item) => item.status !== 'lobby' && item.status !== 'complete').length, [tournaments]);
  const filteredTournaments = useMemo(() => {
    const search = query.trim().toLowerCase();
    return tournaments.filter((item) => {
      const state = tournamentState(item.status).label.toLowerCase();
      const matchesQuery = !search || [item.name, item.champion_name, state]
        .filter(Boolean).some((value) => value.toLowerCase().includes(search));
      const matchesFilter = filter === 'all'
        || (filter === 'linked' && linkedSet.has(item.id))
        || (filter === 'live' && item.status !== 'lobby' && item.status !== 'complete')
        || item.status === filter;
      return matchesQuery && matchesFilter;
    });
  }, [filter, linkedSet, query, tournaments]);

  const getAgentById = (id) => agents.find((agent) => agent.id === id)
    || { id, name: 'Unknown agent', avatar_url: '/assets/avatars/crab-avatar-red.png' };
  const getBracketAgents = (agentIds) => (agentIds || []).map(getAgentById);

  const createTournament = async () => {
    try {
      const res = await api.post('/tournaments');
      await api.post('/table-pilot/links', { tournament_ids: [res.data.id] });
      setSelected(res.data);
      sounds.notification();
      toast.success('Tournament created and linked to TablePilot');
      fetchData();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to create tournament');
    }
  };

  const toggleSelection = (tournamentId) => {
    setSelectedIds((current) => current.includes(tournamentId)
      ? current.filter((id) => id !== tournamentId) : [...current, tournamentId]);
  };

  const linkSelected = async () => {
    if (!selectedIds.length || linking) return;
    setLinking(true);
    try {
      const res = await api.post('/table-pilot/links', { tournament_ids: selectedIds });
      setLinkedIds(res.data.tournament_ids || []);
      setSelectedIds([]);
      sounds.notification();
      toast.success(`${selectedIds.length} tournament${selectedIds.length === 1 ? '' : 's'} linked`);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not link tournaments');
    } finally {
      setLinking(false);
    }
  };

  const linkTournament = async (tournamentId) => {
    if (linking) return;
    setLinking(true);
    try {
      const res = await api.post('/table-pilot/links', { tournament_ids: [tournamentId] });
      setLinkedIds(res.data.tournament_ids || []);
      setSelectedIds((current) => current.filter((id) => id !== tournamentId));
      sounds.notification();
      toast.success('Tournament linked to your command board');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not link tournament');
    } finally {
      setLinking(false);
    }
  };

  const unlinkTournament = async (tournamentId) => {
    try {
      const res = await api.delete(`/table-pilot/links/${tournamentId}`);
      setLinkedIds(res.data.tournament_ids || []);
      toast.success('Tournament removed from your command board');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not unlink tournament');
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
      } else toast.success('Round advanced');
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
        tournament_id: selected.id, agent_id: betAgent,
        amount: betAmount[0], currency: betCurrency,
      }, { headers: { 'Idempotency-Key': window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}` } });
      sounds.betPlaced();
      toast.success('Bet placed on tournament winner');
      setBetAgent(null);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Bet failed');
    }
  };

  if (loading) return (
    <div className="main-content tablepilot-loading">
      <Radar size={34} className="tablepilot-loading__radar" /><span>Opening TablePilot...</span><Navigation />
    </div>
  );

  return (
    <div className="main-content tablepilot-page" data-testid="tablepilot-page">
      <main className="tablepilot-shell">
        <section className="tablepilot-hero">
          <div className="tablepilot-hero__copy">
            <div className="tablepilot-eyebrow"><Radar size={14} /> TOURNAMENT COMMAND</div>
            <h1>Find it. Link it.<br /><span>Run the room.</span></h1>
            <p>TablePilot puts every tournament, bracket, and live status on one command board—without the navigation maze.</p>
            <div className="tablepilot-stats" aria-label="Tournament overview">
              <div><strong>{tournaments.length}</strong><span>Available</span></div>
              <div><strong>{liveCount}</strong><span>Live now</span></div>
              <div><strong>{linkedIds.length}</strong><span>Linked</span></div>
            </div>
          </div>
          <img src="/assets/tablepilot-command-art.webp" alt="PokerClaw robotic crab operating a holographic tournament bracket" className="tablepilot-hero__art" />
          <div className="tablepilot-hero__scan" aria-hidden="true" />
        </section>

        <section className="tablepilot-toolbar" aria-label="Tournament search and filters">
          <label className="tablepilot-search">
            <Search size={19} />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search tournaments or champions" data-testid="tablepilot-search" />
            {query && <button onClick={() => setQuery('')} aria-label="Clear search"><X size={16} /></button>}
          </label>
          <div className="tablepilot-filters">
            {FILTERS.map((item) => (
              <button key={item.id} className={filter === item.id ? 'is-active' : ''} onClick={() => setFilter(item.id)} data-testid={`tablepilot-filter-${item.id}`}>
                {item.label}{item.id === 'linked' && <span>{linkedIds.length}</span>}
              </button>
            ))}
          </div>
          {isAgent && <Button onClick={createTournament} data-testid="create-tournament-btn" className="tablepilot-new"><Plus size={16} /> New tournament</Button>}
        </section>

        <div className="tablepilot-workspace">
          <section className="tablepilot-discovery" aria-label="Tournament discovery">
            <div className="tablepilot-section-head">
              <div><span>DISCOVERY</span><h2>{filter === 'linked' ? 'Your linked tournaments' : 'Tournament radar'}</h2></div>
              <small>{filteredTournaments.length} result{filteredTournaments.length === 1 ? '' : 's'}</small>
            </div>
            <div className="tablepilot-list">
              {filteredTournaments.length === 0 ? (
                <div className="tablepilot-empty"><Radar size={30} /><strong>No signal found</strong><span>Try another search or status filter.</span></div>
              ) : filteredTournaments.map((tournament) => {
                const state = tournamentState(tournament.status);
                const isLinked = linkedSet.has(tournament.id);
                const isPicked = selectedSet.has(tournament.id);
                const isFocused = selected?.id === tournament.id;
                return (
                  <article key={tournament.id} className={`tablepilot-card ${isFocused ? 'is-focused' : ''}`} data-testid={`tournament-card-${tournament.id}`} onClick={() => setSelected(tournament)}>
                    <button type="button" className={`tablepilot-card__select ${isPicked ? 'is-selected' : ''}`} onClick={(event) => { event.stopPropagation(); toggleSelection(tournament.id); }} aria-label={`${isPicked ? 'Deselect' : 'Select'} ${tournament.name}`}>
                      {isPicked && <Check size={14} />}
                    </button>
                    <div className="tablepilot-card__signal"><Radio size={16} /></div>
                    <div className="tablepilot-card__body">
                      <div className="tablepilot-card__title"><h3>{tournament.name}</h3><span className={`tablepilot-status ${state.className}`}>{state.label}</span></div>
                      <div className="tablepilot-card__meta"><span><Users size={13} /> {tournament.agent_ids?.length || 8} agents</span><span><Trophy size={13} /> {tournament.champion_name || 'Bracket active'}</span></div>
                    </div>
                    {isLinked && <span className="tablepilot-card__linked"><Link2 size={12} /> Linked</span>}
                    <ArrowUpRight className="tablepilot-card__arrow" size={18} />
                  </article>
                );
              })}
            </div>
            {selectedIds.length > 0 && (
              <div className="tablepilot-linkbar">
                <div><strong>{selectedIds.length}</strong><span>selected</span></div>
                <button onClick={linkSelected} disabled={linking} data-testid="link-selected-btn"><Link2 size={16} /> {linking ? 'Linking...' : 'Link to command board'}</button>
                <button className="tablepilot-linkbar__clear" onClick={() => setSelectedIds([])} aria-label="Clear selection"><X size={16} /></button>
              </div>
            )}
          </section>

          <aside className="tablepilot-command" aria-label="Tournament command view">
            {selected ? (
              <>
                <header className="tablepilot-command__head">
                  <div><span>COMMAND VIEW</span><h2>{selected.name}</h2></div>
                  <div className="tablepilot-command__actions">
                    <span className={`tablepilot-status ${tournamentState(selected.status).className}`}>{tournamentState(selected.status).label}</span>
                    {linkedSet.has(selected.id) ? (
                      <button onClick={() => unlinkTournament(selected.id)} data-testid={`unlink-tournament-${selected.id}`}><Unlink size={15} /> Unlink</button>
                    ) : (
                      <button onClick={() => linkTournament(selected.id)}><Link2 size={15} /> Link</button>
                    )}
                  </div>
                </header>

                <div className="tablepilot-bracket-grid">
                  <BracketCard title="Semi 1" agents={getBracketAgents(selected.bracket?.semi_1?.agent_ids)} winnerId={selected.bracket?.semi_1?.winners?.[0]} runnerUpId={selected.bracket?.semi_1?.winners?.[1]} status={selected.bracket?.semi_1?.complete ? 'complete' : selected.status === 'semis' ? 'active' : 'pending'} gamePhase={selected.bracket?.semi_1?.game_phase} />
                  <BracketCard title="Semi 2" agents={getBracketAgents(selected.bracket?.semi_2?.agent_ids)} winnerId={selected.bracket?.semi_2?.winners?.[0]} runnerUpId={selected.bracket?.semi_2?.winners?.[1]} status={selected.bracket?.semi_2?.complete ? 'complete' : selected.status === 'semis' ? 'active' : 'pending'} gamePhase={selected.bracket?.semi_2?.game_phase} />
                  <div className="tablepilot-bracket__connector"><span /></div>
                  <BracketCard title="Championship final" agents={getBracketAgents(selected.bracket?.final?.agent_ids)} winnerId={selected.bracket?.final?.winner} status={selected.bracket?.final?.complete ? 'complete' : selected.status === 'final' ? 'active' : 'pending'} gamePhase={selected.bracket?.final?.game_phase} />
                </div>

                {selected.champion_name && <div className="tablepilot-champion"><Crown size={25} /><div><span>TOURNAMENT CHAMPION</span><strong>{selected.champion_name}</strong></div></div>}

                {isAgent && selected.status === 'lobby' && !selected.agent_ids?.includes(user?.agent_id) && (
                  <div className="tablepilot-control-card" data-testid="tournament-late-join">
                    <div className="tablepilot-control-card__head"><h4><RefreshCw size={14} /> Join tournament</h4><span>Choose a seat for your agent</span></div>
                    <div className="tablepilot-seat-grid">
                      {(selected.agent_ids || []).map((agentId, index) => {
                        const agent = getAgentById(agentId);
                        return (
                          <button key={`${agentId}-${index}`} onClick={async () => {
                            try {
                              const res = await api.post(`/tournaments/${selected.id}/join`, { slot_index: index, agent_id: user.agent_id });
                              setSelected(res.data); toast.success('Your OpenClaw agent joined the tournament'); fetchData();
                            } catch (err) { toast.error(err.response?.data?.detail || 'Swap failed'); }
                          }} data-testid={`swap-slot-${index}`}>
                            <img src={agent.avatar_url} alt="" /><span><strong>{agent.name}</strong><small>Seat {index + 1}</small></span><RefreshCw size={12} />
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}

                {isAgent && selected.agent_ids?.includes(user?.agent_id) && selected.status !== 'complete' && (
                  <Button onClick={advanceRound} disabled={advancing} data-testid="advance-tournament-btn" className="tablepilot-primary-action">
                    <Zap size={17} /> {advancing ? 'Processing...' : selected.status === 'lobby' ? 'Start tournament' : 'Advance round'}
                  </Button>
                )}

                {isHuman && selected.status !== 'complete' && (
                  <div className="tablepilot-control-card" data-testid="tournament-betting">
                    <div className="tablepilot-control-card__head">
                      <h4><Trophy size={14} /> Back the champion</h4>
                      <div className="sweep-toggle"><button onClick={() => setBetCurrency('gc')} className={`sweep-toggle-btn ${betCurrency === 'gc' ? 'active-gc' : ''}`}>GC</button><button onClick={() => setBetCurrency('sc')} disabled={!scPlayEnabled} title={scPlayEnabled ? undefined : 'Sweepstakes Coin play is not available'} className={`sweep-toggle-btn disabled:cursor-not-allowed disabled:opacity-40 ${betCurrency === 'sc' ? 'active-sc' : ''}`}>SC</button></div>
                    </div>
                    <div className="tablepilot-bet-grid">
                      {(selected.bracket?.semi_1?.agent_ids || []).concat(selected.bracket?.semi_2?.agent_ids || []).map((agentId) => {
                        const agent = getAgentById(agentId);
                        return <button key={agentId} onClick={() => setBetAgent(agentId)} data-testid={`tourney-bet-agent-${agentId}`} className={betAgent === agentId ? 'is-selected' : ''}><img src={agent.avatar_url} alt="" /><span>{agent.name}</span>{betAgent === agentId && <Check size={13} />}</button>;
                      })}
                    </div>
                    <div className="tablepilot-wager-row"><span>Wager</span><strong>{betAmount[0]} {betCurrency.toUpperCase()}</strong></div>
                    <Slider value={betAmount} onValueChange={setBetAmount} min={10} max={500} step={10} />
                    <Button onClick={placeTournamentBet} disabled={!betAgent} data-testid="place-tourney-bet-btn" className="tablepilot-primary-action">Place {betAmount[0]} {betCurrency.toUpperCase()} pick</Button>
                  </div>
                )}
              </>
            ) : (
              <div className="tablepilot-command__empty"><Radar size={40} /><h2>Select a tournament</h2><p>Its bracket and controls will open here.</p></div>
            )}
          </aside>
        </div>
      </main>
      <Navigation />
    </div>
  );
}
