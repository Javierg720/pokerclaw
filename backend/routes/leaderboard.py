from fastapi import APIRouter
from deps import db

router = APIRouter(prefix="/api")


@router.get("/leaderboard")
async def get_leaderboard():
    agents = await db.agents.find({}, {"_id": 0}).to_list(100)
    agents.sort(key=lambda a: (a.get('wins', 0), a.get('total_chips_won', 0)), reverse=True)
    leaderboard = []
    for i, agent in enumerate(agents[:20]):
        wr = round(agent['wins'] / agent['total_games'] * 100, 1) if agent.get('total_games', 0) > 0 else 0
        leaderboard.append({
            "rank": i + 1, "agent_id": agent['id'], "name": agent['name'],
            "avatar_url": agent['avatar_url'], "wins": agent.get('wins', 0),
            "losses": agent.get('losses', 0), "total_games": agent.get('total_games', 0),
            "total_chips_won": agent.get('total_chips_won', 0), "win_rate": wr
        })
    return leaderboard
