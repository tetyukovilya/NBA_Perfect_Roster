"""Lineup building logic."""
from typing import List, Set
from .models import Player


def lineup_by_position(players: List[Player], metric: str) -> List[Player]:
    """Return a list of 5 players, one for each position (PG, SG, SF, PF, C),
    selected by highest metric value among players whose original position matches.
    If a position lacks players, fall back to best remaining players regardless of position.
    """
    positions = ['PG', 'SG', 'SF', 'PF', 'C']
    used: Set[str] = set()
    lineup: List[Player] = [None] * 5  # index corresponds to positions order
    
    # First pass: try to fill each position with matching original pos
    for idx, pos in enumerate(positions):
        candidates = [p for p in players if p.pos == pos and p.player not in used]
        if not candidates:
            continue
        candidates_sorted = sorted(candidates, key=lambda x: x.get_metric(metric), reverse=True)
        best = candidates_sorted[0]
        lineup[idx] = best
        used.add(best.player)
    
    # Second pass: fill any remaining slots with best overall remaining players
    remaining_players = [p for p in players if p.player not in used]
    remaining_sorted = sorted(remaining_players, key=lambda x: x.get_metric(metric), reverse=True)
    rem_idx = 0
    for idx in range(5):
        if lineup[idx] is None:
            if rem_idx < len(remaining_sorted):
                lineup[idx] = remaining_sorted[rem_idx]
                used.add(lineup[idx].player)
                rem_idx += 1
            else:
                lineup[idx] = None
    
    # Filter out None values
    lineup = [p for p in lineup if p is not None]
    
    # If still less than 5, just take top remaining
    if len(lineup) < 5:
        needed = 5 - len(lineup)
        extra = [p for p in remaining_sorted if p.player not in used][:needed]
        lineup.extend(extra)
        for p in extra:
            used.add(p.player)
    
    return lineup[:5]  # Ensure exactly 5