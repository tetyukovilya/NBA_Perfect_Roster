"""Game simulation logic."""
import random
from typing import List, Optional, Dict, Tuple
from .models import Player, Lineup
from .config import (
    LEAGUE_FG, POSSESSIONS_PER_GAME, NUM_GAMES_SIM,
    SHOT_PROB_MIN, SHOT_PROB_MAX
)
from .chemistry import get_team_chemistry_sum, clear_chemistry_cache


def possession(offense: List[Player], defense: List[Player], 
               chem_bonus: float, co_minutes_dict: Dict[Tuple[str, str], float]) -> Tuple[int, Optional[str]]:
    """Simulate one possession; return points scored by offense and which team gets rebound if miss."""
    # Choose ball handler weighted by usage
    ball_handler = random.choices(offense, weights=[p.usage for p in offense])[0]
    # Choose defender weighted by defensive skill
    defender = random.choices(defense, weights=[p.defs for p in defense])[0]
    
    # Base success probability
    p_shot = ball_handler.offs * (1 - defender.defs) * LEAGUE_FG
    
    # Chemistry boost from teammates on floor (excluding ball handler) - cached
    chem = get_team_chemistry_sum(ball_handler, offense, co_minutes_dict)
    p_shot *= (1 + chem_bonus * chem)  # chem_bonus scales overall chemistry influence
    
    # Clamp
    p_shot = max(SHOT_PROB_MIN, min(SHOT_PROB_MAX, p_shot))
    
    if random.random() < p_shot:
        # Made shot
        pts = 3 if random.random() < ball_handler.x3p else 2
        return pts, None  # no rebound
    else:
        # Missed shot -> rebound
        off_reb = sum(p.orb for p in offense)
        def_reb = sum(p.drb for p in defense)
        total = off_reb + def_reb
        if total == 0:
            reb_team = random.choice(['off', 'def'])
        else:
            if random.random() < off_reb / total:
                reb_team = 'off'
            else:
                reb_team = 'def'
        return 0, reb_team


def simulate_game(lineup_a: List[Player], lineup_b: List[Player], 
                  chem_bonus: float = 0.1, possessions: int = POSSESSIONS_PER_GAME,
                  co_minutes_dict: Optional[Dict[Tuple[str, str], float]] = None) -> Tuple[int, int]:
    """Simulate a full game between two lineups."""
    if co_minutes_dict is None:
        co_minutes_dict = {}
    
    score_a = 0
    score_b = 0
    
    # Track possession properly: offensive rebound doesn't count as new possession
    possessions_played = 0
    offense_has_ball = True  # True = lineup_a has ball, False = lineup_b has ball
    
    while possessions_played < possessions:
        if offense_has_ball:
            pts, reb = possession(lineup_a, lineup_b, chem_bonus, co_minutes_dict)
            score_a += pts
        else:
            pts, reb = possession(lineup_b, lineup_a, chem_bonus, co_minutes_dict)
            score_b += pts
        
        if reb is None:
            # Made shot - possession ends, other team gets ball
            offense_has_ball = not offense_has_ball
            possessions_played += 1
        elif reb == 'off':
            # Offensive rebound - same team keeps ball, possession continues
            pass
        else:
            # Defensive rebound - other team gets ball
            offense_has_ball = not offense_has_ball
            possessions_played += 1
    
    return score_a, score_b


def evaluate_lineup(lineup: List[Player], opponents: List[List[Player]], 
                    chem_bonus: float = 0.1, games: int = NUM_GAMES_SIM,
                    co_minutes_dict: Optional[Dict[Tuple[str, str], float]] = None) -> float:
    """Play 'games' number of games against each opponent lineup, return average point difference."""
    if co_minutes_dict is None:
        co_minutes_dict = {}
    
    clear_chemistry_cache()  # Clear cache since team composition changes
    
    total_diff = 0.0
    total_games = 0
    
    for opp in opponents:
        for _ in range(games):
            a, b = simulate_game(lineup, opp, chem_bonus, co_minutes_dict=co_minutes_dict)
            total_diff += (a - b)
            total_games += 1
    
    return total_diff / total_games if total_games else 0.0


def simulate_matchup(lineup_a: List[Player], lineup_b: List[Player],
                     chem_bonus: float = 0.1, games: int = NUM_GAMES_SIM,
                     co_minutes_dict: Optional[Dict[Tuple[str, str], float]] = None) -> Dict:
    """Simulate a series between two lineups and return detailed results."""
    if co_minutes_dict is None:
        co_minutes_dict = {}
    
    clear_chemistry_cache()
    
    wins_a = 0
    wins_b = 0
    total_diff = 0.0
    scores_a = []
    scores_b = []
    
    for _ in range(games):
        a, b = simulate_game(lineup_a, lineup_b, chem_bonus, co_minutes_dict=co_minutes_dict)
        scores_a.append(a)
        scores_b.append(b)
        total_diff += (a - b)
        if a > b:
            wins_a += 1
        elif b > a:
            wins_b += 1
    
    return {
        'lineup_a_wins': wins_a,
        'lineup_b_wins': wins_b,
        'avg_point_diff': total_diff / games if games else 0.0,
        'avg_score_a': sum(scores_a) / len(scores_a) if scores_a else 0.0,
        'avg_score_b': sum(scores_b) / len(scores_b) if scores_b else 0.0,
    }