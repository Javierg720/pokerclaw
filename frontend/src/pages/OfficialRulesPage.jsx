import { Link } from 'react-router-dom';
import { ArrowLeft, Scale, ShieldCheck } from 'lucide-react';

const Rule = ({ title, children }) => (
  <section className="glass rounded-xl p-4 border border-white/5">
    <h2 className="text-sm font-bold text-white mb-2">{title}</h2>
    <div className="text-xs text-white/45 leading-relaxed">{children}</div>
  </section>
);

export default function OfficialRulesPage() {
  return (
    <div className="min-h-screen px-4 py-6 max-w-lg mx-auto" data-testid="official-rules-page">
      <Link to="/wallet" className="inline-flex items-center gap-2 text-xs text-white/50 hover:text-white mb-6">
        <ArrowLeft size={14} /> Back to wallet
      </Link>
      <div className="flex items-center gap-3 mb-2">
        <Scale className="text-[#FFE600]" size={24} />
        <h1 className="text-xl font-black text-white">OFFICIAL RULES</h1>
      </div>
      <div className="flex gap-2 rounded-xl bg-[#FF003C]/10 border border-[#FF003C]/20 p-3 mb-5">
        <ShieldCheck size={18} className="text-[#FF6B88] shrink-0" />
        <p className="text-[11px] text-[#FF9BAD] leading-relaxed">
          Draft launch controls. Sweepstakes Coin play and crypto funding are available only in configured jurisdictions
          after player eligibility checks. Crypto prize redemption is available only when identity checks, operator payout review,
          and final jurisdiction-specific rules are enabled.
        </p>
      </div>
      <div className="space-y-3">
        <Rule title="No purchase necessary">
          No purchase is necessary to obtain a free method of entry. A purchase does not improve the odds of winning.
          Eligible human players may use the daily free-coin claim in the wallet.
        </Rule>
        <Rule title="Two separate virtual currencies">
          Gold Coins are entertainment-only virtual credits. They have no cash value and can never be redeemed for cash or prizes.
          Sweepstakes Coins are free promotional entries. SC play is unavailable unless the player satisfies every eligibility control.
        </Rule>
        <Rule title="Eligibility">
          The production minimum age is 21 unless final jurisdiction-specific rules require a higher age. Age verification,
          allowed-jurisdiction verification, and geolocation are required before SC play. Employees, restricted persons,
          and residents of excluded jurisdictions are not eligible.
        </Rule>
        <Rule title="Responsible play">
          Players may permanently self-exclude from SC play from the wallet. Production launch also requires configurable
          play limits, responsible-play support links, fraud controls, and an audited customer-support process.
        </Rule>
        <Rule title="Funding and prizes">
          Configured deployments may accept verified on-chain crypto deposits for SC. Eligible players may request redemption
          of available SC into BTC, LTC, or ETH at the displayed exchange quote. SC is reserved when a request is submitted,
          and payout is completed only after identity review and on-chain verification. Crypto deposits do not replace the free
          daily entry path or improve game odds.
        </Rule>
        <Rule title="Game integrity">
          PokerClaw must publish how agent behavior, side-bet odds, settlement, cancellations, outages, and errors are handled.
          Results and wallet movements require tamper-evident records before production launch.
        </Rule>
      </div>
    </div>
  );
}
