"""Command-line interface for NBA analysis."""
import argparse
import sys
from .main import main as run_analysis
from .config import NUM_GAMES_SIM, CHEMISTRY_BONUS_WEIGHT, OUTPUT_PATH


def parse_args():
    parser = argparse.ArgumentParser(
        description='NBA Historical Lineup Analysis and Simulation',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        '--games', '-g', type=int, default=NUM_GAMES_SIM,
        help='Number of games to simulate per matchup'
    )
    parser.add_argument(
        '--chem-weight', '-c', type=float, default=CHEMISTRY_BONUS_WEIGHT,
        help='Chemistry bonus weight (scale factor)'
    )
    parser.add_argument(
        '--output', '-o', type=str, default=OUTPUT_PATH,
        help='Output markdown file path'
    )
    parser.add_argument(
        '--quick', '-q', action='store_true',
        help='Quick mode: only 10 games per matchup for testing'
    )
    parser.add_argument(
        '--list-lineups', '-l', action='store_true',
        help='Only build and print lineups, skip simulation'
    )
    parser.add_argument(
        '--version', '-v', action='version',
        version='%(prog)s 2.0.0'
    )
    return parser.parse_args()


def main():
    args = parse_args()
    
    if args.quick:
        print('Quick mode: 10 games per matchup')
        # Override the constant for this run
        import nba_analysis.config as config
        config.NUM_GAMES_SIM = 10
        config.CHEMISTRY_BONUS_WEIGHT = args.chem_weight
        config.OUTPUT_PATH = args.output
    else:
        import nba_analysis.config as config
        config.NUM_GAMES_SIM = args.games
        config.CHEMISTRY_BONUS_WEIGHT = args.chem_weight
        config.OUTPUT_PATH = args.output
    
    if args.list_lineups:
        from nba_analysis.data_loader import load_players, prepare_players
        from nba_analysis.lineup_builder import lineup_by_position
        
        print('Loading players...')
        players = load_players()
        players = prepare_players(players)
        
        overall = lineup_by_position(players, 'ws')
        offense = lineup_by_position(players, 'ows')
        defense = lineup_by_position(players, 'dws')
        
        print('\n=== BEST OVERALL FIVE (WS) ===')
        for i, p in enumerate(overall):
            print(f'  {i+1}. {p.player} ({p.pos}) - WS: {p.ws:.2f}')
        
        print('\n=== BEST OFFENSIVE FIVE (OWS) ===')
        for i, p in enumerate(offense):
            print(f'  {i+1}. {p.player} ({p.pos}) - OWS: {p.ows:.2f}')
        
        print('\n=== BEST DEFENSIVE FIVE (DWS) ===')
        for i, p in enumerate(defense):
            print(f'  {i+1}. {p.player} ({p.pos}) - DWS: {p.dws:.2f}')
        return
    
    run_analysis()


if __name__ == '__main__':
    main()