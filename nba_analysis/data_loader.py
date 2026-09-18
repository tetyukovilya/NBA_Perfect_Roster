"""Data loading and preprocessing for NBA player data."""
import csv
import os
from typing import List, Dict
from collections import defaultdict

from .config import DATA_PATH, POS_MAP, DEFAULT_POSITION
from .models import Player


def normalize_position(pos: str) -> str:
    """Map hybrid/alternate positions to standard 5 positions."""
    return POS_MAP.get(pos.strip().upper(), DEFAULT_POSITION)


def load_players() -> List[Player]:
    """Load players from CSV file."""
    players = []
    with open(DATA_PATH, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                player = Player(
                    player=row.get('player', '').strip(),
                    team=row.get('team', '').strip(),
                    pos=normalize_position(row.get('pos', '')),
                    original_pos=row.get('pos', '').strip(),
                    season=row.get('season', '').strip(),
                    lg=row.get('lg', '').strip(),
                    ows=float(row.get('ows', 0) or 0),
                    dws=float(row.get('dws', 0) or 0),
                    ws=float(row.get('ws', 0) or 0),
                    obpm=float(row.get('obpm', 0) or 0),
                    dbpm=float(row.get('dbpm', 0) or 0),
                    vorp=float(row.get('vorp', 0) or 0),
                    per=float(row.get('per', 0) or 0),
                    usg=float(row.get('usg_percent', 0) or 0),
                    ast=float(row.get('ast_percent', 0) or 0),
                    stl=float(row.get('stl_percent', 0) or 0),
                    blk=float(row.get('blk_percent', 0) or 0),
                    tov=float(row.get('tov_percent', 0) or 0),
                    orb=float(row.get('orb_percent', 0) or 0),
                    drb=float(row.get('drb_percent', 0) or 0),
                    trb=float(row.get('trb_percent', 0) or 0),
                    ts=float(row.get('ts_percent', 0) or 0),
                    x3p_ar=float(row.get('x3p_ar', 0) or 0),
                    f_tr=float(row.get('f_tr', 0) or 0),
                    mp=float(row.get('mp', 0) or 0),
                )
                if player.player:
                    players.append(player)
            except ValueError:
                continue
    return players


def normalize_stat(vals: List[float]) -> List[float]:
    """Normalize a list of numbers to 0-1 range; if all equal, return 0.5."""
    if not vals:
        return []
    v_min = min(vals)
    v_max = max(vals)
    if v_max == v_min:
        return [0.5] * len(vals)
    return [(v - v_min) / (v_max - v_min) for v in vals]


def prepare_players(players: List[Player]) -> List[Player]:
    """Add normalized attributes and compute chemistry vectors."""
    # Extract raw lists for normalization
    ows_vals = [p.ows for p in players]
    dws_vals = [p.dws for p in players]
    usg_vals = [p.usg for p in players]
    ast_vals = [p.ast for p in players]
    x3p_vals = [p.x3p_ar for p in players]
    trb_vals = [p.trb for p in players]
    
    # Normalize
    ows_norm = normalize_stat(ows_vals)
    dws_norm = normalize_stat(dws_vals)
    usg_norm = normalize_stat(usg_vals)
    ast_norm = normalize_stat(ast_vals)
    x3p_norm = normalize_stat(x3p_vals)
    trb_norm = normalize_stat(trb_vals)
    
    for i, p in enumerate(players):
        p.offs = ows_norm[i]
        p.defs = dws_norm[i]
        p.usage = usg_norm[i]
        p.ast_norm = ast_norm[i]
        p.x3p = x3p_norm[i]
        p.trb_norm = trb_norm[i]
        # Vector for chemistry similarity: [offs, defs, 3p%, ast%, trb%]
        p.vec = [p.offs, p.defs, p.x3p, p.ast_norm, p.trb_norm]
    
    return players


def compute_co_play_minutes(players: List[Player]) -> Dict[tuple, float]:
    """Return dict mapping (player_i, player_j) -> total minutes played together."""
    # Group by (season, team)
    season_team_players = defaultdict(list)
    for p in players:
        key = (p.season, p.team)
        season_team_players[key].append(p)
    
    co_minutes = defaultdict(float)
    for group in season_team_players.values():
        for i in range(len(group)):
            pi = group[i]
            for j in range(i + 1, len(group)):
                pj = group[j]
                shared = min(pi.mp, pj.mp)
                if shared > 0:
                    co_minutes[(pi.player, pj.player)] += shared
                    co_minutes[(pj.player, pi.player)] += shared
    return dict(co_minutes)