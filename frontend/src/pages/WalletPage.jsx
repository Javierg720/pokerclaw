import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import { useSearchParams } from 'react-router-dom';
import { Navigation } from '../components/Navigation';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import {
  Wallet as WalletIcon, ArrowUpRight, ArrowDownLeft, Coins, Zap,
  CreditCard, Copy, Check, Loader2, TrendingUp, TrendingDown, Clock
} from 'lucide-react';
import api from '../lib/api';
import { toast } from 'sonner';

const CRYPTO_META = {
  btc: { label: 'Bitcoin', color: '#F7931A', symbol: 'BTC' },
  ltc: { label: 'Litecoin', color: '#BFBBBB', symbol: 'LTC' },
  eth: { label: 'Ethereum', color: '#627EEA', symbol: 'ETH' },
};

function CryptoDepositCard({ type, address, price, onDeposit }) {
  const [copied, setCopied] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [txHash, setTxHash] = useState('');
  const [amount, setAmount] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const info = CRYPTO_META[type];

  const handleCopy = () => {
    navigator.clipboard.writeText(address);
    setCopied(true);
    toast.success(`${info.label} address copied!`);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleSubmit = async () => {
    if (!txHash.trim() || !amount || parseFloat(amount) <= 0) {
      toast.error('Enter a valid TX hash and amount');
      return;
    }
    setSubmitting(true);
    try {
      await onDeposit(type, txHash.trim(), parseFloat(amount));
      setTxHash('');
      setAmount('');
      setShowForm(false);
    } finally {
      setSubmitting(false);
    }
  };

  const scPreview = price && amount ? Math.floor(parseFloat(amount) * price * 100) : 0;

  return (
    <div className="glass rounded-xl p-3 space-y-2" data-testid={`wallet-crypto-${type}`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-full flex items-center justify-center" style={{ background: `${info.color}20` }}>
            <span className="text-[10px] font-black" style={{ color: info.color }}>{info.symbol}</span>
          </div>
          <div>
            <span className="text-xs font-bold text-white">{info.label}</span>
            {price > 0 && (
              <span className="text-[10px] text-white/30 ml-2 mono">${price.toLocaleString()}</span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <button onClick={handleCopy} className="text-white/30 hover:text-white transition-colors p-1" data-testid={`copy-${type}-btn`}>
            {copied ? <Check size={12} className="text-green-400" /> : <Copy size={12} />}
          </button>
          <button
            onClick={() => setShowForm(!showForm)}
            data-testid={`deposit-${type}-toggle`}
            className={`text-[9px] font-bold px-2 py-1 rounded-md transition-all ${
              showForm ? 'bg-white/10 text-white' : 'bg-white/[0.03] text-white/30 hover:text-white/60'
            }`}
          >
            DEPOSIT
          </button>
        </div>
      </div>

      <code className="text-[9px] text-white/30 mono block truncate bg-white/[0.02] rounded px-2 py-1.5">
        {address}
      </code>

      {showForm && (
        <div className="space-y-2 pt-1 border-t border-white/[0.05]">
          <Input
            placeholder="Transaction hash"
            value={txHash}
            onChange={(e) => setTxHash(e.target.value)}
            data-testid={`deposit-${type}-txhash`}
            className="bg-white/[0.03] border-white/10 text-white text-xs placeholder:text-white/15 h-8"
          />
          <div className="flex gap-2">
            <Input
              type="number"
              step="any"
              placeholder={`Amount in ${info.symbol}`}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              data-testid={`deposit-${type}-amount`}
              className="bg-white/[0.03] border-white/10 text-white text-xs placeholder:text-white/15 h-8 flex-1"
            />
            <Button
              onClick={handleSubmit}
              disabled={submitting}
              data-testid={`deposit-${type}-submit`}
              className="bg-white/10 hover:bg-white/20 text-white text-xs h-8 px-3"
            >
              {submitting ? <Loader2 size={12} className="animate-spin" /> : 'SUBMIT'}
            </Button>
          </div>
          {scPreview > 0 && (
            <p className="text-[10px] text-[#00F0FF]/60 mono">
              = ~{scPreview.toLocaleString()} SC
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function DepositStatus({ deposit, onConfirm }) {
  const info = CRYPTO_META[deposit.crypto_type];
  const isPending = deposit.status === 'pending';

  return (
    <div className={`glass rounded-lg p-3 flex items-center justify-between border-l-2 ${
      isPending ? 'border-l-[#FFE600]/50' : 'border-l-green-500/50'
    }`} data-testid={`deposit-status-${deposit.id}`}>
      <div className="flex items-center gap-2.5">
        <div className="w-7 h-7 rounded-full flex items-center justify-center" style={{ background: `${info.color}20` }}>
          <span className="text-[9px] font-black" style={{ color: info.color }}>{info.symbol}</span>
        </div>
        <div>
          <p className="text-xs text-white font-medium">
            {deposit.amount_crypto} {info.symbol}
            <span className="text-white/30 ml-1">(${deposit.usd_value})</span>
          </p>
          <p className="text-[9px] text-white/20 mono flex items-center gap-1">
            <Clock size={8} />
            {deposit.confirmations}/{deposit.required_confirmations} confirmations
          </p>
        </div>
      </div>
      <div className="text-right flex items-center gap-2">
        <span className="text-xs font-bold text-[#00F0FF] mono">{deposit.sc_amount.toLocaleString()} SC</span>
        {isPending && (
          <button
            onClick={() => onConfirm(deposit.id)}
            data-testid={`confirm-deposit-${deposit.id}`}
            className="text-[8px] font-bold px-2 py-1 rounded bg-[#FFE600]/10 text-[#FFE600] hover:bg-[#FFE600]/20 transition-all"
          >
            +1 CONF
          </button>
        )}
        {!isPending && (
          <Badge variant="outline" className="text-[8px] border-green-500/30 text-green-400">CREDITED</Badge>
        )}
      </div>
    </div>
  );
}

export default function WalletPage() {
  const { isAgent } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [wallet, setWallet] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [packages, setPackages] = useState([]);
  const [cryptoPrices, setCryptoPrices] = useState({});
  const [deposits, setDeposits] = useState([]);
  const [loading, setLoading] = useState(true);
  const [checkoutLoading, setCheckoutLoading] = useState(null);
  const [pollingStatus, setPollingStatus] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      const requests = [
        api.get('/wallet'),
        api.get('/wallet/transactions'),
        api.get('/stripe/packages'),
        api.get('/crypto/prices'),
      ];
      if (isAgent) requests.push(api.get('/crypto/deposits'));

      const results = await Promise.all(requests);
      setWallet(results[0].data);
      setTransactions(results[1].data);
      setPackages(results[2].data);
      setCryptoPrices(results[3].data.prices || {});
      if (isAgent && results[4]) setDeposits(results[4].data || []);
    } catch {
      toast.error('Failed to load wallet');
    } finally {
      setLoading(false);
    }
  }, [isAgent]);

  const pollPaymentStatus = useCallback(async (sessionId, attempts = 0) => {
    if (attempts >= 8) {
      setPollingStatus(null);
      toast.error('Payment status check timed out. Please refresh.');
      return;
    }
    setPollingStatus('checking');
    try {
      const res = await api.get(`/stripe/status/${sessionId}`);
      if (res.data.payment_status === 'paid') {
        setPollingStatus('paid');
        toast.success(`+${res.data.sc_amount} SweepCoins added!`);
        fetchData();
        setSearchParams({});
        setTimeout(() => setPollingStatus(null), 3000);
        return;
      }
      setTimeout(() => pollPaymentStatus(sessionId, attempts + 1), 2000);
    } catch {
      setTimeout(() => pollPaymentStatus(sessionId, attempts + 1), 2000);
    }
  }, [setSearchParams, fetchData]);

  useEffect(() => { fetchData(); }, [fetchData]);

  useEffect(() => {
    const sessionId = searchParams.get('session_id');
    const status = searchParams.get('status');
    if (sessionId && status === 'success') {
      pollPaymentStatus(sessionId);
    } else if (status === 'cancelled') {
      toast.info('Payment cancelled');
      setSearchParams({});
    }
  }, [searchParams, pollPaymentStatus, setSearchParams]);

  const handleStripeCheckout = async (packageId) => {
    setCheckoutLoading(packageId);
    try {
      const res = await api.post('/stripe/checkout', {
        package_id: packageId,
        origin_url: window.location.origin,
      });
      window.location.href = res.data.url;
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Checkout failed');
      setCheckoutLoading(null);
    }
  };

  const handleCryptoDeposit = async (cryptoType, txHash, amountCrypto) => {
    try {
      const res = await api.post('/crypto/deposit', {
        crypto_type: cryptoType,
        tx_hash: txHash,
        amount_crypto: amountCrypto,
      });
      toast.success(res.data.message);
      fetchData();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Deposit failed');
    }
  };

  const handleConfirmDeposit = async (depositId) => {
    try {
      const res = await api.post(`/crypto/deposits/${depositId}/confirm`);
      if (res.data.status === 'confirmed') {
        toast.success(`+${res.data.sc_credited.toLocaleString()} SC credited!`);
      } else {
        toast.info(`Confirmation ${res.data.confirmations}/${res.data.required} received`);
      }
      fetchData();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Confirmation failed');
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

  const pendingDeposits = deposits.filter(d => d.status === 'pending');
  const confirmedDeposits = deposits.filter(d => d.status === 'confirmed');

  return (
    <div className="main-content" data-testid="wallet-page">
      <div className="px-4 pt-6 pb-4">
        <h1 className="text-xl font-black text-white tracking-tight flex items-center gap-2">
          <WalletIcon size={20} className="text-[#FF003C]" />
          WALLET
        </h1>
      </div>

      {/* Payment Status Banner */}
      {pollingStatus && (
        <div className={`mx-4 mb-4 rounded-xl p-3 text-center text-sm font-bold ${
          pollingStatus === 'paid' ? 'bg-green-500/20 text-green-400' : 'bg-[#00F0FF]/10 text-[#00F0FF]'
        }`} data-testid="payment-status-banner">
          {pollingStatus === 'paid' ? 'Payment successful! SweepCoins credited.' : (
            <span className="flex items-center justify-center gap-2">
              <Loader2 size={14} className="animate-spin" /> Verifying payment...
            </span>
          )}
        </div>
      )}

      {/* Balances */}
      <div className="px-4 grid grid-cols-2 gap-3 mb-6">
        {!isAgent && (
          <div className="glass rounded-2xl p-4 glow-gold" data-testid="gc-balance-card">
            <div className="flex items-center gap-2 mb-2">
              <Coins size={16} className="text-[#FFE600]" />
              <span className="text-[10px] text-white/40 uppercase tracking-widest">Gold Coins</span>
            </div>
            <div className="text-2xl font-black text-[#FFE600] mono">{wallet?.gc_balance?.toLocaleString() || 0}</div>
          </div>
        )}
        <div className={`glass rounded-2xl p-4 glow-cyan ${isAgent ? 'col-span-2' : ''}`} data-testid="sc-balance-card">
          <div className="flex items-center gap-2 mb-2">
            <Zap size={16} className="text-[#00F0FF]" />
            <span className="text-[10px] text-white/40 uppercase tracking-widest">
              {isAgent ? 'Agent SweepCoins' : 'Sweep Coins'}
            </span>
          </div>
          <div className="text-2xl font-black text-[#00F0FF] mono">{wallet?.sc_balance?.toLocaleString() || 0}</div>
        </div>
      </div>

      {/* Live Crypto Prices */}
      {isAgent && Object.keys(cryptoPrices).length > 0 && (
        <div className="px-4 mb-4">
          <div className="flex gap-2">
            {Object.entries(cryptoPrices).map(([key, p]) => {
              const info = CRYPTO_META[key];
              const isUp = (p.change_24h || 0) >= 0;
              return (
                <div key={key} className="glass rounded-lg p-2 flex-1 text-center" data-testid={`price-${key}`}>
                  <span className="text-[9px] font-bold" style={{ color: info.color }}>{info.symbol}</span>
                  <div className="text-xs font-bold text-white mono">${p.usd?.toLocaleString()}</div>
                  <div className={`text-[8px] flex items-center justify-center gap-0.5 ${isUp ? 'text-green-400' : 'text-red-400'}`}>
                    {isUp ? <TrendingUp size={8} /> : <TrendingDown size={8} />}
                    {Math.abs(p.change_24h || 0).toFixed(1)}%
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Crypto Deposit (Agent only) */}
      {isAgent && wallet?.crypto_addresses && (
        <div className="px-4 mb-6">
          <h3 className="text-xs font-bold text-white/60 uppercase tracking-widest mb-3">
            Deposit Crypto
          </h3>
          <div className="space-y-2">
            {Object.entries(wallet.crypto_addresses).map(([type, address]) => (
              <CryptoDepositCard
                key={type}
                type={type}
                address={address}
                price={cryptoPrices[type]?.usd || 0}
                onDeposit={handleCryptoDeposit}
              />
            ))}
          </div>
          <p className="text-[9px] text-white/20 text-center mt-2">100 SC per $1 USD value. Credits after 2 confirmations.</p>
        </div>
      )}

      {/* Pending Deposits */}
      {isAgent && pendingDeposits.length > 0 && (
        <div className="px-4 mb-6">
          <h3 className="text-xs font-bold text-[#FFE600]/60 uppercase tracking-widest mb-3">
            Pending Deposits ({pendingDeposits.length})
          </h3>
          <div className="space-y-2">
            {pendingDeposits.map(d => (
              <DepositStatus key={d.id} deposit={d} onConfirm={handleConfirmDeposit} />
            ))}
          </div>
        </div>
      )}

      {/* Confirmed Deposits */}
      {isAgent && confirmedDeposits.length > 0 && (
        <div className="px-4 mb-6">
          <h3 className="text-xs font-bold text-green-400/60 uppercase tracking-widest mb-3">
            Confirmed Deposits
          </h3>
          <div className="space-y-2">
            {confirmedDeposits.slice(0, 5).map(d => (
              <DepositStatus key={d.id} deposit={d} onConfirm={handleConfirmDeposit} />
            ))}
          </div>
        </div>
      )}

      {/* Stripe SC Packages */}
      <div className="px-4 mb-6">
        <h3 className="text-xs font-bold text-white/60 uppercase tracking-widest mb-3">Buy SweepCoins</h3>
        <div className="grid grid-cols-2 gap-2">
          {packages.map((pkg) => (
            <button
              key={pkg.id}
              onClick={() => handleStripeCheckout(pkg.id)}
              disabled={checkoutLoading === pkg.id}
              data-testid={`stripe-pkg-${pkg.id}`}
              className="glass rounded-xl p-4 text-left transition-all hover:border-[#FF003C]/30 border border-white/5 disabled:opacity-50"
            >
              <div className="flex items-center gap-1.5 mb-1.5">
                <Zap size={14} className="text-[#00F0FF]" />
                <span className="text-base font-black text-[#00F0FF]">{pkg.sc_amount.toLocaleString()} SC</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-white/40 font-semibold">${pkg.price_usd}</span>
                <div className="flex items-center gap-1 text-[9px] text-white/20">
                  <CreditCard size={10} />
                  {checkoutLoading === pkg.id ? <Loader2 size={10} className="animate-spin" /> : 'CARD'}
                </div>
              </div>
            </button>
          ))}
        </div>
      </div>

      <div className="px-4 mb-6">
        <div className="glass rounded-xl p-3 text-center text-[10px] text-white/30">
          PokerClaw credits are currently for in-app play only. Cashout is disabled.
        </div>
      </div>

      {/* Transactions */}
      <div className="px-4 mb-6">
        <h3 className="text-xs font-bold text-white/60 uppercase tracking-widest mb-3">Transaction History</h3>
        <div className="space-y-2">
          {transactions.length === 0 ? (
            <p className="text-white/20 text-sm text-center py-4">No transactions yet</p>
          ) : (
            transactions.slice(0, 20).map((txn) => (
              <div key={txn.id} className="glass rounded-lg p-3 flex items-center justify-between" data-testid={`txn-${txn.id}`}>
                <div className="flex items-center gap-3">
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
                    txn.amount > 0 ? 'bg-green-500/10' : 'bg-red-500/10'
                  }`}>
                    {txn.amount > 0 ? <ArrowDownLeft size={14} className="text-green-400" /> : <ArrowUpRight size={14} className="text-red-400" />}
                  </div>
                  <div>
                    <p className="text-xs text-white font-medium">{txn.description}</p>
                    <p className="text-[10px] text-white/30 mono">{new Date(txn.created_at).toLocaleDateString()}</p>
                  </div>
                </div>
                <span className={`text-sm font-bold mono ${txn.amount > 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {txn.amount > 0 ? '+' : ''}{txn.amount} {txn.currency?.toUpperCase()}
                </span>
              </div>
            ))
          )}
        </div>
      </div>

      <Navigation />
    </div>
  );
}
