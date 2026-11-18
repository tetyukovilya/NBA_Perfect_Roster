"""Тесты текстовой игры (макет): геометрия площадки и цикл владения."""
from __future__ import annotations

import random

from nba_analysis.config import AnalysisConfig
from nba_analysis.pipeline import build_lineups, load_dataset
from nba_analysis.textgame.actors import PlayerAgent
from nba_analysis.textgame.court import Court, ShotZone, is_three, zone_at
from nba_analysis.textgame.engine import simulate_possession


def test_zone_geometry():
    assert zone_at(0.5, 0.0) is ShotZone.RESTRICTED       # под кольцом
    assert zone_at(3.0, 1.0) is ShotZone.PAINT
    assert zone_at(6.0, 1.0) is ShotZone.MIDRANGE
    assert zone_at(9.0, 6.5) is ShotZone.CORNER_THREE     # угловая
    assert zone_at(4.0, 7.0) is ShotZone.ARC_THREE        # дуга сверху
    assert is_three(ShotZone.CORNER_THREE) and is_three(ShotZone.ARC_THREE)
    assert not is_three(ShotZone.MIDRANGE)


def test_court_clamp():
    court = Court()
    assert court.clamp(-5, 99) == (0.0, 7.5)
    assert court.clamp(99, -99) == (14.0, -7.5)


def _make_agent(pos="PG", x=8.0, y=0.0):
    profile = type("P", (), {"name": "Test", "stl": 1.5, "three_rate": 0.3})()
    return PlayerAgent(profile, pos, x, y, random.Random(0))


def test_defender_moves_toward_mark():
    court = Court()
    d = _make_agent("PG", x=10, y=0)
    mark = _make_agent("SG", x=8, y=4)
    before = d.dist_to(mark.x, mark.y)
    for _ in range(5):
        d.defend_update(mark, court)
    assert d.dist_to(mark.x, mark.y) < before


def test_possession_terminates_with_players():
    cfg = AnalysisConfig()
    data = load_dataset(cfg)
    a, b = build_lineups(cfg, data)[:2]
    from nba_analysis.profiles import build_profile

    rng = random.Random(7)
    court = Court()
    off, dfn = [], []
    spots = {"PG": (11, 0), "SG": (8.5, 5.5), "SF": (7, -6), "PF": (5, 3), "C": (2.8, 0)}
    for lineup, agents in ((a, off), (b, dfn)):
        for pos, p in lineup.slots():
            x, y = spots[pos]
            agents.append(PlayerAgent(build_profile(p, data.context, cfg.simulation), pos, x, y, rng))
    res = simulate_possession(off, dfn, court, rng)
    assert res.points in (0, 2, 3)
    assert res.events  # play-by-play непустой
