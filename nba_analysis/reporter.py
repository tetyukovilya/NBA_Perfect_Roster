"""Markdown-отчёт по результатам анализа."""
from __future__ import annotations

from pathlib import Path

from .models import Lineup
from .pipeline import AnalysisResult

_METRIC_TITLES = {
    "ws": "Win Shares",
    "ows": "Offensive Win Shares",
    "dws": "Defensive Win Shares",
}


def _fmt(value: float | None, spec: str = ".1f") -> str:
    return "—" if value is None else format(value, spec)


def format_lineup(lineup: Lineup) -> str:
    title = _METRIC_TITLES.get(lineup.metric, lineup.metric.upper())
    metric = lineup.metric.upper()
    lines = [
        f"## {lineup.name} — {title}",
        "",
        f"| Pos | Player | Season | Team | Orig. pos | {metric} | OBPM | DBPM | VORP | PER | TS% | USG% |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for pos, p in lineup.slots():
        lines.append(
            f"| {pos} | **{p.name}** | {p.season} {p.lg} | {p.team} | {p.original_pos or '—'} "
            f"| {_fmt(getattr(p, lineup.metric), '.2f')} | {_fmt(p.obpm)} | {_fmt(p.dbpm)} "
            f"| {_fmt(p.vorp)} | {_fmt(p.per)} | {_fmt(p.ts_percent, '.3f')} | {_fmt(p.usg_percent)} |"
        )
    return "\n".join(lines)


def format_simulation(result: AnalysisResult) -> str:
    sim = result.config.simulation
    lines = [
        "# Simulation",
        "",
        f"{sim.games} games per matchup, {sim.possessions_per_game} possessions per team, "
        f"chemistry weight {sim.chemistry_weight}, era adjustment {'on' if sim.era_adjust else 'off'}, "
        f"seed {sim.seed}.",
        "",
        "| Matchup | Avg score | Win % (first) | Avg diff ± SE |",
        "|---|---|---|---|",
    ]
    for r in result.matchups:
        lines.append(
            f"| {r.team_a} vs {r.team_b} | {r.avg_score_a:.1f} : {r.avg_score_b:.1f} "
            f"| {r.win_pct_a:.1%} | {r.mean_diff:+.2f} ± {r.stderr_diff:.2f} |"
        )
    lines += ["", "| Lineup | Avg point diff vs others |", "|---|---|"]
    for name, diff in sorted(result.avg_diff.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {name} | {diff:+.2f} |")
    return "\n".join(lines)


def generate_report(result: AnalysisResult) -> str:
    cfg = result.config
    seasons = f"{cfg.season_from or 'all'}–{cfg.season_to or 'now'}"
    parts = [
        "# Best Starting Fives — All Time (one player per position)",
        "",
        f"Seasons: {seasons}; leagues: {', '.join(cfg.leagues)}; min minutes: {cfg.min_minutes:g}.",
        "",
    ]
    for lineup in result.lineups:
        parts += [format_lineup(lineup), ""]
    parts.append(format_simulation(result))
    return "\n".join(parts) + "\n"


def save_report(content: str, path: Path | str) -> None:
    Path(path).write_text(content, encoding="utf-8")
