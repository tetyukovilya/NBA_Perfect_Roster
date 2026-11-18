"""Конфигурация проекта: пути, константы и настраиваемые параметры.

Все параметры, которые влияют на результат, собраны в неизменяемые dataclass'ы.
CLI и пользовательский код создают изменённые копии через ``dataclasses.replace``,
а не мутируют глобальные переменные модуля.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# --- Пути -------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = PROJECT_ROOT / "data" / "Players.csv"
OUTPUT_PATH = PROJECT_ROOT / "starting_five_2026.md"

# --- Позиции ----------------------------------------------------------------
STANDARD_POSITIONS: tuple[str, ...] = ("PG", "SG", "SF", "PF", "C")
DEFAULT_POSITION = "SF"

# Гибридные/устаревшие обозначения позиций -> одна из пяти стандартных.
POS_MAP: dict[str, str] = {
    "PG": "PG", "SG": "SG", "SF": "SF", "PF": "PF", "C": "C",
    "G": "PG", "F": "SF", "G-F": "SG", "F-G": "SG",
    "F-C": "PF", "C-F": "PF", "C-PF": "PF", "PF-C": "PF",
    "SG-SF": "SG", "SF-SG": "SF", "PG-SG": "PG", "SG-PG": "SG",
}

# Метрики, по которым можно строить пятёрки (числовые поля Player).
LINEUP_METRICS: tuple[str, ...] = (
    "ws", "ows", "dws", "ws_48", "vorp", "bpm", "obpm", "dbpm", "per",
)

# Пятёрки, которые строятся по умолчанию: (название, метрика).
DEFAULT_LINEUPS: tuple[tuple[str, str], ...] = (
    ("Overall", "ws"),
    ("Offense", "ows"),
    ("Defense", "dws"),
)


@dataclass(frozen=True)
class ChemistryConfig:
    """Параметры парной «химии» игроков.

    chem(i, j) = w_similarity    * cos_sim(style_i, style_j)   # 0..1
               + w_familiarity   * familiarity(i, j)           # 0..1, по совместным минутам
               - w_usage_overlap * max(0, usg_i + usg_j - 0.4) # два «мячевых» игрока мешают друг другу
    Результат обрезается до [chem_min, chem_max].
    """

    w_similarity: float = 0.3
    w_familiarity: float = 0.5
    w_usage_overlap: float = 1.0
    # Сколько совместных минут нужно, чтобы familiarity достигла 1.0
    # (дальше — насыщение, шкала логарифмическая).
    familiarity_saturation_minutes: float = 5000.0
    chem_min: float = -0.5
    chem_max: float = 0.5


@dataclass(frozen=True)
class SimulationConfig:
    """Параметры модели владения и серии матчей."""

    games: int = 10_000
    possessions_per_game: int = 100
    # Множитель влияния химии на вероятность попадания:
    # p_make *= 1 + chemistry_weight * mean_chem(ball_handler, teammates)
    chemistry_weight: float = 0.2
    # Чего нет в датасете — берём средние по лиге.
    league_ft_pct: float = 0.75
    # Отношение 3P% к 2P% (≈ 0.36 / 0.52 в современной NBA).
    three_to_two_ratio: float = 0.69
    # Насколько сильно DBPM обороны снижает точность атаки (1.0 = «как в BPM»).
    defense_scale: float = 1.0
    league_points_per_possession: float = 1.10
    # Пересчитывать TS% относительно среднего по сезону (сравнение разных эпох).
    era_adjust: bool = True
    max_make_prob: float = 0.85
    max_offensive_rebounds: int = 5  # защита от бесконечного владения
    seed: int | None = None


@dataclass(frozen=True)
class AnalysisConfig:
    """Полная конфигурация пайплайна."""

    data_path: Path = DATA_PATH
    output_path: Path = OUTPUT_PATH
    # Отсечка по минутам: сезоны на крошечной выборке не годятся для симуляции.
    min_minutes: float = 1000.0
    season_from: int | None = None
    season_to: int | None = None
    leagues: tuple[str, ...] = ("NBA", "ABA", "BAA")
    lineups: tuple[tuple[str, str], ...] = DEFAULT_LINEUPS
    simulation: SimulationConfig = field(default_factory=SimulationConfig)
    chemistry: ChemistryConfig = field(default_factory=ChemistryConfig)
