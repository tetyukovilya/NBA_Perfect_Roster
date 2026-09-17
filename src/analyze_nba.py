import pandas as pd
import os

def main():
    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Project root is one level up from src
    project_root = os.path.dirname(script_dir)
    data_path = os.path.join(project_root, 'data', 'Players.csv')
    
    # Read all lines, split on first '|', take the second part (the CSV line)
    with open(data_path, 'r') as f:
        lines = f.readlines()
    
    # Process lines: remove newline, split on first '|'
    csv_lines = []
    for line in lines:
        line = line.strip()
        if '|' in line:
            # Split on first '|'
            parts = line.split('|', 1)
            csv_lines.append(parts[1])
        else:
            # If no pipe, skip or handle? Assume header line might not have pipe? But we saw it does.
            csv_lines.append(line)
    
    # Now csv_lines[0] is the header line
    header = csv_lines[0]
    data_rows = csv_lines[1:]
    
    # Split each row by commas
    data = [row.split(',') for row in data_rows]
    
    # Create DataFrame
    df = pd.DataFrame(data, columns=header.split(','))
    
    print("Dataset shape:", df.shape)
    print("\nColumns:", df.columns.tolist())
    print("\nFirst few rows:")
    print(df.head())
    
    # Filter for the most recent season (2026)
    df_2026 = df[df['season'] == '2026']
    print("\nNumber of players in 2026 season:", df_2026.shape[0])
    
    # For each position, we'll define a score.
    # We'll normalize the stats and then compute a weighted sum.
    
    # Let's first see the unique positions
    print("\nUnique positions:", df_2026['pos'].unique())
    
    # We'll define position-specific scores.
    # We'll use the following stats (higher is better)
    position_stats = {
        'PG': ['ast_percent', 'stl_percent', 'tov_percent', 'ws', 'bpm', 'vorp'],  # tov_percent is negative (lower is better)
        'SG': ['ts_percent', 'x3p_ar', 'ws', 'bpm', 'vorp', 'stl_percent'],
        'SF': ['ts_percent', 'trb_percent', 'ws', 'bpm', 'vorp', 'stl_percent'],
        'PF': ['trb_percent', 'orb_percent', 'ws', 'bpm', 'vorp', 'blk_percent'],
        'C':  ['trb_percent', 'blk_percent', 'ws', 'bpm', 'vorp', 'ts_percent']
    }
    
    # Convert relevant columns to numeric, coercing errors to NaN
    stat_columns = set()
    for stats in position_stats.values():
        stat_columns.update(stats)
    # Also include tov_percent_inv later
    for col in stat_columns:
        if col in df_2026.columns:
            df_2026[col] = pd.to_numeric(df_2026[col], errors='coerce')
    
    # We'll invert tov_percent so that higher is better (lower turnovers -> higher score)
    df_2026['tov_percent_inv'] = -df_2026['tov_percent']
    
    # For each position, compute a score
    best_players = {}
    for pos, stats in position_stats.items():
        # Filter players of this position
        pos_df = df_2026[df_2026['pos'] == pos].copy()
        if pos_df.empty:
            print(f"No players found for position {pos}")
            continue
        
        # Adjust stats: for tov_percent we already inverted, but note that in the list we used 'tov_percent' for PG.
        # We'll replace 'tov_percent' with 'tov_percent_inv' in the stats list for PG.
        if pos == 'PG':
            adjusted_stats = [s if s != 'tov_percent' else 'tov_percent_inv' for s in stats]
        else:
            adjusted_stats = stats
        
        # Normalize each stat (z-score) and then sum
        for stat in adjusted_stats:
            if stat in pos_df.columns:
                # Avoid division by zero if std is zero
                if pos_df[stat].std() == 0 or pd.isna(pos_df[stat].std()):
                    pos_df[stat + '_norm'] = 0
                else:
                    pos_df[stat + '_norm'] = (pos_df[stat] - pos_df[stat].mean()) / pos_df[stat].std()
            else:
                print(f"Warning: {stat} not in columns for {pos}")
        
        # Sum the normalized stats to get a score
        norm_cols = [stat + '_norm' for stat in adjusted_stats if stat in pos_df.columns]
        pos_df['score'] = pos_df[norm_cols].sum(axis=1, skipna=True)
        
        # Select the top player (drop NaN scores)
        pos_df = pos_df.dropna(subset=['score'])
        if pos_df.empty:
            print(f"No valid scores for position {pos}")
            continue
        top_player = pos_df.loc[pos_df['score'].idxmax()]
        best_players[pos] = top_player[['player', 'pos', 'score'] + adjusted_stats]
        print(f"\nTop {pos}:")
        print(best_players[pos][['player', 'pos', 'score']])
    
    # Display the starting five
    print("\n\nStarting Five (2026 season):")
    for pos in ['PG', 'SG', 'SF', 'PF', 'C']:
        if pos in best_players:
            player_name = best_players[pos]['player']
            score = best_players[pos]['score']
            print(f"{pos}: {player_name} (Score: {score:.2f})")

if __name__ == "__main__":
    main()