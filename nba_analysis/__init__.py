"""NBA Analysis Package."""
from .config import (
    DATA_PATH, OUTPUT_PATH,
    LEAGUE_FG, POSSESSIONS_PER_GAME, NUM_GAMES_SIM,
    W_SIM, W_CO, W_USG_DIFF, CHEMISTRY_BONUS_WEIGHT,
    POS_MAP, STANDARD_POSITIONS
)
from .models import Player, Lineup
from .data_loader import load_players, prepare_players, compute_co_play_minutes, normalize_position
from .lineup_builder import lineup_by_position
from .chemistry import chemistry, get_team_chemistry_sum, clear_chemistry_cache
from .simulation import possession, simulate_game, evaluate_lineup, simulate_matchup
from .reporter import format_md_lineup, format_md_simulation_results, generate_report, save_report
from .main import main
from .cli import main as cli_main

__all__ = [
    # config
    'DATA_PATH', 'OUTPUT_PATH',
    'LEAGUE_FG', 'POSSESSIONS_PER_GAME', 'NUM_GAMES_SIM',
    'W_SIM', 'W_CO', 'W_USG_DIFF', 'CHEMISTRY_BONUS_WEIGHT',
    'POS_MAP', 'STANDARD_POSITIONS',
    # models
    'Player', 'Lineup',
    # data_loader
    'load_players', 'prepare_players', 'compute_co_play_minutes', 'normalize_position',
    # lineup_builder
    'lineup_by_position',
    # chemistry
    'chemistry', 'get_team_chemistry_sum', 'clear_chemistry_cache',
    # simulation
    'possession', 'simulate_game', 'evaluate_lineup', 'simulate_matchup',
    # reporter
    'format_md_lineup', 'format_md_simulation_results', 'generate_report', 'save_report',
    # main
    'main',
    # cli
    'cli_main',
]

__version__ = '2.0.0'