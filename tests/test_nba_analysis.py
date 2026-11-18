"""Тесты пакета nba_analysis."""
from __future__ import annotations

import random
import textwrap
from dataclasses import replace

import pytest

from nba_analysis.chemistry import ChemistryModel, compute_shared_minutes, cosine_similarity
from nba_analysis.cli import build_parser, config_from_args
from nba_analysis.config import AnalysisConfig, ChemistryConfig, SimulationConfig
from nba_analysis.data_loader import (
    filter_players, load_players, normalize_position, parse_row, season_rows, team_rows,
)
from nba_analysis.lineup_builder import best_lineup
from nba_analysis.models import Lineup, Player, is_aggregate_team
from nba_analysis.profiles import LeagueContext, build_profile, least_squares
from nba_analysis.simulation import Simulator, average_point_diff, round_robin

POSITIONS = ("PG", "SG", "SF", "PF", "C")


def make_player(pid="p1", pos="SF", season=2020, team="TST", **stats) -> Player:
    """Игрок с «средними» современными показателями; любые поля можно переопределить."""
    base = dict(
        mp=2000.0, per=15.0, ts_percent=0.56, x3p_ar=0.35, f_tr=0.25,
        orb_percent=5.0, drb_percent=15.0, trb_percent=10.0, ast_percent=15.0,
        stl_percent=1.5, blk_percent=1.5, tov_percent=12.0, usg_percent=20.0,
        ows=3.0, dws=2.0, ws=5.0, ws_48=0.12, obpm=0.0, dbpm=0.0, bpm=0.0, vorp=1.0,
    )
    base.update(stats)
    return Player(player_id=pid, name=pid.upper(), season=season, lg="NBA", team=team,
                  pos=pos, original_pos=pos, g=70, **base)


def make_lineup(prefix: str, name: str | None = None, **stats) -> Lineup:
    players = tuple(make_player(f"{prefix}{i}", pos, **stats) for i, pos in enumerate(POSITIONS))
    return Lineup(name=name or prefix, metric="ws", players=players)


@pytest.fixture
def ctx() -> LeagueContext:
    rows = [make_player(f"ctx{i}", POSITIONS[i % 5]) for i in range(20)]
    return LeagueContext(rows)


# --- data loading -----------------------------------------------------------

class TestDataLoader:
    def test_normalize_position(self):
        assert normalize_position("PG") == "PG"
        assert normalize_position(" g-f ") == "SG"
        assert normalize_position("F-C") == "PF"
        assert normalize_position("XYZ") == "SF"
        assert normalize_position(None) == "SF"

    def test_parse_row_treats_na_as_missing(self):
        # Регрессия: раньше строка с "NA" в любой колонке молча выбрасывалась,
        # из-за чего пропадали все сезоны до 1974 года.
        p = parse_row({"player": "Bill Russell", "player_id": "russebi01", "season": "1964",
                       "lg": "NBA", "team": "BOS", "pos": "C", "g": "78", "mp": "3482",
                       "dws": "16.0", "dbpm": "NA", "usg_percent": "NA"})
        assert p is not None
        assert p.season == 1964 and p.mp == 3482.0 and p.dws == 16.0
        assert p.dbpm is None and p.usg_percent is None

    def test_parse_row_rejects_rows_without_identity(self):
        assert parse_row({"player": "", "player_id": "x", "season": "2020"}) is None
        assert parse_row({"player": "X", "player_id": "", "season": "2020"}) is None

    def test_load_players_from_csv(self, tmp_path):
        csv_path = tmp_path / "players.csv"
        csv_path.write_text(textwrap.dedent("""\
            season,lg,player,player_id,age,team,pos,g,mp,ws,dbpm
            2020,NBA,A One,aone01,25,LAL,PG,70,2000,5.0,1.0
            2020,NBA,B Two,btwo01,NA,BOS,C,60,NA,3.0,NA
        """), encoding="utf-8")
        players = load_players(csv_path)
        assert [p.player_id for p in players] == ["aone01", "btwo01"]
        assert players[1].age is None and players[1].mp is None

    def test_aggregate_team_detection(self):
        assert is_aggregate_team("2TM") and is_aggregate_team("3TM") and is_aggregate_team("TOT")
        assert not is_aggregate_team("LAL") and not is_aggregate_team("TMX")

    def test_season_rows_prefers_aggregate_row(self):
        rows = [
            make_player("traded", team="2TM", ws=8.0),
            make_player("traded", team="LAL", ws=5.0),
            make_player("traded", team="BOS", ws=3.0),
            make_player("stayed", team="MIA", ws=6.0),
        ]
        assert sorted((p.player_id, p.team) for p in season_rows(rows)) == [
            ("stayed", "MIA"), ("traded", "2TM")]
        assert all(not p.is_aggregate for p in team_rows(rows))

    def test_filter_players(self):
        rows = [make_player("a", mp=500), make_player("b", season=1990),
                make_player("c"), replace(make_player("d"), lg="ABA")]
        kept = filter_players(rows, min_minutes=1000, season_from=2000, leagues=["NBA"])
        assert [p.player_id for p in kept] == ["c"]


# --- models -----------------------------------------------------------------

class TestModels:
    def test_get_metric(self):
        p = make_player(ws=8.0, dbpm=None)
        assert p.get_metric("ws") == 8.0
        assert p.get_metric("dbpm") == float("-inf")
        with pytest.raises(ValueError):
            p.get_metric("not_a_metric")

    def test_lineup_validation(self):
        with pytest.raises(ValueError, match="exactly 5"):
            Lineup("x", "ws", tuple(make_player(f"p{i}") for i in range(3)))
        same = tuple(make_player("dup", season=2000 + i) for i in range(5))
        with pytest.raises(ValueError, match="same player"):
            Lineup("x", "ws", same)


# --- lineup builder ---------------------------------------------------------

class TestLineupBuilder:
    def test_picks_best_per_position(self):
        players = [make_player(f"{pos}{j}", pos, ws=8.0 + j) for pos in POSITIONS for j in range(3)]
        lineup = best_lineup(players, "ws")
        assert [p.player_id for p in lineup] == [f"{pos}2" for pos in POSITIONS]
        assert lineup.positions == POSITIONS

    def test_same_player_used_once(self):
        # Один и тот же игрок лучший и как SF, и как PF (разные сезоны).
        players = [
            make_player("lebron", "SF", season=2009, ws=20.0),
            make_player("lebron", "PF", season=2013, ws=19.0),
            make_player("pf_other", "PF", ws=10.0),
            *[make_player(f"{pos}x", pos, ws=5.0) for pos in ("PG", "SG", "C")],
        ]
        lineup = best_lineup(players, "ws")
        ids = [p.player_id for p in lineup]
        assert ids.count("lebron") == 1
        assert dict(zip(lineup.positions, ids))["PF"] == "pf_other"

    def test_fills_missing_position_with_best_remaining(self):
        players = [make_player(f"g{i}", "PG", ws=10.0 - i) for i in range(5)]
        lineup = best_lineup(players, "ws")
        assert len({p.player_id for p in lineup}) == 5

    def test_not_enough_players(self):
        with pytest.raises(ValueError):
            best_lineup([make_player("a")], "ws")


# --- profiles ---------------------------------------------------------------

class TestProfiles:
    def test_least_squares_recovers_line(self):
        xs = [[x] for x in range(10)]
        ys = [3 * x + 2 for x in range(10)]
        a, b = least_squares(xs, ys)
        assert a == pytest.approx(3) and b == pytest.approx(2)

    def test_missing_stats_are_imputed(self, ctx):
        old = make_player("old", season=2020, usg_percent=None, tov_percent=None, dbpm=None)
        assert ctx.stat(old, "tov_percent") == pytest.approx(12.0)  # среднее по сезону
        assert ctx.stat(old, "usg_percent") > 0                     # регрессия по PER/TS
        assert isinstance(ctx.dbpm(old), float)

    def test_three_rate_defaults_to_zero_before_three_point_era(self, ctx):
        p = make_player("old", season=1965, x3p_ar=None)
        assert ctx.stat(p, "x3p_ar") == 0.0

    def test_profile_is_consistent_with_ts(self, ctx):
        cfg = SimulationConfig(era_adjust=False)
        good = build_profile(make_player("good", ts_percent=0.65), ctx, cfg)
        bad = build_profile(make_player("bad", ts_percent=0.48), ctx, cfg)
        assert good.p2 > bad.p2 and good.p3 > bad.p3
        for prof in (good, bad):
            assert 0 < prof.p3 < prof.p2 <= cfg.max_make_prob
            assert 0 <= prof.tov_rate < 0.5 and 0 <= prof.ft_trip_rate < 1


# --- chemistry --------------------------------------------------------------

class TestChemistry:
    def test_cosine_similarity(self):
        assert cosine_similarity([1, 2, 3], [1, 2, 3]) == pytest.approx(1.0)
        assert cosine_similarity([1, 0], [0, 1]) == 0.0
        assert cosine_similarity([0, 0], [1, 2]) == 0.0

    def test_shared_minutes_ignore_aggregate_rows(self):
        rows = [
            make_player("a", team="LAL", mp=2000), make_player("b", team="LAL", mp=1500),
            make_player("c", team="2TM", mp=2500), make_player("d", team="2TM", mp=2500),
        ]
        shared = compute_shared_minutes(rows)
        assert shared == {("a", "b"): 1500}

    def test_familiarity_saturates(self):
        model = ChemistryModel({("a", "b"): 10**6, ("a", "c"): 100})
        assert model.familiarity("a", "b") == 1.0
        assert 0 < model.familiarity("c", "a") < 1
        assert model.familiarity("a", "zzz") == 0.0

    def test_pair_is_clamped_and_symmetric(self, ctx):
        cfg = ChemistryConfig()
        model = ChemistryModel({("a", "b"): 10**6}, cfg)
        a = build_profile(make_player("a"), ctx, SimulationConfig())
        b = build_profile(make_player("b"), ctx, SimulationConfig())
        assert cfg.chem_min <= model.pair(a, b) <= cfg.chem_max
        assert model.pair(a, b) == model.pair(b, a)

    def test_two_ball_dominant_players_have_worse_chemistry(self, ctx):
        model = ChemistryModel({})
        sim = SimulationConfig()
        star1 = build_profile(make_player("s1", usg_percent=33), ctx, sim)
        star2 = build_profile(make_player("s2", usg_percent=33), ctx, sim)
        role = build_profile(make_player("r", usg_percent=14), ctx, sim)
        assert model.pair(star1, star2) < model.pair(star1, role)


# --- simulation -------------------------------------------------------------

class TestSimulation:
    def test_possession_points_are_valid(self, ctx):
        sim = Simulator(ctx, SimulationConfig(seed=1))
        a, b = sim.team_state(make_lineup("a")), sim.team_state(make_lineup("b"))
        points = [sim.possession(a, b) for _ in range(2000)]
        assert min(points) >= 0
        assert 0.85 < sum(points) / len(points) < 1.35  # реалистичные очки за владение

    def test_seed_makes_results_reproducible(self, ctx):
        cfg = SimulationConfig(seed=42)
        r1 = Simulator(ctx, cfg).play_series(make_lineup("a"), make_lineup("b"), games=50)
        r2 = Simulator(ctx, cfg).play_series(make_lineup("a"), make_lineup("b"), games=50)
        assert r1 == r2

    def test_games_have_no_ties_and_counts_add_up(self, ctx):
        sim = Simulator(ctx, SimulationConfig(possessions_per_game=20), rng=random.Random(0))
        r = sim.play_series(make_lineup("a"), make_lineup("b"), games=300)
        assert r.wins_a + r.wins_b >= 295  # ничьи возможны только после 5 овертаймов

    def test_better_shooters_win(self, ctx):
        sim = Simulator(ctx, SimulationConfig(seed=7, era_adjust=False))
        r = sim.play_series(make_lineup("good", ts_percent=0.62), make_lineup("bad", ts_percent=0.50), 300)
        assert r.mean_diff > 5 and r.win_pct_a > 0.7

    def test_better_defense_lowers_opponent_score(self, ctx):
        sim = Simulator(ctx, SimulationConfig(seed=7))
        offense = make_lineup("off")
        vs_avg = sim.play_series(offense, make_lineup("avg", dbpm=0.0), 300)
        vs_elite = sim.play_series(offense, make_lineup("elite", dbpm=3.0), 300)
        assert vs_elite.avg_score_a < vs_avg.avg_score_a

    def test_round_robin_and_average_diff(self, ctx):
        sim = Simulator(ctx, SimulationConfig(seed=3))
        lineups = [make_lineup("a"), make_lineup("b"), make_lineup("c")]
        results = round_robin(sim, lineups, games=20)
        assert len(results) == 3
        diffs = average_point_diff(results)
        assert set(diffs) == {"a", "b", "c"}
        assert sum(diffs.values()) == pytest.approx(0.0, abs=1e-9)


# --- CLI / pipeline ---------------------------------------------------------

class TestCli:
    def test_config_from_args(self):
        args = build_parser().parse_args(["-q", "--seed", "5", "--from", "1980", "--no-era-adjust"])
        cfg = config_from_args(args)
        assert cfg.simulation.games == 100
        assert cfg.simulation.seed == 5 and cfg.simulation.era_adjust is False
        assert cfg.season_from == 1980
        # Глобальная конфигурация не мутируется.
        assert AnalysisConfig().simulation.games == SimulationConfig().games


@pytest.mark.skipif(not AnalysisConfig().data_path.exists(), reason="data/Players.csv not found")
class TestRealData:
    def test_pipeline_end_to_end(self, tmp_path):
        from nba_analysis.pipeline import run_analysis
        from nba_analysis.reporter import generate_report, save_report

        cfg = replace(AnalysisConfig(), simulation=SimulationConfig(games=5, seed=1),
                      output_path=tmp_path / "report.md")
        result = run_analysis(cfg)
        assert [lu.name for lu in result.lineups] == ["Overall", "Offense", "Defense"]
        # До исправления парсинга "NA" сезонов до 1974 года не было вовсе.
        assert min(p.season for p in result.lineups[2]) < 1974
        save_report(generate_report(result), cfg.output_path)
        text = cfg.output_path.read_text(encoding="utf-8")
        assert "Michael Jordan" in text and "| Matchup |" in text
