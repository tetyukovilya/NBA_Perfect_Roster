"""NBA analysis: лучшие пятёрки в истории и симуляция матчей между ними."""

__version__ = "3.0.0"

from .config import AnalysisConfig, ChemistryConfig, SimulationConfig  # noqa: E402
from .models import Lineup, Player  # noqa: E402
from .pipeline import AnalysisResult, run_analysis  # noqa: E402

__all__ = [
    "AnalysisConfig",
    "AnalysisResult",
    "ChemistryConfig",
    "Lineup",
    "Player",
    "SimulationConfig",
    "run_analysis",
    "__version__",
]
