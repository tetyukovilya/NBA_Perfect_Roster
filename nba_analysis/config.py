"""Configuration constants for NBA analysis."""
import os

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(BASE_DIR, 'data', 'Players.csv')
OUTPUT_PATH = os.path.join(BASE_DIR, 'starting_five_2026.md')

# Simulation parameters
LEAGUE_FG = 0.46  # league average field goal percentage (approx)
POSSESSIONS_PER_GAME = 100
NUM_GAMES_SIM = 10000  # number of games to simulate for each lineup
CHEMISTRY_BONUS_WEIGHT = 0.1

# Chemistry weights
W_SIM = 0.6      # skill similarity weight
W_CO = 0.3       # co-play minutes weight
W_USG_DIFF = 0.1 # usage difference penalty

# Position normalization map
POS_MAP = {
    'PG': 'PG', 'SG': 'SG', 'SF': 'SF', 'PF': 'PF', 'C': 'C',
    'G': 'PG', 'F': 'SF', 'G-F': 'SG', 'F-G': 'SG',
    'F-C': 'PF', 'C-F': 'PF', 'C-PF': 'PF', 'PF-C': 'PF',
    'SG-SF': 'SG', 'SF-SG': 'SF', 'PG-SG': 'PG', 'SG-PG': 'SG',
}

DEFAULT_POSITION = 'SF'
STANDARD_POSITIONS = ['PG', 'SG', 'SF', 'PF', 'C']

# Chemistry clamping
CHEM_MIN = -0.5
CHEM_MAX = 0.5

# Shot probability clamping
SHOT_PROB_MIN = 0.0
SHOT_PROB_MAX = 0.9