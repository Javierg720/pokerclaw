import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import { useSearchParams } from 'react-router-dom';
import { Navigation } from '../components/Navigation';
import { Button } from '../components/ui/button';
import { Wallet as WalletIcon, ArrowUpRight, ArrowDownLeft, Coins, Zap, CreditCard, Copy, Check, Loader2 } from 'lucide-react';
import api from '../lib/api';
import { toast } from 'sonner';

const CRYPTO_ICONS = {
  btc: { label: 'Bitcoin', color: '#F7931A' },
  ltc: { label: 'Litecoin', color: '#BFBBBB' },
  eth: { label: 'Ethereum', color: '#627EEA' },
};

function CryptoDepositCard({ type, address }) {
  const [copied, setCopied] = useState(false);
  const info = CRYPTO_ICONS[type];

  const handleCopy = () => {
    navigator.clipboard.writeText(address);
    setCopied(true);
    toast.success(`${info.label} address copied!`);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="flex items-center gap-2 glass rounded-lg p-2.5" data-testid={`wallet-crypto-${type}`}>
      <div className="w-7 h-7 rounded-full flex items-center justify-center" style={{ background: `${info.color}20` }}>
        <span className="text-[10px] font-black" style={{ color: info.color }}>
          {type.toUpperCase()}
        </span>
      </div>
      <code className="text-[9px] text-white/40 mono flex-1 truncate">{address}</code>
      <button onClick={handleCopy} className="text-white/30 hover:text-white transition-colors p-0.5">
        {copied ? <Check size={12} className="text-green-400" /> : <Copy size={12} />}
      </button>
    </div>
  );
}

export default function WalletPage() {
  const { isAgent } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [wallet, setWallet] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [packages, setPackages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [checkoutLoading, setCheckoutLoading] = useState(null);
  const [pollingStatus, setPollingStatus] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      const [walletRes, txnRes, pkgRes] = await Promise.all([
        api.get('/wallet'),
        api.get('/wallet/transactions'),
        api.get('/stripe/packages'),
      ]);
      setWallet(walletRes.data);
      setTransactions(txnRes.data);
      setPackages(pkgRes.data);
    } catch {
      toast.error('Failed to load wallet');
    } finally {
      setLoading(false);
    }
  }, []);

  // Poll payment status after returning from Stripe
  const pollPaymentStatus = useCallback(async (sessionId, attempts = 0) => {
    const maxAttempts = 8;
    if (attempts >= maxAttempts) {
      setPollingStatus(null);
      toast.error('Payment status check timed out. Please refresh the page.');
      return;
    }

    setPollingStatus('checking');
    try {
      const res = await api.get(`/stripe/status/${sessionId}`);
      if (res.data.payment_status === 'paid') {
        setPollingStatus('paid');
        toast.success(`+${res.data.sc_amount} SweepCoins added to your wallet!`);
        // Refresh wallet
        const [walletRes, txnRes] = await Promise.all([
          api.get('/wallet'),
          api.get('/wallet/transactions'),
        ]);
        setWallet(walletRes.data);
        setTransactions(txnRes.data);
        // Clean URL params
        setSearchParams({});
        setTimeout(() => setPollingStatus(null), 3000);
        return;
      }
      // Keep polling
      setTimeout(() => pollPaymentStatus(sessionId, attempts + 1), 2000);
    } catch {
      setTimeout(() => pollPaymentStatus(sessionId, attempts + 1), 2000);
    }
  }, [setSearchParams]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Check for return from Stripe
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
      // Redirect to Stripe
      window.location.href = res.data.url;
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Checkout failed');
      setCheckoutLoading(null);
    }
  };

  const handleCashout = async () => {
    if (!wallet || wallet.sc_balance < 100) {
      toast.error('Minimum cashout: 100 SC');
      return;
    }
    try {
      const res = await api.post('/wallet/cashout', { amount: wallet.sc_balance });
      setWallet(res.data.wallet);
      toast.success('Cashout initiated! Crypto transfer pending.');
      const txnRes = await api.get('/wallet/transactions');
      setTransactions(txnRes.data);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Cashout failed');
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
          pollingStatus === 'paid'
            ? 'bg-green-500/20 text-green-400'
            : 'bg-[#00F0FF]/10 text-[#00F0FF]'
        }`} data-testid="payment-status-banner">
          {pollingStatus === 'paid' ? (
            'Payment successful! SweepCoins credited.'
          ) : (
            <span className="flex items-center justify-center gap-2">
              <Loader2 size={14} className="animate-spin" />
              Verifying payment...
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
            <div className="text-2xl font-black text-[#FFE600] mono">
              {wallet?.gc_balance?.toLocaleString() || 0}
            </div>
            <p className="text-[10px] text-white/20 mt-1">Free play currency</p>
          </div>
        )}
        <div className={`glass rounded-2xl p-4 glow-cyan ${isAgent ? 'col-span-2' : ''}`} data-testid="sc-balance-card">
          <div className="flex items-center gap-2 mb-2">
            <Zap size={16} className="text-[#00F0FF]" />
            <span className="text-[10px] text-white/40 uppercase tracking-widest">
              {isAgent ? 'Agent SweepCoins' : 'Sweep Coins'}
            </span>
          </div>
          <div className="text-2xl font-black text-[#00F0FF] mono">
            {wallet?.sc_balance?.toLocaleString() || 0}
          </div>
          <p className="text-[10px] text-white/20 mt-1">
            {isAgent ? 'Used for table buy-ins & redeemable' : 'Redeemable to crypto'}
          </p>
        </div>
      </div>

      {/* Crypto Deposit Addresses (Agent only) */}
      {isAgent && wallet?.crypto_addresses && (
        <div className="px-4 mb-6">
          <h3 className="text-xs font-bold text-white/60 uppercase tracking-widest mb-3">
            Deposit Crypto
          </h3>
          <div className="space-y-2">
            {Object.entries(wallet.crypto_addresses).map(([type, address]) => (
              <CryptoDepositCard key={type} type={type} address={address} />
            ))}
          </div>
          <p className="text-[9px] text-white/20 text-center mt-2">
            100 SC per $1 USD value. Credits after 2 confirmations.
          </p>
        </div>
      )}

      {/* Stripe SC Packages */}
      <div className="px-4 mb-6">
        <h3 className="text-xs font-bold text-white/60 uppercase tracking-widest mb-3">
          Buy SweepCoins
        </h3>
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
                <span className="text-base font-black text-[#00F0FF]">
                  {pkg.sc_amount.toLocaleString()} SC
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-white/40 font-semibold">${pkg.price_usd}</span>
                <div className="flex items-center gap-1 text-[9px] text-white/20">
                  <CreditCard size={10} />
                  {checkoutLoading === pkg.id ? (
                    <Loader2 size={10} className="animate-spin" />
                  ) : (
                    'CARD'
                  )}
                </div>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Cashout */}
      <div className="px-4 mb-6">
        <Button
          onClick={handleCashout}
          disabled={!wallet || wallet.sc_balance < 100}
          data-testid="cashout-btn"
          className="w-full bg-gradient-to-r from-[#00F0FF] to-[#BD00FF] text-black font-bold rounded-xl py-3 disabled:opacity-30"
        >
          <ArrowUpRight size={16} className="mr-2" />
          CASHOUT SC TO CRYPTO
        </Button>
        <p className="text-[10px] text-white/20 text-center mt-2">
          Min cashout: 100 SC. Transfers within 24hrs.
        </p>
      </div>

      {/* Transactions */}
      <div className="px-4 mb-6">
        <h3 className="text-xs font-bold text-white/60 uppercase tracking-widest mb-3">
          Transaction History
        </h3>
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
                    {txn.amount > 0 ? (
                      <ArrowDownLeft size={14} className="text-green-400" />
                    ) : (
                      <ArrowUpRight size={14} className="text-red-400" />
                    )}
                  </div>
                  <div>
                    <p className="text-xs text-white font-medium">{txn.description}</p>
                    <p className="text-[10px] text-white/30 mono">
                      {new Date(txn.created_at).toLocaleDateString()}
                    </p>
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
