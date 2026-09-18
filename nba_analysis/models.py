"""Data models for NBA players and lineups."""
from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class Player:
    """NBA player with season statistics."""
    # Required fields (no defaults)
    player: str
    team: str
    pos: str              # normalized position (PG, SG, SF, PF, C)
    original_pos: str     # original position from data
    season: str
    lg: str
    ows: float
    dws: float
    ws: float
    obpm: float
    dbpm: float
    vorp: float
    per: float
    usg: float
    ast: float
    stl: float
    blk: float
    tov: float
    orb: float
    drb: float
    trb: float
    ts: float
    x3p_ar: float
    f_tr: float
    mp: float
    
    # Normalized attributes (computed) - all have defaults
    offs: float = 0.0     # offensive skill proxy (normalized OWS)
    defs: float = 0.0     # defensive skill proxy (normalized DWS)
    usage: float = 0.0    # normalized usage
    ast_norm: float = 0.0
    x3p: float = 0.0
    trb_norm: float = 0.0
    vec: List[float] = field(default_factory=list)  # chemistry vector [offs, defs, x3p, ast, trb]
    
    def get_metric(self, metric: str) -> float:
        """Get a metric value by name."""
        return getattr(self, metric, 0.0)


@dataclass
class Lineup:
    """A 5-player lineup with assigned positions."""
    players: List[Player]
    name: str
    metric: str  # metric used to select this lineup
    
    def __post_init__(self):
        if len(self.players) != 5:
            raise ValueError(f"Lineup must have exactly 5 players, got {len(self.players)}")
    
    def get_assigned_positions(self) -> List[str]:
        """Return assigned positions for each player slot."""
        return ['PG', 'SG', 'SF', 'PF', 'C']