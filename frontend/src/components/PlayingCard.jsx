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

export function PlayingCard({ card, size = 'md', delay = 0, dealFrom }) {
  const sizes = {
    xs: 'playing-card--xs w-12 h-[68px] text-xs',
    sm: 'playing-card--sm w-[54px] h-[76px] text-sm',
    md: 'playing-card--md w-[56px] h-20 text-sm',
    lg: 'w-20 h-28 text-lg',
  };

  const animClass = dealFrom ? 'card-deal-dir' : 'card-deal';
  const style = {
    animationDelay: `${delay}ms`,
    ...(dealFrom && {
      '--deal-x': `${dealFrom.x}px`,
      '--deal-y': `${dealFrom.y}px`,
    }),
  };

  if (!card) {
    return (
      <div
        className={`playing-card playing-card-back ${sizes[size]} ${animClass}`}
        style={style}
        data-testid="card-back"
      />
    );
  }

  const suitSymbol = SUIT_SYMBOLS[card.suit] || '?';
  const colorClass = SUIT_COLORS[card.suit] || 'suit-black';

  return (
    <div
      className={`playing-card playing-card-front ${sizes[size]} ${animClass} flex flex-col justify-between p-1`}
      style={style}
      data-testid={`card-${card.rank}-${card.suit}`}
    >
      <div className={`${colorClass} playing-card__corner font-bold leading-none`}>
        <div>{card.rank}</div>
        <div className="text-[0.7em]">{suitSymbol}</div>
      </div>
      <div className={`${colorClass} playing-card__pip text-center text-[1.4em] leading-none`}>
        {suitSymbol}
      </div>
      <div className={`${colorClass} playing-card__corner font-bold leading-none self-end rotate-180`}>
        <div>{card.rank}</div>
        <div className="text-[0.7em]">{suitSymbol}</div>
      </div>
    </div>
  );
}
