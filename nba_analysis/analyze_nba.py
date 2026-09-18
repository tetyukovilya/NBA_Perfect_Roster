import csv
import os
import math
import random
from collections import defaultdict
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple

DATA_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'Players.csv')
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), '..', 'starting_five_2026.md')

LEAGUE_FG = 0.46  # league average field goal percentage (approx)
POSSESSIONS_PER_GAME = 100
NUM_GAMES_SIM = 10000  # number of games to simulate for each lineup

# weights for chemistry
W_SIM = 0.6
W_CO = 0.3
W_USG_DIFF = 0.1

# Position normalization map (handles hybrid positions from Basketball-Reference)
POS_MAP = {
    'PG': 'PG', 'SG': 'SG', 'SF': 'SF', 'PF': 'PF', 'C': 'C',
    'G': 'PG', 'F': 'SF', 'G-F': 'SG', 'F-G': 'SG',
    'F-C': 'PF', 'C-F': 'PF', 'C-PF': 'PF', 'PF-C': 'PF',
    'SG-SF': 'SG', 'SF-SG': 'SF', 'PG-SG': 'PG', 'SG-PG': 'SG',
}

def normalize_position(pos: str) -> str:
    """Map hybrid/alternate positions to standard 5 positions."""
    return POS_MAP.get(pos.strip().upper(), 'SF')  # default to SF if unknown

def load_players():
    players = []
    with open(DATA_PATH, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                ows = float(row.get('ows', 0) or 0)
                dws = float(row.get('dws', 0) or 0)
                ws = float(row.get('ws', 0) or 0)
                obpm = float(row.get('obpm', 0) or 0)
                dbpm = float(row.get('dbpm', 0) or 0)
                vorp = float(row.get('vorp', 0) or 0)
                per = float(row.get('per', 0) or 0)
                usg = float(row.get('usg_percent', 0) or 0)
                ast = float(row.get('ast_percent', 0) or 0)
                stl = float(row.get('stl_percent', 0) or 0)
                blk = float(row.get('blk_percent', 0) or 0)
                tov = float(row.get('tov_percent', 0) or 0)
                orb = float(row.get('orb_percent', 0) or 0)
                drb = float(row.get('drb_percent', 0) or 0)
                trb = float(row.get('trb_percent', 0) or 0)
                ts = float(row.get('ts_percent', 0) or 0)
                x3p = float(row.get('x3p_ar', 0) or 0)
                ft_rate = float(row.get('f_tr', 0) or 0)
                mp = float(row.get('mp', 0) or 0)
                player = row.get('player', '').strip()
                team = row.get('team', '').strip()
                pos = row.get('pos', '').strip()
                season = row.get('season', '').strip()
                lg = row.get('lg', '').strip()
                if not player:
                    continue
                players.append({
                    'player': player,
                    'team': team,
                    'pos': normalize_position(pos),  # normalized position
                    'original_pos': pos,  # keep original for display
                    'season': season,
                    'lg': lg,
                    'ows': ows,
                    'dws': dws,
                    'ws': ws,
                    'obpm': obpm,
                    'dbpm': dbpm,
                    'vorp': vorp,
                    'per': per,
                    'usg': usg,
                    'ast': ast,
                    'stl': stl,
                    'blk': blk,
                    'tov': tov,
                    'orb': orb,
                    'drb': drb,
                    'trb': trb,
                    'ts': ts,
                    'x3p_ar': x3p,
                    'f_tr': ft_rate,
                    'mp': mp,
                })
            except ValueError:
                continue
    return players

def normalize_stat(vals):
    """Normalize a list of numbers to 0-1 range; if all equal, return 0.5."""
    if not vals:
        return [0.5] * len(vals)
    v_min = min(vals)
    v_max = max(vals)
    if v_max == v_min:
        return [0.5] * len(vals)
    return [(v - v_min) / (v_max - v_min) for v in vals]

def prepare_players(players):
    """Add normalized attributes and compute vectors."""
    # extract raw lists for normalization
    ows_vals = [p['ows'] for p in players]
    dws_vals = [p['dws'] for p in players]
    usg_vals = [p['usg'] for p in players]
    ast_vals = [p['ast'] for p in players]
    x3p_vals = [p['x3p_ar'] for p in players]
    trb_vals = [p['trb'] for p in players]
    # normalize
    ows_norm = normalize_stat(ows_vals)
    dws_norm = normalize_stat(dws_vals)
    usg_norm = normalize_stat(usg_vals)
    ast_norm = normalize_stat(ast_vals)
    x3p_norm = normalize_stat(x3p_vals)
    trb_norm = normalize_stat(trb_vals)
    for i, p in enumerate(players):
        p['offs'] = ows_norm[i]  # offensive skill proxy
        p['defs'] = dws_norm[i]  # defensive skill proxy
        p['usage'] = usg_norm[i]
        p['ast'] = ast_norm[i]
        p['x3p'] = x3p_norm[i]
        p['trb'] = trb_norm[i]
        # vector for chemistry similarity
        p['vec'] = [p['offs'], p['defs'], p['x3p'], p['ast'], p['trb']]
    return players

def compute_co_play_minutes(players):
    """Return dict mapping (player_i, player_j) -> total minutes played together."""
    # group by (season, team)
    season_team_players = defaultdict(list)
    for p in players:
        key = (p['season'], p['team'])
        season_team_players[key].append(p)
    co_minutes = defaultdict(float)
    for group in season_team_players.values():
        # for each pair in group, add minutes of each player (approx shared time)
        # simple approach: sum of min(mp_i, mp_j) as proxy
        for i in range(len(group)):
            pi = group[i]
            for j in range(i+1, len(group)):
                pj = group[j]
                shared = min(pi['mp'], pj['mp'])
                if shared > 0:
                    co_minutes[(pi['player'], pj['player'])] += shared
                    co_minutes[(pj['player'], pi['player'])] += shared
    return co_minutes

def cosine_similarity(v1, v2):
    dot = sum(a*b for a,b in zip(v1, v2))
    norm1 = math.sqrt(sum(a*a for a in v1))
    norm2 = math.sqrt(sum(b*b for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)

# Global cache for chemistry calculations
_chemistry_cache = {}
_team_chem_cache = {}

def chemistry(p1, p2, co_minutes_dict):
    """Chemistry bonus between two players (0-1 ish). Cached."""
    key = (p1['player'], p2['player'])
    if key in _chemistry_cache:
        return _chemistry_cache[key]
    
    sim = cosine_similarity(p1['vec'], p2['vec'])
    co = co_minutes_dict.get((p1['player'], p2['player']), 0.0)
    co_log = math.log1p(co)  # log(1+co)
    usg_diff = abs(p1['usage'] - p2['usage'])
    bonus = W_SIM * sim + W_CO * co_log - W_USG_DIFF * usg_diff
    # clamp to reasonable range, e.g., -0.5 to 0.5
    result = max(-0.5, min(0.5, bonus))
    _chemistry_cache[key] = result
    return result

def get_team_chemistry_sum(ball_handler, offense, co_minutes_dict):
    """Cached sum of chemistry between ball_handler and all teammates."""
    # Create a cache key from the team composition
    team_players = tuple(sorted(p['player'] for p in offense))
    key = (ball_handler['player'], team_players)
    if key in _team_chem_cache:
        return _team_chem_cache[key]
    
    chem_sum = sum(chemistry(ball_handler, teammate, co_minutes_dict) 
                   for teammate in offense if teammate is not ball_handler)
    _team_chem_cache[key] = chem_sum
    return chem_sum

def clear_chemistry_cache():
    """Clear the chemistry cache between simulation runs."""
    global _chemistry_cache, _team_chem_cache
    _chemistry_cache = {}
    _team_chem_cache = {}

def lineup_by_position(players, metric):
    """Return a list of 5 players, one for each position (PG,SG,SF,PF,C),
    selected by highest metric value among players whose original position matches.
    If a position lacks players, fall back to best remaining players regardless of position.
    """
    positions = ['PG', 'SG', 'SF', 'PF', 'C']
    used = set()
    lineup = [None] * 5  # index corresponds to positions order
    # First pass: try to fill each position with matching original pos
    for idx, pos in enumerate(positions):
        # filter players matching position and not used
        candidates = [p for p in players if p['pos'] == pos and p['player'] not in used]
        if not candidates:
            continue
        # sort by metric descending
        candidates_sorted = sorted(candidates, key=lambda x: x[metric], reverse=True)
        best = candidates_sorted[0]
        lineup[idx] = best
        used.add(best['player'])
    # Second pass: fill any remaining slots with best overall remaining players
    remaining_players = [p for p in players if p['player'] not in used]
    remaining_sorted = sorted(remaining_players, key=lambda x: x[metric], reverse=True)
    rem_idx = 0
    for idx in range(5):
        if lineup[idx] is None:
            if rem_idx < len(remaining_sorted):
                lineup[idx] = remaining_sorted[rem_idx]
                used.add(lineup[idx]['player'])
                rem_idx += 1
            else:
                # should not happen if enough players
                lineup[idx] = None
    # Ensure we have exactly 5 players (filter None)
    lineup = [p for p in lineup if p is not None]
    # If still less than 5, just take top remaining (should not happen)
    if len(lineup) < 5:
        needed = 5 - len(lineup)
        extra = [p for p in remaining_sorted if p['player'] not in used][:needed]
        lineup.extend(extra)
        for p in extra:
            used.add(p['player'])
    return lineup

def format_md(title, five, metric):
    lines = [f'## {title}\n']
    positions = ['PG', 'SG', 'SF', 'PF', 'C']
    for idx, p in enumerate(five):
        assigned_pos = positions[idx] if idx < len(positions) else 'N/A'
        original_pos = p.get('original_pos', p['pos'])
        lines.append(
            f'{idx+1}. **{p["player"]}** (Assigned Pos: {assigned_pos}, Original Pos: {original_pos}, {p["team"]}, {p["season"]} {p["lg"]}) '
            f'{metric.upper()}:{p[metric]:.2f} | OBPM:{p["obpm"]:.2f} DBPM:{p["dbpm"]:.2f} '
            f'VORP:{p["vorp"]:.2f} PER:{p["per"]:.1f}'
        )
    lines.append('')
    return '\n'.join(lines)

def possession(offense, defense, chem_bonus, co_minutes_dict):
    """Simulate one possession; return points scored by offense and which team gets rebound if miss."""
    # choose ball handler weighted by usage
    ball_handler = random.choices(offense, weights=[p['usage'] for p in offense])[0]
    # choose defender weighted by defensive skill
    defender = random.choices(defense, weights=[p['defs'] for p in defense])[0]
    # base success probability
    p_shot = ball_handler['offs'] * (1 - defender['defs']) * LEAGUE_FG
    # chemistry boost from teammates on floor (excluding ball handler) - cached
    chem = get_team_chemistry_sum(ball_handler, offense, co_minutes_dict)
    p_shot *= (1 + chem_bonus * chem)  # chem_bonus scales overall chemistry influence
    # clamp
    p_shot = max(0.0, min(0.9, p_shot))
    if random.random() < p_shot:
        # made shot
        pts = 3 if random.random() < ball_handler['x3p'] else 2
        return pts, None  # no rebound
    else:
        # missed shot -> rebound
        off_reb = sum(p['orb'] for p in offense)
        def_reb = sum(p['drb'] for p in defense)
        total = off_reb + def_reb
        if total == 0:
            # fallback random
            reb_team = random.choice(['off', 'def'])
        else:
            if random.random() < off_reb / total:
                reb_team = 'off'
            else:
                reb_team = 'def'
        return 0, reb_team

def simulate_game(lineup_a, lineup_b, chem_bonus=0.1, possessions=POSSESSIONS_PER_GAME, co_minutes_dict=None):
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
            # made shot - possession ends, other team gets ball
            offense_has_ball = not offense_has_ball
            possessions_played += 1
        elif reb == 'off':
            # offensive rebound - same team keeps ball, possession continues (don't increment counter)
            pass
        else:
            # defensive rebound - other team gets ball
            offense_has_ball = not offense_has_ball
            possessions_played += 1
    return score_a, score_b

def evaluate_lineup(lineup, opponents, chem_bonus=0.1, games=NUM_GAMES_SIM, co_minutes_dict=None):
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

def main():
    players = load_players()
    players = prepare_players(players)
    co_minutes = compute_co_play_minutes(players)
    
    # compute position-specific lineups
    overall = lineup_by_position(players, 'ws')
    offense = lineup_by_position(players, 'ows')
    defense = lineup_by_position(players, 'dws')
    
    # Build markdown content
    md_lines = []
    md_lines.append('# Best Overall Five (Win Shares) – All Time (One per Position)')
    md_lines.append(format_md('Best Overall Five (WS)', overall, 'ws'))
    md_lines.append('# Best Offensive Five (Offensive Win Shares) – All Time (One per Position)')
    md_lines.append(format_md('Best Offensive Five (OWS)', offense, 'ows'))
    md_lines.append('# Best Defensive Five (Defensive Win Shares) – All Time (One per Position)')
    md_lines.append(format_md('Best Defensive Five (DWS)', defense, 'dws'))
    
    # Simulation section
    md_lines.append('# Simulation Results (Chemistry Adjusted)')
    md_lines.append(f'Each lineup simulated {NUM_GAMES_SIM} games against each of the other two lineups.')
    md_lines.append(f'Chemistry bonus weight: 0.1 (scale factor).')
    md_lines.append('')
    
    lineups = [('Overall', overall), ('Offense', offense), ('Defense', defense)]
    # compute avg point diff vs others
    for name_i, lineup_i in lineups:
        opps = [lineup_j for name_j, lineup_j in lineups if name_j != name_i]
        avg_diff = evaluate_lineup(lineup_i, opps, chem_bonus=0.1, co_minutes_dict=co_minutes)
        md_lines.append(f'## {name_i} Lineup')
        md_lines.append(f'Average point difference per game vs other lineups: {avg_diff:.2f} points')
        md_lines.append('')
    
    # Write to file
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        f.write('\n'.join(md_lines))
    
    print(f'Results written to {OUTPUT_PATH}')

if __name__ == '__main__':
    main()