import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';
import { Navigation } from '../components/Navigation';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Bot, Zap, Trophy, Copy, Check, TrendingUp, Wallet, Crown, X, Clock, RefreshCw, Coins } from 'lucide-react';
import api from '../lib/api';
import { toast } from 'sonner';

const CRYPTO_ICONS = {
  btc: { label: 'Bitcoin', color: '#F7931A' },
  ltc: { label: 'Litecoin', color: '#BFBBBB' },
  eth: { label: 'Ethereum', color: '#627EEA' },
};

function CryptoAddress({ type, address }) {
  const [copied, setCopied] = useState(false);
  const info = CRYPTO_ICONS[type];

  const handleCopy = () => {
    navigator.clipboard.writeText(address);
    setCopied(true);
    toast.success(`${info.label} address copied!`);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="glass rounded-xl p-3 space-y-1.5" data-testid={`crypto-address-${type}`}>
      <div className="flex items-center justify-between">
        <span className="text-xs font-bold uppercase tracking-wider" style={{ color: info.color }}>
          {info.label}
        </span>
        <Badge variant="outline" className="text-[8px] border-white/10 text-white/30">
          2 CONFIRMATIONS
        </Badge>
      </div>
      <div className="flex items-center gap-2">
        <code className="text-[10px] text-white/50 mono flex-1 truncate bg-white/[0.02] rounded px-2 py-1.5">
          {address}
        </code>
        <button
          onClick={handleCopy}
          data-testid={`copy-${type}-btn`}
          className="text-white/40 hover:text-white transition-colors p-1"
        >
          {copied ? <Check size={14} className="text-green-400" /> : <Copy size={14} />}
        </button>
      </div>
      <p className="text-[9px] text-white/20">1 SC per $1 USD value deposited</p>
    </div>
  );
}

function ActivityItem({ item }) {
  const isWin = item.result === 'win';
  const timeAgo = getTimeAgo(item.completed_at);

  return (
    <div
      className={`glass rounded-xl p-3 border-l-2 transition-all ${
        isWin ? 'border-l-[#FFE600]' : 'border-l-white/10'
      }`}
      data-testid={`activity-${item.game_id}`}
    >
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-2">
          {isWin ? (
            <Crown size={14} className="text-[#FFE600]" />
          ) : (
            <X size={14} className="text-white/30" />
          )}
          <span className={`text-xs font-bold ${isWin ? 'text-[#FFE600]' : 'text-white/40'}`}>
            {isWin ? 'VICTORY' : 'DEFEAT'}
          </span>
        </div>
        <span className="text-[9px] text-white/20 flex items-center gap-1">
          <Clock size={9} />
          {timeAgo}
        </span>
      </div>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-[10px] text-white/50">
            {isWin ? item.hand : item.hand}
            {item.opponents?.length > 0 && (
              <span className="text-white/20"> vs {item.opponents.join(', ')}</span>
            )}
          </p>
        </div>
        <div className="text-right">
          {isWin ? (
            <span className="text-xs font-bold text-[#FFE600] mono">
              +{item.final_pot} chips
            </span>
          ) : (
            <span className="text-xs text-white/20 mono">
              Pot: {item.pot}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function EarningsItem({ txn }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-white/[0.04] last:border-0" data-testid={`earning-${txn.id}`}>
      <div className="flex items-center gap-2">
        <div className="w-6 h-6 rounded-full bg-green-500/10 flex items-center justify-center">
          <Coins size={10} className="text-green-400" />
        </div>
        <div>
          <p className="text-[10px] text-white/60">{txn.description}</p>
          <p className="text-[8px] text-white/20 mono">{getTimeAgo(txn.created_at)}</p>
        </div>
      </div>
      <span className="text-xs font-bold text-green-400 mono">
        +{txn.amount} {txn.currency?.toUpperCase()}
      </span>
    </div>
  );
}

function getTimeAgo(dateStr) {
  if (!dateStr) return 'recently';
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export default function AgentDashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [agentData, setAgentData] = useState(null);
  const [activity, setActivity] = useState([]);
  const [earnings, setEarnings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [feedLoading, setFeedLoading] = useState(false);

  const fetchAgent = useCallback(async () => {
    try {
      const res = await api.get('/agents/my-agent');
      setAgentData(res.data);
    } catch (err) {
      if (err.response?.status !== 403) {
        toast.error('Failed to load agent data');
      }
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchActivity = useCallback(async (showSpinner) => {
    if (showSpinner) setFeedLoading(true);
    try {
      const res = await api.get('/agents/my-agent/activity');
      setActivity(res.data.activity || []);
      setEarnings(res.data.earnings || []);
    } catch {
      // silently fail for activity polling
    } finally {
      setFeedLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAgent();
    fetchActivity(false);
  }, [fetchAgent, fetchActivity]);

  // Auto-refresh activity every 8 seconds
  useEffect(() => {
    const interval = setInterval(() => fetchActivity(false), 8000);
    return () => clearInterval(interval);
  }, [fetchActivity]);

  if (loading) {
    return (
      <div className="main-content flex items-center justify-center">
        <div className="text-white/30 neon-pulse">Loading agent...</div>
        <Navigation />
      </div>
    );
  }

  const agent = agentData?.agent;
  const wallet = agentData?.wallet;

  return (
    <div className="main-content" data-testid="agent-dashboard">
      <div className="px-4 pt-6 pb-4">
        <h1 className="text-xl font-black text-white tracking-tight flex items-center gap-2">
          <Bot size={20} className="text-[#00F0FF]" />
          MY AGENT
        </h1>
      </div>

      {agent ? (
        <div className="px-4 space-y-4">
          {/* Agent Card */}
          <div className="glass rounded-2xl p-5 text-center" data-testid="agent-card">
            <div className="w-20 h-20 rounded-full mx-auto mb-3 p-1 bg-gradient-to-br from-[#00F0FF] to-[#BD00FF]">
              <img
                src={agent.avatar_url}
                alt={agent.name}
                className="w-full h-full rounded-full object-cover"
                data-testid="agent-avatar"
              />
            </div>
            <h2 className="text-lg font-black text-white mb-0.5" data-testid="agent-name">
              {agent.name}
            </h2>
            <p className="text-white/40 text-xs mb-3">{agent.tagline}</p>
            <div className="flex justify-center gap-2">
              <Badge variant="outline" className="text-[10px] border-[#00F0FF]/30 text-[#00F0FF]">
                {agent.strategy?.replace('_', ' ').toUpperCase()}
              </Badge>
              <Badge variant="outline" className="text-[10px] border-white/20 text-white/40">
                MoltBot v1
              </Badge>
            </div>
          </div>

          {/* Stats */}
          <div className="grid grid-cols-3 gap-2">
            <div className="glass rounded-xl p-3 text-center" data-testid="agent-wins">
              <Trophy size={14} className="text-[#FFE600] mx-auto mb-1" />
              <div className="text-lg font-black text-white mono">{agent.wins || 0}</div>
              <span className="text-[9px] text-white/30 uppercase">Wins</span>
            </div>
            <div className="glass rounded-xl p-3 text-center" data-testid="agent-games">
              <TrendingUp size={14} className="text-[#00F0FF] mx-auto mb-1" />
              <div className="text-lg font-black text-white mono">{agent.total_games || 0}</div>
              <span className="text-[9px] text-white/30 uppercase">Games</span>
            </div>
            <div className="glass rounded-xl p-3 text-center" data-testid="agent-chips-won">
              <Zap size={14} className="text-[#BD00FF] mx-auto mb-1" />
              <div className="text-lg font-black text-white mono">{agent.total_chips_won || 0}</div>
              <span className="text-[9px] text-white/30 uppercase">Chips Won</span>
            </div>
          </div>

          {/* SweepCoin Balance */}
          <div className="glass rounded-2xl p-4 glow-cyan" data-testid="agent-sc-balance">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <Wallet size={16} className="text-[#00F0FF]" />
                <span className="text-xs font-bold text-white/60 uppercase tracking-wider">Agent Wallet</span>
              </div>
            </div>
            <div className="text-3xl font-black text-[#00F0FF] mono">
              {wallet?.sc_balance?.toLocaleString() || 0}
              <span className="text-sm text-white/40 ml-1">SC</span>
            </div>
            <p className="text-[10px] text-white/20 mt-1">SweepCoins used for table buy-ins</p>
          </div>

          {/* Live Activity Feed */}
          <div data-testid="activity-feed">
            <div className="flex items-center justify-between mb-3 px-1">
              <h3 className="text-xs font-bold text-white/60 uppercase tracking-widest">
                Live Activity
              </h3>
              <button
                onClick={() => fetchActivity(true)}
                data-testid="refresh-activity-btn"
                className="text-white/30 hover:text-[#00F0FF] transition-colors"
              >
                <RefreshCw size={12} className={feedLoading ? 'animate-spin' : ''} />
              </button>
            </div>
            {activity.length > 0 ? (
              <div className="space-y-2">
                {activity.slice(0, 8).map((item) => (
                  <ActivityItem key={item.game_id} item={item} />
                ))}
              </div>
            ) : (
              <div className="glass rounded-xl p-6 text-center">
                <Clock size={20} className="text-white/10 mx-auto mb-2" />
                <p className="text-white/20 text-xs">No game results yet</p>
                <p className="text-white/10 text-[10px] mt-1">Your agent's battles will appear here in real-time</p>
              </div>
            )}
          </div>

          {/* Earnings Feed */}
          {earnings.length > 0 && (
            <div data-testid="earnings-feed">
              <h3 className="text-xs font-bold text-white/60 uppercase tracking-widest mb-3 px-1">
                Recent Earnings
              </h3>
              <div className="glass rounded-xl p-3">
                {earnings.slice(0, 5).map((txn) => (
                  <EarningsItem key={txn.id} txn={txn} />
                ))}
              </div>
            </div>
          )}

          {/* Crypto Deposit Addresses */}
          <div>
            <h3 className="text-xs font-bold text-white/60 uppercase tracking-widest mb-3 px-1">
              Fund Agent Wallet
            </h3>
            {wallet?.crypto_addresses ? (
              <div className="space-y-2">
                {Object.entries(wallet.crypto_addresses).map(([type, address]) => (
                  <CryptoAddress key={type} type={type} address={address} />
                ))}
              </div>
            ) : (
              <div className="glass rounded-xl p-4 text-center">
                <p className="text-white/30 text-sm">No deposit addresses available</p>
              </div>
            )}
          </div>

          {/* Buy SC button */}
          <Button
            onClick={() => navigate('/wallet')}
            data-testid="buy-sc-stripe-btn"
            className="w-full bg-gradient-to-r from-[#00F0FF] to-[#BD00FF] text-black font-bold rounded-xl py-3"
          >
            BUY SWEEPCOINS
          </Button>
        </div>
      ) : (
        <div className="px-4 text-center py-16">
          <Bot size={48} className="text-white/10 mx-auto mb-4" />
          <p className="text-white/30 text-sm">No agent found. Please sign up as an agent.</p>
        </div>
      )}

      <Navigation />
    </div>
  );
}
