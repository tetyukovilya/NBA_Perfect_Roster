"""Площадка: координаты, зоны броска, ASCII-отрисовка.

Единицы — условные «футы»: длина половины площадки ~47 футов, но для
игрового макета сжимаем до 14x15, сохраняя пропорции зон (краска,
трёхочковая дуга, угловые трёхи).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ShotZone(Enum):
    RESTRICTED = "restricted"      # лэйап/данк
    PAINT = "paint"                # близкая двуха
    MIDRANGE = "midrange"          # средний
    CORNER_THREE = "corner_three"  # угловая трёха
    ARC_THREE = "arc_three"        # трёха с дуги
    BACKCOURT = "backcourt"        # за дугой (не реализуем в макете)


# Границы зон (по дистанции до кольца в условных единицах).
R_RESTRICTED = 2.5
R_PAINT = 5.0
R_MIDRANGE = 8.0
# Угловая трёха: глубоко по базовой линии и у боковой линии.
CORNER_MIN_X = 6.5
CORNER_MAX_Y = 5.6


def zone_at(x: float, y: float) -> ShotZone:
    d = (x * x + y * y) ** 0.5
    if d < R_RESTRICTED:
        return ShotZone.RESTRICTED
    if d < R_PAINT:
        return ShotZone.PAINT
    if d < R_MIDRANGE:
        return ShotZone.MIDRANGE
    if x >= CORNER_MIN_X and abs(y) >= CORNER_MAX_Y:
        return ShotZone.CORNER_THREE
    if d < 14.0:
        return ShotZone.ARC_THREE
    return ShotZone.BACKCOURT


def is_three(zone: ShotZone) -> bool:
    return zone in (ShotZone.CORNER_THREE, ShotZone.ARC_THREE)


# Штраф к точности за дальность внутри двухочковой зоны (1.0 = без штрафа).
def range_factor(zone: ShotZone) -> float:
    return {
        ShotZone.RESTRICTED: 1.00,
        ShotZone.PAINT: 0.95,
        ShotZone.MIDRANGE: 0.85,
        ShotZone.CORNER_THREE: 1.00,
        ShotZone.ARC_THREE: 0.95,
        ShotZone.BACKCOURT: 0.30,
    }[zone]


@dataclass(frozen=True, slots=True)
class Court:
    """Размеры половины площадки."""

    length: float = 14.0   # от щита до центральной линии
    width: float = 15.0    # боковая линия к боковой линии

    def clamp(self, x: float, y: float) -> tuple[float, float]:
        """Удержать точку внутри поля (мяч/игрок не уходят за линии)."""
        return (
            min(max(x, 0.0), self.length),
            min(max(y, -self.width / 2), self.width / 2),
        )

    def render(
        self,
        offense: list[tuple[str, float, float, bool]],
        defense: list[tuple[str, float, float]],
        tick: int,
    ) -> str:
        """ASCII-снимок площадки.

        offense: (имя, x, y, есть_мяч), defense: (имя, x, y).
        Сетка 15x30; колоко — '#', мяч у игрока — 'o', без мяча — 'O',
        защитники — 'x'.
        """
        rows, cols = 15, 30
        grid = [["."] * cols for _ in range(rows)]

        def cell(x: float, y: float) -> tuple[int, int]:
            r = int(round((y + self.width / 2) * (rows - 1) / self.width))
            c = int(round(x * (cols - 1) / self.length))
            return max(0, rows - 1 - r), max(0, min(cols - 1, c))

        r0, c0 = cell(0.0, 0.0)
        grid[r0][c0] = "#"  # кольцо
        for name, x, y in defense:
            r, c = cell(x, y)
            grid[r][c] = "x"
        for name, x, y, has_ball in offense:
            r, c = cell(x, y)
            grid[r][c] = "o" if has_ball else "O"

        lines = [f"--- тик {tick} " + "-" * 40]
        lines += ["".join(row) for row in grid]
        legend = "  # кольцо | o мяч | O атака | x защита"
        return "\n".join(lines) + "\n" + legend
