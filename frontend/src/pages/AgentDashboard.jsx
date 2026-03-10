import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { Navigation } from '../components/Navigation';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Bot, Zap, Trophy, Copy, Check, TrendingUp, Wallet } from 'lucide-react';
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

export default function AgentDashboard() {
  const { user } = useAuth();
  const [agentData, setAgentData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchAgent = async () => {
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
    };
    fetchAgent();
  }, []);

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

          {/* Stripe button placeholder */}
          <Button
            disabled
            data-testid="buy-sc-stripe-btn"
            className="w-full bg-gradient-to-r from-[#00F0FF] to-[#BD00FF] text-black font-bold rounded-xl py-3 disabled:opacity-40"
          >
            BUY SC WITH CARD (COMING SOON)
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
