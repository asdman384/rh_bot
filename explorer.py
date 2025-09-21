import logging
import time
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple

from boss import BossDain, BossBhalor
from map_memory import MapMemory
from maze_rh import MazeRH
from model import ALL_DIRS, Direction, Pos


logger = logging.getLogger(__name__)


def direction_priority(base: Optional[Direction]) -> List[Direction]:
    """
    Возвращает упорядоченный список направлений (8 шт.) с предпочтением
    продолжать прежнее направление, затем слабые повороты.
    """
    if base is None:
        return [Direction.NW, Direction.SE]

    order = {
        #         ↙              ↙            ↖             ↘             ↗
        Direction.SW: [Direction.SW, Direction.NW, Direction.SE, Direction.NE],
        #         ↗              ↗             ↘            ↖             ↙
        Direction.NE: [Direction.NE, Direction.SE, Direction.NW, Direction.SW],
        #         ↖              ↖             ↗            ↙             ↘
        Direction.NW: [Direction.NW, Direction.NE, Direction.SW, Direction.SE],
        #         ↘              ↘             ↙            ↗             ↖
        Direction.SE: [Direction.SE, Direction.SW, Direction.NE, Direction.NW],
    }
    return order[base][:]


def bfs_shortest_path(graph: MapMemory, start: Pos, goal: Pos) -> Optional[List[Pos]]:
    """Кратчайший путь в известном графе между start и goal (включая оба)."""
    if start == goal:
        return [start]
    q: Deque[Pos] = deque([start])
    prev: Dict[Pos, Optional[Pos]] = {start: None}
    while q:
        v = q.popleft()
        for u in graph.neighbors_open(v):
            if u not in prev:
                prev[u] = v
                if u == goal:
                    # восстановить путь
                    path: List[Pos] = [u]
                    while v is not None:
                        path.append(v)
                        v = prev[v]
                    path.reverse()
                    return path
                q.append(u)
    return None


# === Онлайн-исследователь =====================================================
class Explorer:
    """
    Онлайн-агент, исследующий лабиринт, который раскрывается по мере движения.
    """

    def __init__(self, maze: MazeRH, start: Pos = (0, 0)) -> None:
        self.maze = maze
        self._init(start)

    def _init(self, start: Pos = (0, 0)) -> None:
        self.pos: Pos = start
        self.prev_dir: Optional[Direction] = None
        self.map = MapMemory()
        self.map.ensure(start)

    # --- Основной цикл ---
    def run(
        self, max_steps: int = 50000, restart=True, verbose: bool = False
    ) -> Tuple[bool, int, Optional[Direction]]:
        """
        Выполняет пошаговый поиск выхода.
        Возвращает (reason, число_шагов).
        """
        if restart:
            self._init()
            self.maze.init_camera()

        steps = 0
        # Первичная сенсорика
        self.sense_here()
        last_dir: Direction | None = None

        while steps < max_steps:
            # Отметить посещение текущей клетки
            self.map.ensure(self.pos).visited += 1

            # Проверка выхода
            exit = self.maze.is_exit()
            if exit[0]:
                print(
                    f"[OK] Exit reached at {self.pos} in {steps} steps."
                ) if verbose else None

                # TODO: return for all bosses
                if (
                    type(self.maze.boss) is BossBhalor
                    or type(self.maze.boss) is BossDain
                ):
                    return "success", steps, exit[1]
                # TODO: remove
                # dir can be either SW or NE
                if last_dir == Direction.NW:
                    last_dir = Direction.SW
                elif last_dir == Direction.SE:
                    last_dir = Direction.NE
                return "success", steps, last_dir

            # Выбрать локальный ход (в ещё не посещённого соседа)
            last_dir = d = self._pick_local_step()

            # Если локальных кандидатов нет — пойдём к ближайшей известной непосещённой клетке
            if d is None:
                target = self._nearest_unvisited_open()
                if target is None:
                    logger.debug("[END] Full explored region exhausted.")
                    return (
                        "[END] Full explored region exhausted.",
                        steps,
                        None,
                    )
                if target != self.pos:
                    # Проложить путь к target (BFS) и сделать ПЕРВЫЙ шаг по нему
                    path = bfs_shortest_path(self.map, self.pos, target)
                    if not path or len(path) < 2:
                        # Не нашли путь в известном графе — такое возможно, если граф несвязен без обратимости
                        # Попробуем локально "расшить" с помощью любого доступного открытого соседа
                        d = self._fallback_any_open_dir()
                        if d is None:
                            logger.debug(
                                "[END] Stuck: no path to target and no local open edges."
                            )
                            return (
                                "[END] Stuck: no path to target and no local open edges.",
                                steps,
                                None,
                            )
                    else:
                        next_pos = path[1]
                        d = self._dir_to(self.pos, next_pos)

            if d is None:
                logger.debug("[END] No move decided.")
                return "[END] No move decided.", steps, None

            if self._move(d):
                steps += 1
                self.prev_dir = d
                self.sense_here()
            else:
                # Не удалось сделать ход (ложное срабатывание can_move)
                # Предыдущая позиция не меняется, prev_dir не меняется
                self.map.mark_edge(self.pos, d, False)
                logger.debug(
                    f"[WARN] Move {d.label} from {self.pos} failed unexpectedly."
                )

            # img = draw_map_memory(self.map)
            # cv2.imshow("map", img)
            # cv2.waitKey(1)

        logger.debug(f"[END] Step limit {max_steps} reached.")
        return "[END] Step limit {max_steps} reached.", steps, None

    # --- Взаимодействие с API ---

    def _can(self, d: Direction) -> bool:
        return self.maze.can_move(d)

    def _move(self, d: Direction) -> bool:
        isMoved, hasSlid = self.maze.move(d)
        multiplier = 2 if hasSlid else 1
        if isMoved:
            self.pos = (
                self.pos[0] + d.dx * multiplier,
                self.pos[1] + d.dy * multiplier,
            )
        return isMoved

    # --- Сенсорика и обновление памяти ---

    def sense_here(self) -> None:
        """
        Запрашивает can_move_* во всех 8 направлениях из текущей клетки
        и обновляет локальную карту.
        """
        for d in ALL_DIRS:
            can = self._can(d)
            self.map.mark_edge(self.pos, d, can)

    # --- Выбор следующей цели/шага ---

    def _pick_local_step(self) -> Optional[Direction]:
        """
        Локальный ход: если рядом есть не посещённый сосед — выбрать его согласно приоритету.
        """
        cell = self.map.ensure(self.pos)
        prio = direction_priority(self.prev_dir)
        best: Optional[Direction] = None
        for d in prio:
            if d in cell.open_dirs:
                nxt = (self.pos[0] + d.dx, self.pos[1] + d.dy)
                if self.map.ensure(nxt).visited == 0:
                    best = d
                    break
        return best

    def _nearest_unvisited_open(self) -> Optional[Pos]:
        """
        Находит ближайшую (по рёбрам известного графа) клетку, которая уже известна как
        проходимая, но ещё не посещена.
        """
        # Быстрый случай: текущая ещё не отмечена посещённой (перед sense/visit)
        if self.map.ensure(self.pos).visited == 0:
            return self.pos

        targets = [
            p for p, c in self.map.cells.items() if c.visited == 0 and c.open_dirs
        ]
        if not targets:
            return None

        # BFS по известному графу до любого из targets
        q: Deque[Pos] = deque([self.pos])
        dist: Dict[Pos, int] = {self.pos: 0}
        parent: Dict[Pos, Optional[Pos]] = {self.pos: None}
        while q:
            v = q.popleft()
            if (
                v != self.pos
                and self.map.ensure(v).visited == 0
                and self.map.ensure(v).open_dirs
            ):
                # ближайшая непосещённая
                return v
            for u in self.map.neighbors_open(v):
                if u not in dist:
                    dist[u] = dist[v] + 1
                    parent[u] = v
                    q.append(u)
        return None

    def _fallback_any_open_dir(self) -> Optional[Direction]:
        """Запасной вариант: выбрать любой открытый выход из текущей клетки (по приоритету направления)."""
        prio = direction_priority(self.prev_dir)
        cell = self.map.ensure(self.pos)
        for d in prio:
            if d in cell.open_dirs:
                return d
        return None

    @staticmethod
    def _dir_to(a: Pos, b: Pos) -> Optional[Direction]:
        dx = b[0] - a[0]
        dy = b[1] - a[1]
        for d in ALL_DIRS:
            if d.dx == dx and d.dy == dy:
                return d
        return None


if __name__ == "__main__":
    from boss.boss import BossDain, BossMine
    from controller import Controller
    from devices.device import Device

    device = Device("127.0.0.1", 58526)
    device.connect()
    controller = Controller(device)
    boss = BossMine(controller, False)
    maze = MazeRH(controller, boss, True)
    explorer = Explorer(maze, True)

    t0 = time.time()
    isSucces, moves, dir = explorer.run(boss.max_moves, True)
    print(
        f"Run Explorer finished with: {isSucces}, moves taken: {moves}, time: {time.time() - t0:.1f}s, dir: {dir.label if dir is not None else None}"
    )
