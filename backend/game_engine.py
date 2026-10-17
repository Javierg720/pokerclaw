import random
from itertools import combinations
from collections import Counter

SUITS = ['hearts', 'diamonds', 'clubs', 'spades']
RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
RANK_VALUES = {r: i for i, r in enumerate(RANKS, 2)}
HAND_NAMES = {
    10: "Royal Flush", 9: "Straight Flush", 8: "Four of a Kind",
    7: "Full House", 6: "Flush", 5: "Straight", 4: "Three of a Kind",
    3: "Two Pair", 2: "One Pair", 1: "High Card"
}

STRATEGIES = {
    'aggressive': {'fold': 0.15, 'raise_pct': 0.6, 'bluff': 0.3},
    'conservative': {'fold': 0.4, 'raise_pct': 0.2, 'bluff': 0.05},
    'balanced': {'fold': 0.25, 'raise_pct': 0.35, 'bluff': 0.15},
    'bluffer': {'fold': 0.2, 'raise_pct': 0.5, 'bluff': 0.5},
    'tight_aggressive': {'fold': 0.35, 'raise_pct': 0.5, 'bluff': 0.1},
    'loose_passive': {'fold': 0.1, 'raise_pct': 0.15, 'bluff': 0.2},
}

AGENT_PRESETS = [
    {"name": "BluffBot_9000", "strategy": "bluffer", "avatar_index": 0, "tagline": "All-in or nothing."},
    {"name": "Neural_Ace", "strategy": "balanced", "avatar_index": 1, "tagline": "Calculated precision."},
    {"name": "Vector_King", "strategy": "conservative", "avatar_index": 2, "tagline": "Patience is profit."},
    {"name": "Quantum_Queen", "strategy": "aggressive", "avatar_index": 3, "tagline": "Chaos is a ladder."},
    {"name": "Deep_Stack", "strategy": "tight_aggressive", "avatar_index": 0, "tagline": "Deep reads, deep pockets."},
    {"name": "Fold_Master", "strategy": "conservative", "avatar_index": 1, "tagline": "Live to fight another day."},
    {"name": "Claw_Crusher", "strategy": "aggressive", "avatar_index": 2, "tagline": "Crush. Dominate. Repeat."},
    {"name": "Molt_Mind", "strategy": "loose_passive", "avatar_index": 3, "tagline": "Slow and steady wins."},
]

AVATAR_URLS = [
    "https://images.unsplash.com/photo-1728112265403-a4aebd5859a5?w=200&h=200&fit=crop",
    "https://images.unsplash.com/photo-1711662171213-4141abec218f?w=200&h=200&fit=crop",
    "https://images.unsplash.com/photo-1677212004257-103cfa6b59d0?w=200&h=200&fit=crop",
    "https://images.unsplash.com/photo-1732020858816-93c130ab8f49?w=200&h=200&fit=crop",
]


def create_deck():
    deck = [{'rank': r, 'suit': s} for s in SUITS for r in RANKS]
    random.shuffle(deck)
    return deck


def card_value(card):
    return RANK_VALUES[card['rank']]


def evaluate_five(cards):
    ranks = sorted([card_value(c) for c in cards], reverse=True)
    suits = [c['suit'] for c in cards]
    is_flush = len(set(suits)) == 1

    is_straight = False
    high = ranks[0]
    if ranks == list(range(high, high - 5, -1)):
        is_straight = True
    elif ranks == [14, 5, 4, 3, 2]:
        is_straight = True
        high = 5

    rank_counts = Counter(ranks)
    counts = sorted(rank_counts.values(), reverse=True)
    by_freq = sorted(rank_counts.items(), key=lambda x: (x[1], x[0]), reverse=True)
    kickers = [r for r, _ in by_freq]

    if is_straight and is_flush:
        return (10 if high == 14 and ranks[4] == 10 else 9, [high])
    if counts == [4, 1]:
        return (8, kickers)
    if counts == [3, 2]:
        return (7, kickers)
    if is_flush:
        return (6, ranks)
    if is_straight:
        return (5, [high])
    if counts == [3, 1, 1]:
        return (4, kickers)
    if counts == [2, 2, 1]:
        return (3, kickers)
    if counts == [2, 1, 1, 1]:
        return (2, kickers)
    return (1, ranks)


def best_hand(hole_cards, community_cards):
    all_cards = hole_cards + community_cards
    if len(all_cards) < 5:
        return (1, [card_value(c) for c in sorted(all_cards, key=card_value, reverse=True)], "High Card")

    best = (0, [])
    for combo in combinations(all_cards, 5):
        score = evaluate_five(list(combo))
        if score > best:
            best = score
    return (*best, HAND_NAMES.get(best[0], "High Card"))


def hand_strength(hole_cards, community_cards=None):
    if not community_cards:
        r1, r2 = card_value(hole_cards[0]), card_value(hole_cards[1])
        suited = hole_cards[0]['suit'] == hole_cards[1]['suit']
        if r1 == r2:
            return 0.5 + (r1 / 14) * 0.5
        score = (max(r1, r2) + min(r1, r2)) / 28
        if suited:
            score += 0.1
        if abs(r1 - r2) <= 2:
            score += 0.05
        return min(score, 1.0)

    rank, _, name = best_hand(hole_cards, community_cards)
    return rank / 10.0


def agent_decide(strategy_name, strength, pot, current_bet, chips, phase):
    s = STRATEGIES.get(strategy_name, STRATEGIES['balanced'])
    phase_mult = {'preflop': 0.8, 'flop': 1.0, 'turn': 1.1, 'river': 1.2}.get(phase, 1.0)
    adj = strength * phase_mult

    if random.random() < s['bluff']:
        adj += random.uniform(0.2, 0.5)

    if adj < s['fold'] and current_bet > 0:
        return 'fold', 0

    if random.random() < s['raise_pct'] and adj > 0.3:
        amt = int(pot * random.uniform(0.3, 1.0))
        amt = max(amt, current_bet * 2, 20)
        amt = min(amt, chips)
        if amt > 0:
            return 'raise', amt

    return 'call', min(current_bet, chips)


def _get_active_players(players):
    """Get players that can still act (not folded, have chips)."""
    return [p for p in players if not p['folded'] and p['chips'] > 0]


def _next_actor(players, current_agent_id):
    """Return the agent_id of the next active player after current_agent_id in
    the original players-list order.  Returns None if no other active player
    exists (caller should then trigger a showdown check)."""
    n = len(players)
    start = next(
        (i for i, p in enumerate(players) if p['agent_id'] == current_agent_id),
        -1,
    )
    if start == -1:
        active = _get_active_players(players)
        return active[0]['agent_id'] if active else None
    for step in range(1, n + 1):
        candidate = players[(start + step) % n]
        if not candidate['folded'] and candidate['chips'] > 0:
            return candidate['agent_id']
    return None


def _get_betting_phase(game_phase):
    """Map game phase to the betting round name."""
    mapping = {
        'preflop': 'preflop',
        'preflop_betting': 'preflop',
        'flop_betting': 'flop',
        'turn_betting': 'turn',
        'river_betting': 'river',
    }
    return mapping.get(game_phase, 'preflop')


def advance_game(game, external_action=None):
    """
    Turn-by-turn game advancement. Each call processes ONE agent's action
    or a phase transition (dealing cards).

    external_action: Optional dict with {agent_id, action, amount} from an
    OpenClaw-connected agent. If provided and it matches the current actor,
    this action is used instead of auto-deciding.

    Phase flow:
      waiting -> dealing (deal hole cards)
      dealing -> preflop_betting (turn-by-turn)
      preflop_betting (all acted) -> flop_deal
      flop_deal -> flop_betting (turn-by-turn)
      flop_betting (all acted) -> turn_deal
      turn_deal -> turn_betting (turn-by-turn)
      turn_betting (all acted) -> river_deal
      river_deal -> river_betting (turn-by-turn)
      river_betting (all acted) -> showdown
      showdown -> complete
    """
    phase = game['phase']
    deck = game['deck']
    players = game['players']
    community = game['community_cards']
    pot = game['pot']
    action = None

    # ── WAITING: Deal hole cards ──
    if phase == 'waiting':
        for p in players:
            p['hole_cards'] = [deck.pop(), deck.pop()]
            p['folded'] = False
            p['current_bet'] = 0
            p['total_bet'] = 0
            p['chips'] = 1000
        game['phase'] = 'preflop_betting'
        game['turn_index'] = 0
        game['round_bet'] = 20  # Big blind
        game['round_phase'] = 'preflop'
        active = _get_active_players(players)
        game['current_actor'] = active[0]['agent_id'] if active else None
        # Per-round counters: track how many players have acted and the
        # initial count so a mid-round fold doesn't prematurely end the round.
        game['round_initial_player_count'] = len(active)
        game['actions_this_round'] = 0

    # ── BETTING ROUNDS (turn-by-turn) ──
    elif phase in ('preflop_betting', 'flop_betting', 'turn_betting', 'river_betting'):
        active = _get_active_players(players)
        # Backwards-compatible: old games may lack these keys; derive safe defaults.
        actions_done = game.get('actions_this_round', game.get('turn_index', 0))
        round_initial = game.get('round_initial_player_count', len(active))

        # Check if only one player left (everyone else folded)
        if len(active) <= 1:
            # Skip to showdown
            game['phase'] = 'showdown'
            game['turn_index'] = 0
            game['current_actor'] = None
        elif actions_done >= round_initial:
            # All initial players have acted this round -> transition to next phase
            for p in players:
                p['current_bet'] = 0
            game['turn_index'] = 0
            game['round_bet'] = 0
            game['actions_this_round'] = 0
            game['current_actor'] = None

            if phase == 'preflop_betting':
                game['phase'] = 'flop_deal'
            elif phase == 'flop_betting':
                game['phase'] = 'turn_deal'
            elif phase == 'turn_betting':
                game['phase'] = 'river_deal'
            elif phase == 'river_betting':
                game['phase'] = 'showdown'
        else:
            # Process ONE agent's action.
            # Identify whose turn it is via current_actor (authoritative), falling
            # back to the legacy turn_index approach for old game documents.
            current_actor_id = game.get('current_actor')
            player = next(
                (p for p in active if p['agent_id'] == current_actor_id),
                active[game.get('turn_index', 0) % len(active)],
            )
            betting_phase = _get_betting_phase(phase)

            # Check if external action was submitted for this agent
            if (external_action
                    and external_action.get('agent_id') == player['agent_id']
                    and external_action.get('action') in ('fold', 'call', 'raise')):
                act = external_action['action']
                amount = external_action.get('amount', 0)
                # Clamp raise amount to available chips
                if act == 'raise':
                    amount = max(int(amount), game.get('round_bet', 0) * 2, 20)
                    amount = min(amount, player['chips'])
                elif act == 'call':
                    amount = min(game.get('round_bet', 0), player['chips'])
            else:
                strength = hand_strength(
                    player['hole_cards'],
                    community if community else None
                )
                act, amount = agent_decide(
                    player['strategy'], strength, pot,
                    game.get('round_bet', 0), player['chips'], betting_phase
                )

            if act == 'fold':
                player['folded'] = True
                action = {
                    'agent_id': player['agent_id'],
                    'agent_name': player['agent_name'],
                    'action': 'fold', 'amount': 0
                }
            elif act == 'raise':
                player['chips'] -= amount
                player['current_bet'] += amount
                player['total_bet'] += amount
                pot += amount
                game['round_bet'] = max(game.get('round_bet', 0), amount)
                action = {
                    'agent_id': player['agent_id'],
                    'agent_name': player['agent_name'],
                    'action': 'raise', 'amount': amount
                }
            else:
                call_amt = min(game.get('round_bet', 0), player['chips'])
                player['chips'] -= call_amt
                player['current_bet'] += call_amt
                player['total_bet'] += call_amt
                pot += call_amt
                action = {
                    'agent_id': player['agent_id'],
                    'agent_name': player['agent_name'],
                    'action': 'call', 'amount': call_amt
                }

            game['turn_index'] = game.get('turn_index', 0) + 1
            game['actions_this_round'] = actions_done + 1
            # When the last player of the round has acted, signal no current actor
            # so the frontend doesn't show anyone as "thinking" before the phase
            # transition.  Otherwise, find the next active player by scanning the
            # original players-list order (fixes the fold-skips-next-player bug).
            if game['actions_this_round'] >= game.get('round_initial_player_count', round_initial):
                game['current_actor'] = None
            else:
                game['current_actor'] = _next_actor(players, player['agent_id'])

    # ── DEAL PHASES ──
    elif phase == 'flop_deal':
        deck.pop()  # burn
        community.extend([deck.pop() for _ in range(3)])
        game['phase'] = 'flop_betting'
        game['turn_index'] = 0
        game['round_bet'] = 0
        game['round_phase'] = 'flop'
        active = _get_active_players(players)
        game['current_actor'] = active[0]['agent_id'] if active else None
        game['round_initial_player_count'] = len(active)
        game['actions_this_round'] = 0

    elif phase == 'turn_deal':
        deck.pop()  # burn
        community.append(deck.pop())
        game['phase'] = 'turn_betting'
        game['turn_index'] = 0
        game['round_bet'] = 0
        game['round_phase'] = 'turn'
        active = _get_active_players(players)
        game['current_actor'] = active[0]['agent_id'] if active else None
        game['round_initial_player_count'] = len(active)
        game['actions_this_round'] = 0

    elif phase == 'river_deal':
        deck.pop()  # burn
        community.append(deck.pop())
        game['phase'] = 'river_betting'
        game['turn_index'] = 0
        game['round_bet'] = 0
        game['round_phase'] = 'river'
        active = _get_active_players(players)
        game['current_actor'] = active[0]['agent_id'] if active else None
        game['round_initial_player_count'] = len(active)
        game['actions_this_round'] = 0

    # ── SHOWDOWN ──
    elif phase == 'showdown':
        active = [p for p in players if not p['folded']]
        if len(active) == 1:
            winner = active[0]
            game['winner_id'] = winner['agent_id']
            game['winner_name'] = winner['agent_name']
            game['winning_hand'] = "Last Standing"
        else:
            best_score = (-1, [])
            winner = None
            for p in active:
                score = best_hand(p['hole_cards'], community)
                p['hand_rank'] = score[0]
                p['hand_name'] = score[2]
                if (score[0], score[1]) > best_score:
                    best_score = (score[0], score[1])
                    winner = p
            if winner:
                game['winner_id'] = winner['agent_id']
                game['winner_name'] = winner['agent_name']
                game['winning_hand'] = winner.get('hand_name', 'High Card')

        house_rake = int(pot * 0.20)
        game['house_rake'] = house_rake
        game['final_pot'] = pot - house_rake
        game['phase'] = 'complete'
        game['current_actor'] = None

    game['deck'] = deck
    game['players'] = players
    game['community_cards'] = community
    game['pot'] = pot
    if action:
        game['actions_log'] = game.get('actions_log', []) + [action]
        game['last_action'] = action

    return game
