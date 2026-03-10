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


def run_betting_round(players, community_cards, pot, phase):
    actions = []
    current_bet = 20 if phase == 'preflop' else 0
    active = [p for p in players if not p['folded'] and p['chips'] > 0]

    for player in active:
        strength = hand_strength(
            player['hole_cards'],
            community_cards if community_cards else None
        )
        action, amount = agent_decide(
            player['strategy'], strength, pot, current_bet, player['chips'], phase
        )

        if action == 'fold':
            player['folded'] = True
            actions.append({
                'agent_id': player['agent_id'],
                'agent_name': player['agent_name'],
                'action': 'fold', 'amount': 0
            })
        elif action == 'raise':
            player['chips'] -= amount
            player['current_bet'] += amount
            player['total_bet'] += amount
            pot += amount
            current_bet = max(current_bet, amount)
            actions.append({
                'agent_id': player['agent_id'],
                'agent_name': player['agent_name'],
                'action': 'raise', 'amount': amount
            })
        else:
            call_amt = min(current_bet, player['chips'])
            player['chips'] -= call_amt
            player['current_bet'] += call_amt
            player['total_bet'] += call_amt
            pot += call_amt
            actions.append({
                'agent_id': player['agent_id'],
                'agent_name': player['agent_name'],
                'action': 'call', 'amount': call_amt
            })

    # Reset current bets for next round
    for p in players:
        p['current_bet'] = 0

    return players, pot, actions


def advance_game(game):
    phase = game['phase']
    deck = game['deck']
    players = game['players']
    community = game['community_cards']
    pot = game['pot']
    actions = []

    if phase == 'waiting':
        # Deal hole cards
        for p in players:
            p['hole_cards'] = [deck.pop(), deck.pop()]
            p['folded'] = False
            p['current_bet'] = 0
            p['total_bet'] = 0
            p['chips'] = 1000
        # Pre-flop betting
        players, pot, actions = run_betting_round(players, None, pot, 'preflop')
        game['phase'] = 'preflop'

    elif phase == 'preflop':
        # Deal flop
        deck.pop()  # burn
        community.extend([deck.pop() for _ in range(3)])
        players, pot, actions = run_betting_round(players, community, pot, 'flop')
        game['phase'] = 'flop'

    elif phase == 'flop':
        deck.pop()  # burn
        community.append(deck.pop())
        players, pot, actions = run_betting_round(players, community, pot, 'turn')
        game['phase'] = 'turn'

    elif phase == 'turn':
        deck.pop()  # burn
        community.append(deck.pop())
        players, pot, actions = run_betting_round(players, community, pot, 'river')
        game['phase'] = 'river'

    elif phase == 'river':
        # Showdown - evaluate hands
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
        game['phase'] = 'showdown'

    elif phase == 'showdown':
        game['phase'] = 'complete'

    game['deck'] = deck
    game['players'] = players
    game['community_cards'] = community
    game['pot'] = pot
    game['actions_log'] = game.get('actions_log', []) + actions

    return game
