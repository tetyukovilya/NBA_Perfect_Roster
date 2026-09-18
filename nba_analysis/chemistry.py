"""Chemistry calculation between players."""
import math
from typing import Dict, List, Tuple
from .models import Player
from .config import (
    W_SIM, W_CO, W_USG_DIFF,
    CHEM_MIN, CHEM_MAX
)

# Global cache for chemistry calculations
_chemistry_cache: Dict[Tuple[str, str], float] = {}
_team_chem_cache: Dict[Tuple[str, Tuple[str, ...]], float] = {}


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


def chemistry(p1: Player, p2: Player, co_minutes_dict: Dict[Tuple[str, str], float]) -> float:
    """Chemistry bonus between two players (-0.5 to 0.5). Cached."""
    key = (p1.player, p2.player)
    if key in _chemistry_cache:
        return _chemistry_cache[key]
    
    sim = cosine_similarity(p1.vec, p2.vec)
    co = co_minutes_dict.get((p1.player, p2.player), 0.0)
    co_log = math.log1p(co)  # log(1+co)
    usg_diff = abs(p1.usage - p2.usage)
    bonus = W_SIM * sim + W_CO * co_log - W_USG_DIFF * usg_diff
    result = max(CHEM_MIN, min(CHEM_MAX, bonus))
    _chemistry_cache[key] = result
    return result


def get_team_chemistry_sum(ball_handler: Player, offense: List[Player], 
                           co_minutes_dict: Dict[Tuple[str, str], float]) -> float:
    """Cached sum of chemistry between ball_handler and all teammates."""
    team_players = tuple(sorted(p.player for p in offense))
    key = (ball_handler.player, team_players)
    if key in _team_chem_cache:
        return _team_chem_cache[key]
    
    chem_sum = sum(
        chemistry(ball_handler, teammate, co_minutes_dict)
        for teammate in offense if teammate is not ball_handler
    )
    _team_chem_cache[key] = chem_sum
    return chem_sum


def clear_chemistry_cache() -> None:
    """Clear the chemistry cache between simulation runs."""
    global _chemistry_cache, _team_chem_cache
    _chemistry_cache = {}
    _team_chem_cache = {}