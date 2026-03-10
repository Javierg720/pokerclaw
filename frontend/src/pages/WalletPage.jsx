import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { Navigation } from '../components/Navigation';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Wallet as WalletIcon, ArrowUpRight, ArrowDownLeft, Coins, Zap, Plus } from 'lucide-react';
import api from '../lib/api';
import { toast } from 'sonner';

const PURCHASE_OPTIONS = [
  { amount: 1000, currency: 'gc', label: '1,000 GC', price: 'Free' },
  { amount: 5000, currency: 'gc', label: '5,000 GC', price: 'Free' },
  { amount: 50, currency: 'sc', label: '50 SC', price: '$4.99' },
  { amount: 200, currency: 'sc', label: '200 SC', price: '$14.99' },
];

export default function WalletPage() {
  const { user } = useAuth();
  const [wallet, setWallet] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [walletRes, txnRes] = await Promise.all([
          api.get('/wallet'),
          api.get('/wallet/transactions'),
        ]);
        setWallet(walletRes.data);
        setTransactions(txnRes.data);
      } catch {
        toast.error('Failed to load wallet');
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  const handlePurchase = async (amount, currency) => {
    try {
      const res = await api.post('/wallet/purchase', { amount, currency });
      setWallet(res.data);
      toast.success(`Added ${amount} ${currency.toUpperCase()}!`);
      const txnRes = await api.get('/wallet/transactions');
      setTransactions(txnRes.data);
    } catch {
      toast.error('Purchase failed');
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

      {/* Balances */}
      <div className="px-4 grid grid-cols-2 gap-3 mb-6">
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
        <div className="glass rounded-2xl p-4 glow-cyan" data-testid="sc-balance-card">
          <div className="flex items-center gap-2 mb-2">
            <Zap size={16} className="text-[#00F0FF]" />
            <span className="text-[10px] text-white/40 uppercase tracking-widest">Sweep Coins</span>
          </div>
          <div className="text-2xl font-black text-[#00F0FF] mono">
            {wallet?.sc_balance?.toLocaleString() || 0}
          </div>
          <p className="text-[10px] text-white/20 mt-1">Redeemable to crypto</p>
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

      {/* Purchase */}
      <div className="px-4 mb-6">
        <h3 className="text-xs font-bold text-white/60 uppercase tracking-widest mb-3">
          Get More Coins
        </h3>
        <div className="grid grid-cols-2 gap-2">
          {PURCHASE_OPTIONS.map((opt) => (
            <button
              key={`${opt.currency}-${opt.amount}`}
              onClick={() => handlePurchase(opt.amount, opt.currency)}
              data-testid={`purchase-${opt.currency}-${opt.amount}`}
              className="glass rounded-xl p-3 text-left transition-all hover:border-[#FF003C]/30 border border-white/5"
            >
              <div className="flex items-center gap-1 mb-1">
                <Plus size={12} className={opt.currency === 'gc' ? 'text-[#FFE600]' : 'text-[#00F0FF]'} />
                <span className={`text-sm font-bold ${opt.currency === 'gc' ? 'text-[#FFE600]' : 'text-[#00F0FF]'}`}>
                  {opt.label}
                </span>
              </div>
              <span className="text-[10px] text-white/30">{opt.price}</span>
            </button>
          ))}
        </div>
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
