"""Tests for NBA analysis package."""
import pytest
from nba_analysis.models import Player, Lineup
from nba_analysis.data_loader import normalize_position, normalize_stat
from nba_analysis.lineup_builder import lineup_by_position
from nba_analysis.config import POS_MAP, CHEM_MIN, CHEM_MAX
from nba_analysis.chemistry import cosine_similarity, chemistry, clear_chemistry_cache
from nba_analysis.simulation import possession, simulate_game


class TestConfig:
    """Tests for configuration and utilities."""
    
    def test_normalize_position_standard(self):
        assert normalize_position('PG') == 'PG'
        assert normalize_position('SG') == 'SG'
        assert normalize_position('SF') == 'SF'
        assert normalize_position('PF') == 'PF'
        assert normalize_position('C') == 'C'
    
    def test_normalize_position_hybrid(self):
        assert normalize_position('G') == 'PG'
        assert normalize_position('F') == 'SF'
        assert normalize_position('G-F') == 'SG'
        assert normalize_position('F-C') == 'PF'
        assert normalize_position('C-F') == 'PF'
        assert normalize_position('SG-SF') == 'SG'
        assert normalize_position('PG-SG') == 'PG'
    
    def test_normalize_position_unknown(self):
        assert normalize_position('XYZ') == 'SF'  # default
        assert normalize_position('') == 'SF'


class TestModels:
    """Tests for data models."""
    
    def test_player_creation(self):
        p = Player(
            player='Test Player', team='TST', pos='PG', original_pos='PG',
            season='2024', lg='NBA', ows=5.0, dws=3.0, ws=8.0,
            obpm=2.0, dbpm=1.5, vorp=3.5, per=20.0,
            usg=25.0, ast=30.0, stl=2.0, blk=0.5, tov=3.0,
            orb=2.0, drb=8.0, trb=10.0, ts=0.58, x3p_ar=0.35, f_tr=0.3, mp=2000
        )
        assert p.player == 'Test Player'
        assert p.pos == 'PG'
        assert p.get_metric('ws') == 8.0
        assert p.get_metric('ows') == 5.0
        assert p.get_metric('dws') == 3.0
    
    def test_player_get_metric_unknown(self):
        p = Player(
            player='Test', team='TST', pos='PG', original_pos='PG',
            season='2024', lg='NBA', ows=5.0, dws=3.0, ws=8.0,
            obpm=2.0, dbpm=1.5, vorp=3.5, per=20.0,
            usg=25.0, ast=30.0, stl=2.0, blk=0.5, tov=3.0,
            orb=2.0, drb=8.0, trb=10.0, ts=0.58, x3p_ar=0.35, f_tr=0.3, mp=2000
        )
        assert p.get_metric('unknown') == 0.0
    
    def test_lineup_creation_valid(self):
        players = [Player(
            player=f'Player{i}', team='TST', pos=pos, original_pos=pos,
            season='2024', lg='NBA', ows=5.0, dws=3.0, ws=8.0,
            obpm=2.0, dbpm=1.5, vorp=3.5, per=20.0,
            usg=25.0, ast=30.0, stl=2.0, blk=0.5, tov=3.0,
            orb=2.0, drb=8.0, trb=10.0, ts=0.58, x3p_ar=0.35, f_tr=0.3, mp=2000
        ) for i, pos in enumerate(['PG', 'SG', 'SF', 'PF', 'C'])]
        lineup = Lineup(players=players, name='Test', metric='ws')
        assert len(lineup.players) == 5
        assert lineup.get_assigned_positions() == ['PG', 'SG', 'SF', 'PF', 'C']
    
    def test_lineup_creation_invalid(self):
        players = [Player(
            player=f'Player{i}', team='TST', pos='PG', original_pos='PG',
            season='2024', lg='NBA', ows=5.0, dws=3.0, ws=8.0,
            obpm=2.0, dbpm=1.5, vorp=3.5, per=20.0,
            usg=25.0, ast=30.0, stl=2.0, blk=0.5, tov=3.0,
            orb=2.0, drb=8.0, trb=10.0, ts=0.58, x3p_ar=0.35, f_tr=0.3, mp=2000
        ) for i in range(3)]
        with pytest.raises(ValueError):
            Lineup(players=players, name='Test', metric='ws')


class TestDataLoader:
    """Tests for data loading utilities."""
    
    def test_normalize_stat_empty(self):
        assert normalize_stat([]) == []
    
    def test_normalize_stat_equal(self):
        assert normalize_stat([5.0, 5.0, 5.0]) == [0.5, 0.5, 0.5]
    
    def test_normalize_stat_normal(self):
        result = normalize_stat([0.0, 5.0, 10.0])
        assert result == [0.0, 0.5, 1.0]
    
    def test_normalize_stat_negative(self):
        result = normalize_stat([-10.0, 0.0, 10.0])
        assert result == [0.0, 0.5, 1.0]


class TestChemistry:
    """Tests for chemistry calculations."""
    
    def setup_method(self):
        clear_chemistry_cache()
    
    def test_cosine_similarity_identical(self):
        v = [1.0, 2.0, 3.0]
        assert cosine_similarity(v, v) == 1.0
    
    def test_cosine_similarity_orthogonal(self):
        v1 = [1.0, 0.0, 0.0]
        v2 = [0.0, 1.0, 0.0]
        assert cosine_similarity(v1, v2) == 0.0
    
    def test_cosine_similarity_opposite(self):
        v1 = [1.0, 0.0]
        v2 = [-1.0, 0.0]
        assert cosine_similarity(v1, v2) == -1.0
    
    def test_cosine_similarity_zero_norm(self):
        assert cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0
        assert cosine_similarity([1.0, 2.0], [0.0, 0.0]) == 0.0
    
    def test_chemistry_same_player(self):
        p1 = Player(
            player='P1', team='TST', pos='PG', original_pos='PG',
            season='2024', lg='NBA', ows=5.0, dws=3.0, ws=8.0,
            obpm=2.0, dbpm=1.5, vorp=3.5, per=20.0,
            usg=25.0, ast=30.0, stl=2.0, blk=0.5, tov=3.0,
            orb=2.0, drb=8.0, trb=10.0, ts=0.58, x3p_ar=0.35, f_tr=0.3, mp=2000
        )
        p1.offs = 0.8
        p1.defs = 0.6
        p1.usage = 0.7
        p1.ast_norm = 0.5
        p1.x3p = 0.4
        p1.trb_norm = 0.3
        p1.vec = [0.8, 0.6, 0.4, 0.5, 0.3]
        
        # Same player should have high similarity
        result = chemistry(p1, p1, {})
        assert result > 0.3  # Similarity of 1.0, log(1+0)=0, usg_diff=0
    
    def test_chemistry_clamping(self):
        p1 = Player(
            player='P1', team='TST', pos='PG', original_pos='PG',
            season='2024', lg='NBA', ows=5.0, dws=3.0, ws=8.0,
            obpm=2.0, dbpm=1.5, vorp=3.5, per=20.0,
            usg=25.0, ast=30.0, stl=2.0, blk=0.5, tov=3.0,
            orb=2.0, drb=8.0, trb=10.0, ts=0.58, x3p_ar=0.35, f_tr=0.3, mp=2000
        )
        p1.offs = 1.0
        p1.defs = 1.0
        p1.usage = 0.0
        p1.ast_norm = 1.0
        p1.x3p = 1.0
        p1.trb_norm = 1.0
        p1.vec = [1.0, 1.0, 1.0, 1.0, 1.0]
        
        p2 = Player(
            player='P2', team='TST', pos='SG', original_pos='SG',
            season='2024', lg='NBA', ows=5.0, dws=3.0, ws=8.0,
            obpm=2.0, dbpm=1.5, vorp=3.5, per=20.0,
            usg=25.0, ast=30.0, stl=2.0, blk=0.5, tov=3.0,
            orb=2.0, drb=8.0, trb=10.0, ts=0.58, x3p_ar=0.35, f_tr=0.3, mp=2000
        )
        p2.offs = 0.0
        p2.defs = 0.0
        p2.usage = 1.0
        p2.ast_norm = 0.0
        p2.x3p = 0.0
        p2.trb_norm = 0.0
        p2.vec = [0.0, 0.0, 0.0, 0.0, 0.0]
        
        # Should be clamped to CHEM_MIN
        result = chemistry(p1, p2, {('P1', 'P2'): 10000})  # large co-play
        from nba_analysis.config import CHEM_MIN, CHEM_MAX
        assert CHEM_MIN <= result <= CHEM_MAX


class TestSimulation:
    """Tests for game simulation."""
    
    def create_test_player(self, name, pos, offs=0.5, defs=0.5, usage=0.2, x3p=0.35, orb=0.1, drb=0.2):
        p = Player(
            player=name, team='TST', pos=pos, original_pos=pos,
            season='2024', lg='NBA', ows=5.0, dws=3.0, ws=8.0,
            obpm=2.0, dbpm=1.5, vorp=3.5, per=20.0,
            usg=25.0, ast=30.0, stl=2.0, blk=0.5, tov=3.0,
            orb=2.0, drb=8.0, trb=10.0, ts=0.58, x3p_ar=0.35, f_tr=0.3, mp=2000
        )
        p.offs = offs
        p.defs = defs
        p.usage = usage
        p.x3p = x3p
        p.orb = orb
        p.drb = drb
        p.vec = [offs, defs, x3p, 0.5, 0.5]
        return p
    
    def test_possession_returns_points(self):
        offense = [self.create_test_player(f'O{i}', pos) for i, pos in enumerate(['PG','SG','SF','PF','C'])]
        defense = [self.create_test_player(f'D{i}', pos) for i, pos in enumerate(['PG','SG','SF','PF','C'])]
        
        pts, reb = possession(offense, defense, chem_bonus=0.0, co_minutes_dict={})
        assert isinstance(pts, int)
        assert pts in (0, 2, 3)
        assert reb in (None, 'off', 'def')
    
    def test_simulate_game_returns_scores(self):
        offense = [self.create_test_player(f'O{i}', pos) for i, pos in enumerate(['PG','SG','SF','PF','C'])]
        defense = [self.create_test_player(f'D{i}', pos) for i, pos in enumerate(['PG','SG','SF','PF','C'])]
        
        score_a, score_b = simulate_game(offense, defense, chem_bonus=0.0, possessions=10, co_minutes_dict={})
        assert isinstance(score_a, int)
        assert isinstance(score_b, int)
        assert score_a >= 0
        assert score_b >= 0


class TestLineupBuilder:
    """Tests for lineup building."""
    
    def create_test_players(self):
        """Create a set of test players with different positions and metrics."""
        players = []
        positions = ['PG', 'SG', 'SF', 'PF', 'C']
        for i, pos in enumerate(positions):
            for j in range(3):  # 3 players per position
                p = Player(
                    player=f'{pos}{j}', team='TST', pos=pos, original_pos=pos,
                    season='2024', lg='NBA', ows=5.0+j, dws=3.0, ws=8.0+j,
                    obpm=2.0, dbpm=1.5, vorp=3.5, per=20.0,
                    usg=25.0, ast=30.0, stl=2.0, blk=0.5, tov=3.0,
                    orb=2.0, drb=8.0, trb=10.0, ts=0.58, x3p_ar=0.35, f_tr=0.3, mp=2000
                )
                players.append(p)
        return players
    
    def test_lineup_by_position_ws(self):
        players = self.create_test_players()
        lineup = lineup_by_position(players, 'ws')
        assert len(lineup) == 5
        # Should pick the highest WS for each position (j=2 has ws=10.0)
        for p in lineup:
            assert p.player.endswith('2')  # PG2, SG2, SF2, PF2, C2
    
    def test_lineup_by_position_ows(self):
        players = self.create_test_players()
        lineup = lineup_by_position(players, 'ows')
        assert len(lineup) == 5
        for p in lineup:
            assert p.player.endswith('2')
    
    def test_lineup_no_duplicates(self):
        players = self.create_test_players()
        lineup = lineup_by_position(players, 'ws')
        names = [p.player for p in lineup]
        assert len(names) == len(set(names))  # No duplicates


if __name__ == '__main__':
    pytest.main([__file__, '-v'])