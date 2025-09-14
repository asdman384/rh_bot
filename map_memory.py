from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Set

from model import OPPOSITE, Direction, Pos
import cv2
import numpy as np


# === Память карты =============================================================
@dataclass
class Cell:
    pos: Pos
    visited: int = 0
    # Наборы направлений от этой клетки
    open_dirs: Set[Direction] = field(default_factory=set)  # можно уйти
    wall_dirs: Set[Direction] = field(default_factory=set)  # стена/запрет


class MapMemory:
    def __init__(self) -> None:
        self.cells: Dict[Pos, Cell] = {}

    def ensure(self, p: Pos) -> Cell:
        if p not in self.cells:
            self.cells[p] = Cell(pos=p)
        return self.cells[p]

    def neighbors_open(self, p: Pos) -> List[Pos]:
        c = self.ensure(p)
        out: List[Pos] = []
        for d in c.open_dirs:
            out.append((p[0] + d.dx, p[1] + d.dy))
        return out

    def mark_edge(self, p: Pos, d: Direction, can_go: bool) -> None:
        c = self.ensure(p)
        if can_go:
            c.open_dirs.add(d)
            # Обновить/создать соседа
            q = (p[0] + d.dx, p[1] + d.dy)
            cq = self.ensure(q)
            cq.open_dirs.add(OPPOSITE[d])
        else:
            c.wall_dirs.add(d)
            c.open_dirs.discard(d)


def draw_map_memory(map_memory: MapMemory, cell_size=5) -> cv2.typing.MatLike:
    # Получить все координаты
    positions = [cell.pos for cell in map_memory.cells.values()]
    if not positions:
        return None

    xs = [p[0] for p in positions]
    ys = [p[1] for p in positions]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    w = (max_x - min_x + 1) * cell_size
    h = (max_y - min_y + 1) * cell_size
    img = np.ones((h, w, 3), dtype=np.uint8) * 255

    for cell in map_memory.cells.values():
        x, y = cell.pos
        px = (x - min_x) * cell_size
        py = (y - min_y) * cell_size

        # Нарисовать грани
        for d in cell.open_dirs:
            if d.dx == 1:  # right
                cv2.line(
                    img,
                    (px + cell_size - 1, py),
                    (px + cell_size - 1, py + cell_size - 1),
                    (0, 255, 0),
                    1,
                )
            if d.dx == -1:  # left
                cv2.line(img, (px, py), (px, py + cell_size - 1), (0, 255, 0), 1)
            if d.dy == 1:  # down
                cv2.line(
                    img,
                    (px, py + cell_size - 1),
                    (px + cell_size - 1, py + cell_size - 1),
                    (0, 255, 0),
                    1,
                )
            if d.dy == -1:  # up
                cv2.line(img, (px, py), (px + cell_size - 1, py), (0, 255, 0), 1)
        for d in cell.wall_dirs:
            if d.dx == 1:
                cv2.line(
                    img,
                    (px + cell_size - 1, py),
                    (px + cell_size - 1, py + cell_size - 1),
                    (0, 0, 255),
                    1,
                )
            if d.dx == -1:
                cv2.line(img, (px, py), (px, py + cell_size - 1), (0, 0, 255), 1)
            if d.dy == 1:
                cv2.line(
                    img,
                    (px, py + cell_size - 1),
                    (px + cell_size - 1, py + cell_size - 1),
                    (0, 0, 255),
                    1,
                )
            if d.dy == -1:
                cv2.line(img, (px, py), (px + cell_size - 1, py), (0, 0, 255), 1)

        # Нарисовать точку если посещено
        if cell.visited:
            cv2.circle(
                img, (px + cell_size // 2, py + cell_size // 2), 1, (0, 0, 0), -1
            )

        # Нарисовать квадрат (опционально, если нужно рамку)
        # cv2.rectangle(img, (px, py), (px+cell_size-1, py+cell_size-1), (128,128,128), 1)

    return img
