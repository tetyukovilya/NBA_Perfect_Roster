"""Report generation in Markdown format."""
from typing import List
from .models import Player, Lineup
from .config import STANDARD_POSITIONS


def format_md_lineup(five: List[Player], metric: str) -> str:
    """Format a lineup as markdown (without title header)."""
    lines = []
    for idx, p in enumerate(five):
        assigned_pos = STANDARD_POSITIONS[idx] if idx < len(STANDARD_POSITIONS) else 'N/A'
        original_pos = p.original_pos
        lines.append(
            f'{idx+1}. **{p.player}** (Assigned Pos: {assigned_pos}, Original Pos: {original_pos}, '
            f'{p.team}, {p.season} {p.lg}) '
            f'{metric.upper()}:{p.get_metric(metric):.2f} | '
            f'OBPM:{p.obpm:.2f} DBPM:{p.dbpm:.2f} '
            f'VORP:{p.vorp:.2f} PER:{p.per:.1f}'
        )
    lines.append('')
    return '\n'.join(lines)


def format_md_simulation_results(results: dict, games: int, chem_weight: float) -> str:
    """Format simulation results as markdown."""
    lines = [
        '# Simulation Results (Chemistry Adjusted)',
        f'Each lineup simulated {games} games against each of the other two lineups.',
        f'Chemistry bonus weight: {chem_weight} (scale factor).',
        ''
    ]
    
    for name, data in results.items():
        lines.append(f'## {name} Lineup')
        lines.append(f'Average point difference per game vs other lineups: {data["avg_diff"]:.2f} points')
        lines.append('')
    
    return '\n'.join(lines)


def generate_report(lineups: List[Lineup], sim_results: dict, 
                    games: int, chem_weight: float) -> str:
    """Generate full markdown report."""
    md_lines = []
    
    title_map = {
        'ws': 'Best Overall Five (Win Shares) – All Time (One per Position)',
        'ows': 'Best Offensive Five (Offensive Win Shares) – All Time (One per Position)',
        'dws': 'Best Defensive Five (Defensive Win Shares) – All Time (One per Position)',
    }
    
    # Lineups
    for lineup in lineups:
        title = title_map.get(lineup.metric, f'Best {lineup.metric.upper()} Five')
        md_lines.append(f'# {title}')
        md_lines.append(format_md_lineup(lineup.players, lineup.metric))
    
    # Simulation
    md_lines.append(format_md_simulation_results(sim_results, games, chem_weight))
    
    return '\n'.join(md_lines)


def save_report(content: str, output_path: str) -> None:
    """Save report to file."""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(content)