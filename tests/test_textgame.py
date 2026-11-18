"""Тесты текстовой игры (макет): геометрия площадки и цикл владения."""
from __future__ import annotations

import random

from nba_analysis.config import AnalysisConfig
from nba_analysis.pipeline import build_lineups, load_dataset
from nba_analysis.profiles import build_profile
from nba_analysis.textgame.actors import PlayerAgent
from nba_analysis.textgame.court import Court, ShotZone, is_three, zone_at
from nba_analysis.textgame.engine import GameState, simulate_possession

SPOTS = {"PG": (11, 0), "SG": (8.5, 5.5), "SF": (7, -6), "PF": (5, 3), "C": (2.8, 0)}


def _load_teams():
    cfg = AnalysisConfig()
    data = load_dataset(cfg)
    a, b = build_lineups(cfg, data)[:2]
    rng = random.Random(7)
    off, dfn = [], []
    for lineup, agents in ((a, off), (b, dfn)):
        for pos, p in lineup.slots():
            x, y = SPOTS[pos]
            agents.append(PlayerAgent(build_profile(p, data.context, cfg.simulation), pos, x, y, rng))
    return off, dfn


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


def test_frozen_defender_does_not_move():
    court = Court()
    d = _make_agent("PG", x=10, y=0)
    d.frozen = 3
    mark = _make_agent("SG", x=4, y=0)
    d.defend_update(mark, court)
    assert (d.x, d.y) == (10, 0)  # стоит на месте


def test_possession_terminates_with_players():
    off, dfn = _load_teams()
    rng = random.Random(7)
    res = simulate_possession(off, dfn, Court(), rng)
    assert res.points in (0, 1, 2, 3, 4)  # 3/4 = and-one
    assert res.events  # play-by-play непустой


def test_game_mechanics_appear_over_many_possessions():
    """Заслоны, фолы, штрафные встречаются в серии владений (фикс. seed)."""
    off, dfn = _load_teams()
    rng = random.Random(11)
    state = GameState()
    all_events = []
    for _ in range(40):
        res = simulate_possession(off, dfn, Court(), rng, state, "A", "B")
        all_events.extend(res.events)
    text = "\n".join(all_events)
    assert "заслон" in text.lower()
    assert "Фол" in text
    assert "Штрафные" in text
    total_fouls = sum(a.personal_fouls for a in dfn)
    assert total_fouls == state.team_fouls.get("B", 0) > 0


def test_on_tick_and_printer_hooks():
    """Движок отдаёт снимки каждого тика и шлёт события в printer."""
    off, dfn = _load_teams()
    rng = random.Random(3)
    snapshots = []
    printed = []
    simulate_possession(off, dfn, Court(), rng, on_tick=snapshots.append)
    assert snapshots, "on_tick не вызван"
    snap = snapshots[0]
    assert len(snap.offense) == 5 and len(snap.defense) == 5
    assert 0 <= snap.handler_idx < 5

    # printer-хук: полная игра без stdout
    from nba_analysis.config import AnalysisConfig
    cfg = AnalysisConfig()
    data = load_dataset(cfg)
    a, b = build_lineups(cfg, data)[:2]
    from nba_analysis.textgame.engine import simulate_game
    score_a, score_b = simulate_game(
        a, b, data.context, possessions=4, seed=5,
        show_court_first=False, printer=printed.append, on_tick=lambda s: None,
    )
    assert isinstance(score_a, int) and isinstance(score_b, int)
    assert any("ИТОГ" in line for line in printed)

