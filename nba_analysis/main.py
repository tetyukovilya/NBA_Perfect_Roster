"""Main entry point for NBA analysis."""
from .data_loader import load_players, prepare_players, compute_co_play_minutes
from .lineup_builder import lineup_by_position
from .simulation import evaluate_lineup
from .reporter import generate_report, save_report
from .models import Lineup
from . import config


def main():
    print('Loading players...')
    players = load_players()
    print(f'Loaded {len(players)} players')
    
    print('Preparing players...')
    players = prepare_players(players)
    
    print('Computing co-play minutes...')
    co_minutes = compute_co_play_minutes(players)
    print(f'Co-minutes pairs: {len(co_minutes)}')
    
    print('Building lineups...')
    overall = lineup_by_position(players, 'ws')
    offense = lineup_by_position(players, 'ows')
    defense = lineup_by_position(players, 'dws')
    
    print('Overall:', [p.player for p in overall])
    print('Offense:', [p.player for p in offense])
    print('Defense:', [p.player for p in defense])
    
    # Create Lineup objects
    lineups = [
        Lineup(players=overall, name='Overall', metric='ws'),
        Lineup(players=offense, name='Offense', metric='ows'),
        Lineup(players=defense, name='Defense', metric='dws'),
    ]
    
    print('Running simulation...')
    lineup_data = [(l.name, l.players) for l in lineups]
    sim_results = {}
    
    for name_i, lineup_i in lineup_data:
        opps = [lineup_j for name_j, lineup_j in lineup_data if name_j != name_i]
        avg_diff = evaluate_lineup(lineup_i, opps, chem_bonus=config.CHEMISTRY_BONUS_WEIGHT, 
                                   games=config.NUM_GAMES_SIM, co_minutes_dict=co_minutes)
        sim_results[name_i] = {'avg_diff': avg_diff}
        print(f'{name_i} Lineup: {avg_diff:.2f} avg point diff')
    
    print('Generating report...')
    report = generate_report(lineups, sim_results, config.NUM_GAMES_SIM, config.CHEMISTRY_BONUS_WEIGHT)
    save_report(report, config.OUTPUT_PATH)
    print(f'Results written to {config.OUTPUT_PATH}')


if __name__ == '__main__':
    main()