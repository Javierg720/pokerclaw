import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertTriangle, ArrowDownLeft, ArrowUpRight, Coins, Gift,
  LockKeyhole, Shield, Wallet as WalletIcon, Zap,
} from 'lucide-react';
import { toast } from 'sonner';

import { Navigation } from '../components/Navigation';
import { Button } from '../components/ui/button';
import { useAuth } from '../context/AuthContext';
import api from '../lib/api';

function BalanceCard({ icon: Icon, label, value, color, note, testId }) {
  return (
    <div className="glass rounded-2xl p-4 border border-white/5" data-testid={testId}>
      <div className="flex items-center gap-2 mb-2">
        <Icon size={16} style={{ color }} />
        <span className="text-[10px] text-white/40 uppercase tracking-widest">{label}</span>
      </div>
      <div className="text-2xl font-black mono" style={{ color }}>
        {(value || 0).toLocaleString()}
      </div>
      <p className="text-[9px] text-white/30 mt-2 leading-relaxed">{note}</p>
    </div>
  );
}

export default function WalletPage() {
  const { isAgent } = useAuth();
  const [wallet, setWallet] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [claiming, setClaiming] = useState(false);
  const [excluding, setExcluding] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const requests = [api.get('/wallet'), api.get('/wallet/transactions')];
      if (!isAgent) requests.push(api.get('/sweepstakes/status'));
      const results = await Promise.all(requests);
      setWallet(results[0].data);
      setTransactions(results[1].data || []);
      if (!isAgent) setStatus(results[2].data);
    } catch {
      toast.error('Failed to load wallet');
    } finally {
      setLoading(false);
    }
  }, [isAgent]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const claimDailyCoins = async () => {
    setClaiming(true);
    try {
      const { data } = await api.post('/sweepstakes/daily-claim');
      const credits = [`${data.gc_credited.toLocaleString()} GC`];
      if (data.sc_credited) credits.push(`${data.sc_credited.toLocaleString()} SC`);
      toast.success(`Daily free coins claimed: ${credits.join(' + ')}`);
      await fetchData();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Daily coins are not available yet');
    } finally {
      setClaiming(false);
    }
  };

  const selfExclude = async () => {
    const confirmed = window.confirm(
      'Permanently self-exclude this account from Sweepstakes Coin play? This cannot be reversed in the app.'
    );
    if (!confirmed) return;
    setExcluding(true);
    try {
      await api.post('/sweepstakes/self-exclude', { days: null });
      toast.success('Self-exclusion is active');
      await fetchData();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Unable to apply self-exclusion');
    } finally {
      setExcluding(false);
    }
  };

  if (loading) {
    return (
      <div className="main-content flex items-center justify-center">
        <div className="text-white/30">Loading...</div>
        <Navigation />
      </div>
    );
  }

  const config = status?.config;
  const eligibility = status?.eligibility;

  return (
    <div className="main-content" data-testid="wallet-page">
      <div className="px-4 pt-6 pb-4">
        <h1 className="text-xl font-black text-white tracking-tight flex items-center gap-2">
          <WalletIcon size={20} className="text-[#FF003C]" />
          {isAgent ? 'AGENT BANK' : 'SOCIAL WALLET'}
        </h1>
      </div>

      <div className="px-4 grid grid-cols-2 gap-3 mb-5">
        <BalanceCard
          icon={Coins}
          label={isAgent ? 'Agent Chips' : 'Gold Coins'}
          value={wallet?.gc_balance}
          color="#FFE600"
          note={isAgent ? 'Agent gameplay credits.' : 'Entertainment only. Never redeemable for cash or prizes.'}
          testId="gc-balance-card"
        />
        <BalanceCard
          icon={Zap}
          label={isAgent ? 'Agent SC' : 'Sweepstakes Coins'}
          value={wallet?.sc_balance}
          color="#00F0FF"
          note={isAgent ? 'Internal agent gameplay credits.' : 'Promotional play only. Eligibility is required before SC play.'}
          testId="sc-balance-card"
        />
      </div>

      {!isAgent && (
        <div className="px-4 space-y-3 mb-6">
          <div className="glass rounded-2xl p-4 border border-[#FFE600]/20">
            <div className="flex gap-3">
              <Gift size={20} className="text-[#FFE600] shrink-0 mt-0.5" />
              <div className="flex-1">
                <h2 className="text-sm font-bold text-white">Free daily coins</h2>
                <p className="text-[11px] text-white/40 mt-1 leading-relaxed">
                  No purchase is necessary. Claim {config?.daily_gc_amount?.toLocaleString() || 0} free GC daily.
                  Eligible players also receive {config?.daily_sc_amount?.toLocaleString() || 0} promotional SC.
                </p>
                <Button
                  onClick={claimDailyCoins}
                  disabled={claiming}
                  data-testid="daily-free-claim"
                  className="mt-3 bg-[#FFE600] hover:bg-[#e5cf00] text-black font-black text-xs"
                >
                  {claiming ? 'CLAIMING...' : 'CLAIM FREE COINS'}
                </Button>
              </div>
            </div>
          </div>

          <div className="glass rounded-2xl p-4 border border-white/5">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Shield size={17} className="text-[#00F0FF]" />
                <h2 className="text-sm font-bold text-white">Sweepstakes access</h2>
              </div>
              <span className={`text-[9px] font-bold px-2 py-1 rounded-full ${
                config?.sc_play_enabled && eligibility?.eligible
                  ? 'bg-green-500/10 text-green-400'
                  : 'bg-[#FF003C]/10 text-[#FF6B88]'
              }`}>
                {config?.sc_play_enabled && eligibility?.eligible ? 'ELIGIBLE' : 'LOCKED'}
              </span>
            </div>
            <div className="grid grid-cols-3 gap-2 text-center">
              <div className="bg-white/[0.03] rounded-lg p-2">
                <div className="text-[9px] text-white/30">AGE</div>
                <div className="text-[10px] font-bold text-white/70 mt-1">{eligibility?.age_verified ? 'VERIFIED' : 'REQUIRED'}</div>
              </div>
              <div className="bg-white/[0.03] rounded-lg p-2">
                <div className="text-[9px] text-white/30">REGION</div>
                <div className="text-[10px] font-bold text-white/70 mt-1">{eligibility?.jurisdiction_allowed ? 'ALLOWED' : 'REQUIRED'}</div>
              </div>
              <div className="bg-white/[0.03] rounded-lg p-2">
                <div className="text-[9px] text-white/30">PLAY</div>
                <div className="text-[10px] font-bold text-white/70 mt-1">{config?.sc_play_enabled ? 'ON' : 'OFF'}</div>
              </div>
            </div>
          </div>

          <div className="glass rounded-2xl p-4 border border-[#FF003C]/20">
            <div className="flex gap-3">
              <LockKeyhole size={19} className="text-[#FF6B88] shrink-0" />
              <div>
                <h2 className="text-sm font-bold text-white">Funding and redemption locked</h2>
                <p className="text-[11px] text-white/40 mt-1 leading-relaxed">
                  Card, crypto, and cashout flows are disabled until an approved provider,
                  identity checks, geolocation, and jurisdiction-specific rules are configured.
                </p>
              </div>
            </div>
          </div>

          <div className="flex items-center justify-between px-1 text-[10px]">
            <Link to="/official-rules" className="text-[#00F0FF] hover:underline">Official Rules & eligibility</Link>
            <button
              onClick={selfExclude}
              disabled={excluding || eligibility?.self_excluded}
              className="text-white/35 hover:text-[#FF6B88] disabled:opacity-50"
              data-testid="self-exclude-button"
            >
              {eligibility?.self_excluded ? 'Self-exclusion active' : 'Self-exclude'}
            </button>
          </div>
        </div>
      )}

      {isAgent && (
        <div className="px-4 mb-6">
          <div className="glass rounded-xl p-4 text-[11px] text-white/40 leading-relaxed flex gap-3">
            <AlertTriangle size={18} className="text-[#FFE600] shrink-0" />
            Agent balances are isolated from human sweepstakes eligibility and cannot be funded or redeemed through this build.
          </div>
        </div>
      )}

      <div className="px-4 mb-6">
        <h3 className="text-xs font-bold text-white/60 uppercase tracking-widest mb-3">Transaction History</h3>
        <div className="space-y-2">
          {transactions.length === 0 ? (
            <p className="text-white/20 text-sm text-center py-4">No transactions yet</p>
          ) : transactions.slice(0, 20).map((txn) => (
            <div key={txn.id} className="glass rounded-lg p-3 flex items-center justify-between" data-testid={`txn-${txn.id}`}>
              <div className="flex items-center gap-3 min-w-0">
                <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${txn.amount > 0 ? 'bg-green-500/10' : 'bg-red-500/10'}`}>
                  {txn.amount > 0 ? <ArrowDownLeft size={14} className="text-green-400" /> : <ArrowUpRight size={14} className="text-red-400" />}
                </div>
                <div className="min-w-0">
                  <p className="text-xs text-white font-medium truncate">{txn.description}</p>
                  <p className="text-[10px] text-white/30 mono">{new Date(txn.created_at).toLocaleDateString()}</p>
                </div>
              </div>
              <span className={`text-sm font-bold mono shrink-0 ${txn.amount > 0 ? 'text-green-400' : 'text-red-400'}`}>
                {txn.amount > 0 ? '+' : ''}{txn.amount} {txn.currency?.toUpperCase()}
              </span>
            </div>
          ))}
        </div>
      </div>

      <Navigation />
    </div>
  );
}
