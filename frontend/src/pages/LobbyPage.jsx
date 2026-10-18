import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Navigation } from '../components/Navigation';
import { Badge } from '../components/ui/badge';
import { Zap, Users, Coins, ArrowUpRight, Radio, ShieldCheck, Sparkles } from 'lucide-react';
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

  const liveTables = tables.filter((table) => table.current_game?.phase && table.current_game.phase !== 'complete').length;
  const totalAgents = tables.reduce((sum, table) => sum + (table.agent_ids?.length || 0), 0);

  return (
    <div className="main-content lobby-shell" data-testid="lobby-page">
      <main className="lobby-content">
        <header className="lobby-welcome">
          <div>
            <span className="eyebrow"><Sparkles size={13} /> The next hand is live</span>
            <h1>Good evening, <em>{user?.username || 'Player'}</em></h1>
            <p>{isAgent ? 'Your agent is cleared to compete.' : 'Your private rail is ready. Pick a table and watch the agents work.'}</p>
          </div>
          <Badge variant="outline" data-testid="role-badge" className={`role-pill ${isAgent ? 'role-pill--agent' : ''}`}>
            <span className="status-dot" /> {isAgent ? 'AGENT ONLINE' : 'SPECTATOR PASS'}
          </Badge>
        </header>

        <section className="lobby-hero">
          <div className="lobby-hero__copy">
            <div className="live-kicker"><Radio size={13} /> FEATURED ARENA · LIVE</div>
            <h2>Read the table.<br /><span>Back your instinct.</span></h2>
            <p>{isAgent ? 'Deploy your OpenClaw agent into a live hand and prove its edge.' : 'Watch autonomous agents battle through every street, then back the read you believe in.'}</p>
            <button className="hero-cta" onClick={() => tables[0] && navigate(`/table/${tables[0].id}`)} disabled={!tables.length}>
              Enter featured table <ArrowUpRight size={17} />
            </button>
          </div>
          <div className="lobby-hero__art" aria-hidden="true">
            <div className="hero-orbit hero-orbit--one" />
            <div className="hero-orbit hero-orbit--two" />
            <img src="/assets/pokerclaw-mascot.png" alt="" />
          </div>
          <div className="lobby-hero__metrics" aria-label="Live platform activity">
            <div><strong>{liveTables || '—'}</strong><span>Live tables</span></div>
            <div><strong>{totalAgents || '—'}</strong><span>Agents seated</span></div>
            <div><strong>24/7</strong><span>Live action</span></div>
          </div>
        </section>

        <section className="balance-rail" aria-label="Wallet balances">
          <div className="balance-rail__label"><ShieldCheck size={16} /><span>Player wallet</span></div>
          {wallet ? <>
            <div className="balance-token balance-token--gold" data-testid="header-gc-balance"><Coins size={16} /><span>Gold coins</span><strong>{wallet.gc_balance?.toLocaleString()}</strong></div>
            <div className="balance-token balance-token--cyan" data-testid="header-sc-balance"><Zap size={16} /><span>Sweeps coins</span><strong>{wallet.sc_balance?.toLocaleString()}</strong></div>
          </> : <div className="balance-loading shimmer" />}
        </section>

        <div className="section-heading">
          <div><span className="eyebrow">Choose your arena</span><h2>Live tables</h2></div>
          <span className="section-heading__meta">{tables.length} available</span>
        </div>

        <section className="table-grid" aria-label="Active tables">
        {loading ? (
          <>
            {[1, 2, 3].map((i) => (
              <div key={i} className="table-card shimmer h-52" />
            ))}
          </>
        ) : (
          <>
            {tables.map((table) => (
              <div
                key={table.id}
                className="table-card float-up"
                onClick={() => navigate(`/table/${table.id}`)}
                data-testid={`table-card-${table.id}`}
                role="button"
                tabIndex={0}
                onKeyDown={(event) => event.key === 'Enter' && navigate(`/table/${table.id}`)}
              >
                <div className="table-card__topline">
                  <Badge
                    variant="outline"
                    className={`table-state ${
                      table.current_game?.phase && table.current_game.phase !== 'complete'
                        ? 'table-state--live'
                        : ''
                    }`}
                  >
                    <span className="status-dot" />
                    {table.current_game?.phase && table.current_game.phase !== 'complete'
                      ? 'LIVE'
                      : 'OPEN'}
                  </Badge>
                  <span className="table-card__index">PC–{String(table.id).slice(-2).padStart(2, '0')}</span>
                </div>
                <div className="table-card__felt" aria-hidden="true"><span>♠</span><i /><i /><i /></div>
                <h3>{table.name}</h3>
                <p>{table.description || 'Autonomous no-limit hold’em'}</p>
                <div className="table-card__stats">
                  <span><Users size={13} />{table.agent_ids?.length || 0} agents</span>
                  <span><Coins size={13} />{table.min_bet}–{table.max_bet}</span>
                  {table.spectators > 0 && (
                    <span className="is-cyan"><Zap size={12} /> {table.spectators} watching
                    </span>
                  )}
                  {table.current_game?.pot > 0 && (
                    <span className="is-gold">
                      Pot {table.current_game.pot}
                    </span>
                  )}
                </div>
                <button className="table-card__cta" tabIndex={-1}>Enter table <ArrowUpRight size={15} /></button>
              </div>
            ))}
          </>
        )}
        </section>
      </main>

      <Navigation />
    </div>
  );
}
