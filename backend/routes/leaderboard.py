from fastapi import APIRouter
from deps import db
from agent_entertainment import public_personality, POLICY_VERSION

router = APIRouter(prefix="/api")


@router.get("/leaderboard")
async def get_leaderboard():
    # ── Top Agents ──
    agents = await db.agents.find({}, {"_id": 0}).to_list(100)
    agents.sort(key=lambda a: (a.get('wins', 0), a.get('total_chips_won', 0)), reverse=True)
    top_agents = []
    for i, agent in enumerate(agents[:20]):
        wr = round(agent['wins'] / agent['total_games'] * 100, 1) if agent.get('total_games', 0) > 0 else 0
        top_agents.append({
            "id": agent['id'], "rank": i + 1, "agent_id": agent['id'],
            "name": agent['name'], "avatar_url": agent['avatar_url'],
            "tagline": agent.get('tagline', ''),
            "strategy": agent.get('strategy', 'balanced'),
            "personality": agent.get('personality') or public_personality(agent),
            "decision_source": "external_agent" if agent.get('is_external') else "pokerclaw_policy",
            "policy_version": "external-agent" if agent.get('is_external') else POLICY_VERSION,
            "wins": agent.get('wins', 0), "losses": agent.get('losses', 0),
            "total_games": agent.get('total_games', 0),
            "total_chips_won": agent.get('total_chips_won', 0), "win_rate": wr
        })

    # ── Top Bettors (spectator leaderboard) ──
    # Aggregate all settled bets (game bets + tournament bets) per user
    bettor_stats = {}

    # Game bets
    settled_bets = await db.bets.find(
        {"status": {"$in": ["won", "lost"]}}, {"_id": 0}
    ).to_list(5000)
    for b in settled_bets:
        uid = b['user_id']
        if uid not in bettor_stats:
            bettor_stats[uid] = {"total_bets": 0, "bets_won": 0, "bets_lost": 0, "total_wagered": 0, "total_won": 0, "net_profit": 0}
        bettor_stats[uid]["total_bets"] += 1
        bettor_stats[uid]["total_wagered"] += b.get('amount', 0)
        if b['status'] == 'won':
            bettor_stats[uid]["bets_won"] += 1
            bettor_stats[uid]["total_won"] += b.get('payout', 0)
            bettor_stats[uid]["net_profit"] += b.get('payout', 0) - b.get('amount', 0)
        else:
            bettor_stats[uid]["bets_lost"] += 1
            bettor_stats[uid]["net_profit"] -= b.get('amount', 0)

    # Tournament bets
    tourney_bets = await db.tournament_bets.find(
        {"status": {"$in": ["won", "lost"]}}, {"_id": 0}
    ).to_list(5000)
    for b in tourney_bets:
        uid = b['user_id']
        if uid not in bettor_stats:
            bettor_stats[uid] = {"total_bets": 0, "bets_won": 0, "bets_lost": 0, "total_wagered": 0, "total_won": 0, "net_profit": 0}
        bettor_stats[uid]["total_bets"] += 1
        bettor_stats[uid]["total_wagered"] += b.get('amount', 0)
        if b['status'] == 'won':
            bettor_stats[uid]["bets_won"] += 1
            bettor_stats[uid]["total_won"] += b.get('payout', 0)
            bettor_stats[uid]["net_profit"] += b.get('payout', 0) - b.get('amount', 0)
        else:
            bettor_stats[uid]["bets_lost"] += 1
            bettor_stats[uid]["net_profit"] -= b.get('amount', 0)

    # Fetch usernames and sort by total won
    top_bettors = []
    for uid, stats in bettor_stats.items():
        user = await db.users.find_one({"id": uid}, {"_id": 0, "username": 1})
        username = user.get('username', 'Anonymous') if user else 'Anonymous'
        win_rate = round(stats['bets_won'] / stats['total_bets'] * 100, 1) if stats['total_bets'] > 0 else 0
        top_bettors.append({
            "user_id": uid, "username": username,
            "total_bets": stats['total_bets'], "bets_won": stats['bets_won'],
            "bets_lost": stats['bets_lost'], "total_wagered": stats['total_wagered'],
            "total_won": stats['total_won'], "net_profit": stats['net_profit'],
            "win_rate": win_rate,
        })

    top_bettors.sort(key=lambda x: (x['total_won'], x['bets_won']), reverse=True)
    for i, b in enumerate(top_bettors[:20]):
        b['rank'] = i + 1

    return {"top_agents": top_agents, "top_bettors": top_bettors[:20]}
