import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertTriangle, ArrowDownLeft, ArrowUpRight, Bitcoin, Coins, Copy, Gift,
  LockKeyhole, RefreshCw, Shield, Wallet as WalletIcon, Zap,
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
  const [cryptoInfo, setCryptoInfo] = useState(null);
  const [deposits, setDeposits] = useState([]);
  const [redemptions, setRedemptions] = useState([]);
  const [selectedCrypto, setSelectedCrypto] = useState('btc');
  const [redemptionCrypto, setRedemptionCrypto] = useState('btc');
  const [txHash, setTxHash] = useState('');
  const [redemptionAmount, setRedemptionAmount] = useState('');
  const [payoutAddress, setPayoutAddress] = useState('');
  const [redemptionKey, setRedemptionKey] = useState(() => window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`);
  const [loading, setLoading] = useState(true);
  const [claiming, setClaiming] = useState(false);
  const [excluding, setExcluding] = useState(false);
  const [submittingDeposit, setSubmittingDeposit] = useState(false);
  const [checkingDeposit, setCheckingDeposit] = useState(null);
  const [redeeming, setRedeeming] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const requests = [
        api.get('/wallet'),
        api.get('/wallet/transactions'),
        api.get('/crypto/prices'),
        api.get('/crypto/deposits'),
      ];
      if (!isAgent) {
        requests.push(api.get('/sweepstakes/status'));
        requests.push(api.get('/wallet/redemptions'));
      }
      const results = await Promise.allSettled(requests);
      if (results[0].status === 'rejected') throw results[0].reason;
      if (results[1].status === 'rejected') throw results[1].reason;
      setWallet(results[0].value.data);
      setTransactions(results[1].value.data || []);
      if (results[2].status === 'fulfilled') setCryptoInfo(results[2].value.data);
      if (results[3].status === 'fulfilled') setDeposits(results[3].value.data || []);
      if (!isAgent && results[4]?.status === 'fulfilled') setStatus(results[4].value.data);
      if (!isAgent && results[5]?.status === 'fulfilled') setRedemptions(results[5].value.data || []);
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

  const submitDeposit = async () => {
    if (!txHash.trim()) return;
    setSubmittingDeposit(true);
    try {
      const { data } = await api.post('/crypto/deposit', {
        crypto_type: activeCrypto,
        tx_hash: txHash.trim(),
      });
      setTxHash('');
      toast.success(data.status === 'confirmed'
        ? `${data.sc_credited.toLocaleString()} SC credited`
        : `Deposit found — ${data.confirmations}/${data.required_confirmations} confirmations`);
      await fetchData();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Unable to verify that deposit');
    } finally {
      setSubmittingDeposit(false);
    }
  };

  const checkDeposit = async (depositId) => {
    setCheckingDeposit(depositId);
    try {
      const { data } = await api.post(`/crypto/deposits/${depositId}/confirm`);
      toast.success(data.status === 'confirmed'
        ? (data.sc_credited ? `${data.sc_credited.toLocaleString()} SC credited` : 'Deposit already credited')
        : `Waiting for confirmations: ${data.confirmations}/${data.required_confirmations}`);
      await fetchData();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Unable to refresh deposit');
    } finally {
      setCheckingDeposit(null);
    }
  };

  const submitRedemption = async () => {
    const amount = Number.parseInt(redemptionAmount, 10);
    if (!amount || !activeRedemptionCrypto || !payoutAddress.trim()) return;
    const confirmed = window.confirm(
      `Reserve ${amount.toLocaleString()} SC for ${activeRedemptionCrypto.toUpperCase()} redemption? ` +
      'Confirm the Coinbase asset and network match this address. Crypto transfers cannot be reversed.'
    );
    if (!confirmed) return;
    setRedeeming(true);
    try {
      const { data } = await api.post('/wallet/cashout', {
        amount,
        crypto_type: activeRedemptionCrypto,
        payout_address: payoutAddress.trim(),
      }, { headers: { 'Idempotency-Key': redemptionKey } });
      toast.success(`Redemption submitted: ${data.payout_crypto_amount} ${data.crypto_type.toUpperCase()}`);
      setRedemptionAmount('');
      setPayoutAddress('');
      setRedemptionKey(window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`);
      await fetchData();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Unable to submit redemption');
    } finally {
      setRedeeming(false);
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
  const cryptoAddresses = cryptoInfo?.deposit_addresses || {};
  const supportedCrypto = Object.keys(cryptoAddresses);
  const activeCrypto = supportedCrypto.includes(selectedCrypto) ? selectedCrypto : supportedCrypto[0];
  const cryptoAllowed = isAgent || eligibility?.eligible;
  const redemptionCoins = Object.keys(cryptoInfo?.prices || {});
  const activeRedemptionCrypto = redemptionCoins.includes(redemptionCrypto) ? redemptionCrypto : redemptionCoins[0];
  const redemptionPrice = cryptoInfo?.prices?.[activeRedemptionCrypto]?.usd;
  const redemptionEstimate = redemptionPrice && cryptoInfo?.sc_per_usd && Number(redemptionAmount) > 0
    ? Number(redemptionAmount) / cryptoInfo.sc_per_usd / redemptionPrice
    : 0;

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

      {cryptoInfo?.funding_enabled && activeCrypto && (
        <div className="px-4 mb-5" data-testid="crypto-funding-panel">
          <div className="glass rounded-2xl p-4 border border-[#00F0FF]/20">
            <div className="flex items-start justify-between gap-3 mb-4">
              <div className="flex gap-3">
                <Bitcoin size={21} className="text-[#00F0FF] shrink-0 mt-0.5" />
                <div>
                  <h2 className="text-sm font-bold text-white">Fund SC with crypto</h2>
                  <p className="text-[10px] text-white/45 mt-1 leading-relaxed">
                    On-chain amount is verified by the server. {cryptoInfo.rate}.
                  </p>
                </div>
              </div>
              <span className="text-[9px] font-bold text-green-400 bg-green-500/10 rounded-full px-2 py-1">LIVE</span>
            </div>

            <div className="flex gap-2 mb-3">
              {supportedCrypto.map((coin) => (
                <button
                  key={coin}
                  type="button"
                  onClick={() => setSelectedCrypto(coin)}
                  className={`flex-1 rounded-lg border py-2 text-[10px] font-black uppercase ${
                    activeCrypto === coin
                      ? 'border-[#00F0FF]/50 bg-[#00F0FF]/10 text-[#00F0FF]'
                      : 'border-white/5 bg-white/[0.02] text-white/35'
                  }`}
                >
                  {coin}
                </button>
              ))}
            </div>

            <div className="rounded-xl bg-black/25 border border-white/5 p-3 mb-3">
              <div className="flex items-center justify-between gap-2 mb-1">
                <span className="text-[9px] uppercase tracking-widest text-white/35">Send {activeCrypto.toUpperCase()} to</span>
                <button
                  type="button"
                  onClick={() => {
                    navigator.clipboard?.writeText(cryptoAddresses[activeCrypto]);
                    toast.success('Deposit address copied');
                  }}
                  className="text-[#00F0FF] hover:text-white"
                  aria-label="Copy deposit address"
                >
                  <Copy size={15} />
                </button>
              </div>
              <div className="mono text-[10px] text-white/80 break-all">{cryptoAddresses[activeCrypto]}</div>
              <div className="text-[9px] text-white/30 mt-2">
                Credit after {cryptoInfo.required_confirmations?.[activeCrypto]} network confirmations.
              </div>
            </div>

            <label className="text-[9px] uppercase tracking-widest text-white/35" htmlFor="deposit-tx-hash">
              Transaction hash
            </label>
            <div className="flex gap-2 mt-1.5">
              <input
                id="deposit-tx-hash"
                value={txHash}
                onChange={(event) => setTxHash(event.target.value)}
                placeholder="Paste the on-chain transaction hash"
                className="min-w-0 flex-1 rounded-lg border border-white/10 bg-black/30 px-3 py-2.5 text-xs text-white placeholder:text-white/20 outline-none focus:border-[#00F0FF]/50"
              />
              <Button
                onClick={submitDeposit}
                disabled={!cryptoAllowed || submittingDeposit || txHash.trim().length < 16}
                className="bg-[#00F0FF] hover:bg-[#00d7e5] text-black font-black text-[10px] px-4"
                data-testid="submit-crypto-deposit"
              >
                {submittingDeposit ? 'VERIFYING' : 'VERIFY'}
              </Button>
            </div>
            {!cryptoAllowed && (
              <p className="text-[10px] text-[#FF9BAD] mt-2">Complete age and region verification before funding SC.</p>
            )}

            {deposits.length > 0 && (
              <div className="mt-4 pt-4 border-t border-white/5 space-y-2">
                <div className="text-[9px] uppercase tracking-widest text-white/35">Recent deposits</div>
                {deposits.slice(0, 3).map((deposit) => (
                  <div key={deposit.id} className="flex items-center justify-between gap-3 rounded-lg bg-white/[0.025] p-2.5">
                    <div className="min-w-0">
                      <div className="text-[10px] font-bold text-white">
                        {deposit.amount_crypto} {deposit.crypto_type.toUpperCase()} · {deposit.sc_amount.toLocaleString()} SC
                      </div>
                      <div className={`text-[9px] mt-0.5 ${deposit.status === 'confirmed' ? 'text-green-400' : 'text-[#FFE600]'}`}>
                        {deposit.status === 'confirmed'
                          ? 'CONFIRMED'
                          : `${deposit.confirmations}/${deposit.required_confirmations} CONFIRMATIONS`}
                      </div>
                    </div>
                    {deposit.status !== 'confirmed' && (
                      <button
                        type="button"
                        onClick={() => checkDeposit(deposit.id)}
                        disabled={checkingDeposit === deposit.id}
                        className="text-[#00F0FF] disabled:opacity-40"
                        aria-label="Refresh deposit confirmations"
                      >
                        <RefreshCw size={16} className={checkingDeposit === deposit.id ? 'animate-spin' : ''} />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {!isAgent && (
        <div className="px-4 space-y-3 mb-6">
          <div className="glass rounded-2xl p-4 border border-[#FFE600]/20">
            <div className="flex gap-3">
              <Gift size={20} className="text-[#FFE600] shrink-0 mt-0.5" />
              <div className="flex-1">
                <h2 className="text-sm font-bold text-white">Free daily coins</h2>
                <p className="text-[11px] text-white/40 mt-1 leading-relaxed">
                  No purchase is necessary. Claim {config?.daily_gc_amount?.toLocaleString() || 0} free GC daily.
                  {config?.sc_play_enabled
                    ? ` Eligible players also receive ${config?.daily_sc_amount?.toLocaleString() || 0} promotional SC.`
                    : ' SC distribution is disabled in this build.'}
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

          {config?.redemption_enabled ? (
            <div className="glass rounded-2xl p-4 border border-[#00F0FF]/20" data-testid="crypto-redemption-panel">
              <div className="flex gap-3 mb-4">
                <ArrowUpRight size={20} className="text-[#00F0FF] shrink-0 mt-0.5" />
                <div>
                  <h2 className="text-sm font-bold text-white">Redeem SC to crypto</h2>
                  <p className="text-[10px] text-white/45 mt-1 leading-relaxed">
                    Choose BTC, LTC, or ETH and use that asset's native Coinbase receiving address. Your quote is locked when SC is reserved for review.
                  </p>
                </div>
              </div>

              <div className="flex gap-2 mb-3">
                {redemptionCoins.map((coin) => (
                  <button
                    key={coin}
                    type="button"
                    onClick={() => setRedemptionCrypto(coin)}
                    className={`flex-1 rounded-lg border py-2 text-[10px] font-black uppercase ${
                      activeRedemptionCrypto === coin
                        ? 'border-[#00F0FF]/50 bg-[#00F0FF]/10 text-[#00F0FF]'
                        : 'border-white/5 bg-white/[0.02] text-white/35'
                    }`}
                  >
                    {coin}
                  </button>
                ))}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                <div>
                  <label className="text-[9px] uppercase tracking-widest text-white/35" htmlFor="redemption-amount">SC amount</label>
                  <input
                    id="redemption-amount"
                    type="number"
                    min={config.minimum_redemption_sc}
                    max={wallet?.sc_balance || 0}
                    value={redemptionAmount}
                    onChange={(event) => setRedemptionAmount(event.target.value)}
                    placeholder={`Minimum ${config.minimum_redemption_sc?.toLocaleString()} SC`}
                    className="mt-1.5 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2.5 text-xs text-white placeholder:text-white/20 outline-none focus:border-[#00F0FF]/50"
                  />
                </div>
                <div>
                  <label className="text-[9px] uppercase tracking-widest text-white/35" htmlFor="payout-address">{activeRedemptionCrypto?.toUpperCase()} receiving address</label>
                  <input
                    id="payout-address"
                    value={payoutAddress}
                    onChange={(event) => setPayoutAddress(event.target.value)}
                    placeholder="Paste your Coinbase receive address"
                    className="mt-1.5 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2.5 text-xs text-white placeholder:text-white/20 outline-none focus:border-[#00F0FF]/50"
                  />
                </div>
              </div>

              <div className="flex items-center justify-between gap-3 mt-3">
                <div className="text-[10px] text-white/45">
                  {redemptionEstimate > 0
                    ? `Estimated locked payout: ${redemptionEstimate.toFixed(activeRedemptionCrypto === 'eth' ? 8 : 8)} ${activeRedemptionCrypto.toUpperCase()}`
                    : `${cryptoInfo?.rate || ''}`}
                </div>
                <Button
                  onClick={submitRedemption}
                  disabled={
                    redeeming || !eligibility?.identity_verified || !activeRedemptionCrypto ||
                    Number(redemptionAmount) < config.minimum_redemption_sc ||
                    Number(redemptionAmount) > (wallet?.sc_balance || 0) || !payoutAddress.trim()
                  }
                  className="bg-[#00F0FF] hover:bg-[#00d7e5] text-black font-black text-[10px] px-4"
                  data-testid="submit-crypto-redemption"
                >
                  {redeeming ? 'SUBMITTING' : 'REDEEM'}
                </Button>
              </div>
              {!eligibility?.identity_verified && (
                <p className="text-[10px] text-[#FF9BAD] mt-2">Identity verification is required before redemption.</p>
              )}

              {redemptions.length > 0 && (
                <div className="mt-4 pt-4 border-t border-white/5 space-y-2">
                  <div className="text-[9px] uppercase tracking-widest text-white/35">Redemption history</div>
                  {redemptions.slice(0, 3).map((redemption) => (
                    <div key={redemption.id} className="rounded-lg bg-white/[0.025] p-2.5">
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-[10px] font-bold text-white">
                          {redemption.sc_amount.toLocaleString()} SC → {redemption.payout_crypto_amount} {redemption.crypto_type.toUpperCase()}
                        </span>
                        <span className={`text-[9px] font-bold ${
                          redemption.status === 'paid' ? 'text-green-400' :
                          redemption.status === 'rejected' ? 'text-[#FF6B88]' : 'text-[#FFE600]'
                        }`}>
                          {redemption.status.replace('_', ' ').toUpperCase()}
                        </span>
                      </div>
                      <div className="mono text-[9px] text-white/30 truncate mt-1">{redemption.payout_address}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="glass rounded-2xl p-4 border border-[#FF003C]/20">
              <div className="flex gap-3">
                <LockKeyhole size={19} className="text-[#FF6B88] shrink-0" />
                <div>
                  <h2 className="text-sm font-bold text-white">Redemption locked</h2>
                  <p className="text-[11px] text-white/40 mt-1 leading-relaxed">
                    Prize redemption remains disabled until identity checks, payout controls,
                    geolocation, and jurisdiction-specific rules are configured.
                  </p>
                </div>
              </div>
            </div>
          )}

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
            Agent balances are isolated from human sweepstakes eligibility. Crypto funding and redemption are unavailable in this GC-only release.
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
