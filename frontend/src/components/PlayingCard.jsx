const SUIT_SYMBOLS = {
  hearts: '\u2665',
  diamonds: '\u2666',
  clubs: '\u2663',
  spades: '\u2660',
};

const SUIT_COLORS = {
  hearts: 'suit-red',
  diamonds: 'suit-red',
  clubs: 'suit-black',
  spades: 'suit-black',
};

export function PlayingCard({ card, size = 'md', delay = 0 }) {
  const sizes = {
    xs: 'w-7 h-10 text-[6px]',
    sm: 'w-9 h-[52px] text-[10px]',
    md: 'w-12 h-[68px] text-xs',
    lg: 'w-20 h-28 text-lg',
  };

  if (!card) {
    return (
      <div
        className={`playing-card playing-card-back ${sizes[size]} card-deal`}
        style={{ animationDelay: `${delay}ms` }}
        data-testid="card-back"
      />
    );
  }

  const suitSymbol = SUIT_SYMBOLS[card.suit] || '?';
  const colorClass = SUIT_COLORS[card.suit] || 'suit-black';

  return (
    <div
      className={`playing-card playing-card-front ${sizes[size]} card-deal flex flex-col justify-between p-1`}
      style={{ animationDelay: `${delay}ms` }}
      data-testid={`card-${card.rank}-${card.suit}`}
    >
      <div className={`${colorClass} font-bold leading-none`}>
        <div>{card.rank}</div>
        <div className="text-[0.7em]">{suitSymbol}</div>
      </div>
      <div className={`${colorClass} text-center text-[1.4em] leading-none`}>
        {suitSymbol}
      </div>
      <div className={`${colorClass} font-bold leading-none self-end rotate-180`}>
        <div>{card.rank}</div>
        <div className="text-[0.7em]">{suitSymbol}</div>
      </div>
    </div>
  );
}
