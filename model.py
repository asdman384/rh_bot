from enum import Enum
from typing import Dict, List, Tuple


class Direction(Enum):
    NE = (1, -1, "NE")  #  ↗
    SE = (1, 1, "SE")  #   ↘
    SW = (-1, 1, "SW")  #  ↙
    NW = (-1, -1, "NW")  # ↖

    @property
    def dx(self) -> int:
        return self.value[0]

    @property
    def dy(self) -> int:
        return self.value[1]

    @property
    def label(self) -> str:
        return self.value[2]


ALL_DIRS: List[Direction] = [
    Direction.NE,
    Direction.SE,
    Direction.SW,
    Direction.NW,
]


OPPOSITE: Dict[Direction, Direction] = {
    Direction.NE: Direction.SW,
    Direction.SE: Direction.NW,
    Direction.SW: Direction.NE,
    Direction.NW: Direction.SE,
}

Pos = Tuple[
    int, int
]  # (x, y), ось x вправо (E), ось y вниз (S) — стандарт экранных координат
