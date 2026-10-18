export function BrandMark({ compact = false, className = '' }) {
  return (
    <div className={`brand-mark ${compact ? 'brand-mark--compact' : ''} ${className}`.trim()} aria-label="PokerClaw">
      <div className="brand-mark__chip" aria-hidden="true">♠</div>
      <div className="brand-mark__type">
        <span>Poker</span><strong>Claw</strong>
      </div>
    </div>
  );
}
