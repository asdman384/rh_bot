import logging
import time
from math import hypot

import cv2

from boss.boss import Boss
from controller import Controller
from detect_location import find_tpl, wait_for
from frames import extract_game
from model import Direction

logger = logging.getLogger(__name__)


class BossMine(Boss):
    minimap_masks = {
        "player": {
            "l1": (150, 50, 134),
            "u1": (180, 90, 170),
            "l2": (150, 50, 134),
            "u2": (180, 90, 170),
        },
        "path": {
            "l1": (97, 109, 88),
            "u1": (123, 193, 125),
            "l2": (97, 109, 88),
            "u2": (123, 193, 125),
        },
        "wall": {
            "l1": (0, 100, 90),
            "u1": (5, 200, 125),
            "l2": (164, 93, 70),
            "u2": (180, 207, 201),
        },
    }

    def __init__(self, controller: Controller, debug: bool = False) -> None:
        super().__init__(controller, debug)
        self.use_slide = False
        self.minimap_sense = True
        self.fa_dir_threshold = {
            "ne": 40,
            "nw": 40,
            "se": 40,
            "sw": 40,
        }
        self._dist_thresh_px = 400
        self.max_moves = 1000
        self.enter_room_clicks = 5
        self.map_xy = None
        self.no_combat_minions = True
        self.exit_check_type = "tpl"  # 'mask' | 'tpl'
        self.exit_tpl_sw = cv2.imread("resources/mine/mine_sw.png")
        self.exit_tpl_sw_threshold = 0.53
        self.exit_tpl_ne = cv2.imread("resources/mine/mine_ne.png")
        self.enemy1 = cv2.imread("resources/mine/enemy1.png")
        self.enemy1_ne = cv2.imread("resources/mine/enemy1-ne.png")
        self.enemy2 = cv2.imread("resources/mine/enemy2.png")
        self.debug = True

    def count_enemies(self, frame830x690: cv2.typing.MatLike) -> int:
        px, py = 830 // 2, 690 // 2
        box, score = find_tpl(
            frame830x690, self.enemy1, [1.0], score_threshold=0.8, debug=self.debug
        )
        if box is not None:
            dist = hypot(box["cx"] - px, box["cy"] - py)
            return 1 if dist < 265 else 0

        box, score = find_tpl(
            frame830x690, self.enemy1_ne, [1.0], score_threshold=0.8, debug=self.debug
        )
        if box is not None:
            dist = hypot(box["cx"] - px, box["cy"] - py)
            return 1 if dist < 265 else 0

        box, score = find_tpl(
            frame830x690, self.enemy2, [1.0], score_threshold=0.8, debug=self.debug
        )
        if box is not None:
            dist = hypot(box["cx"] - px, box["cy"] - py)
            return 1 if dist < 265 else 0

        return 0

    def start_fight(self, dir: Direction) -> int:
        if dir is None:
            raise "dir not defined, cannot start fight"
            return 100

        logger.debug("Fighting boss Mine..." + dir.label)

        ne_route = [
            self.controller.move_N,
            self.controller.move_N,
            self.controller.move_NE,
            self.controller.move_NE,
            self.controller.move_NE,
            self.controller.move_NE,
            self.controller.move_NE,
            self.controller.move_NE,
            self.controller.move_NE,
            self.controller.move_NE,
            self.controller.move_E,
            self.controller.move_SE,
            self.controller.move_S,
            self.controller.move_SW,
            self.controller.move_SW,
            self.controller.move_SW,
            self.controller.move_SW,
            self.controller.move_SW,
            self.controller.move_SW,
            self.controller.move_SW,
        ]
        ne_route.reverse()

        sw_route = [
            self.controller.move_W,
            self.controller.move_W,
            self.controller.move_SW,
            self.controller.move_SW,
            self.controller.move_SW,
            self.controller.move_SW,
            self.controller.move_SW,
            self.controller.move_SW,
            self.controller.move_SW,
            self.controller.move_SW,
            self.controller.move_S,
            self.controller.move_SE,
            self.controller.move_E,
            self.controller.move_NE,
            self.controller.move_NE,
            self.controller.move_NE,
            self.controller.move_NE,
            self.controller.move_NE,
            self.controller.move_NE,
            self.controller.move_NE,
        ]
        sw_route.reverse()

        route = ne_route if dir == Direction.NE else sw_route
        fight_end = cv2.imread("resources/figth_end.png", cv2.IMREAD_COLOR)
        step = 0

        while len(route) > 0:
            route.pop()()
            step += 1
            if step < 12:
                time.sleep(0.1)
                continue
            if wait_for(fight_end, lambda: extract_game(self._get_frame()), 0.6):
                self.controller.wait_loading(timeout=30)
                break

        logger.debug("Finish boss Mine..." + dir.label)
        return 0

    def open_chest(self, dir: Direction) -> bool:
        self.controller.move_NE()
        time.sleep(0.1)
        self.controller.move_SW()
        return True

    def tavern_Route(self) -> None:
        if self.map_xy is None:
            print("go Inventory")
            self.controller._tap((880, 620))  # Inventory button
            time.sleep(0.5)
            frame = self._get_frame()
            cv2.imshow("frame", frame)
            cv2.setMouseCallback("frame", self._mouse_callback)
            cv2.waitKey(0)
            cv2.destroyAllWindows()

            # close inventory
            if wait_for("resources/inventory.png", self._get_frame, 1):
                self.controller.back()
                time.sleep(0.5)

        self.controller._tap((880, 620))  # Inventory button
        if not wait_for("resources/inventory.png", self._get_frame, 1):
            raise "inventory problem 1"

        self.controller._tap(self.map_xy)  # Map item
        time.sleep(0.5)

        self.controller._tap((1150, 630))  # Use button
        time.sleep(0.5)

        self.controller.wait_loading(timeout=30)

        if wait_for("resources/inventory.png", self._get_frame, 1):
            time.sleep(1)
            self.controller.back()
        else:
            raise "inventory problem 2"

        if not wait_for("resources/mine.png", self._get_frame, 5, 0.34):
            print("mine not active")

    def _mouse_callback(self, event, x, y, flags, param):
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        self.map_xy = (x, y)
        print(f"map x={x}, y={y}")

    def portal(self) -> None:
        mine = cv2.imread("resources/mine.png", cv2.IMREAD_COLOR)
        mine_box, _ = find_tpl(self._get_frame(), mine, score_threshold=0.34)

        if mine_box is None:
            raise "mine_box problem"

        self.controller.click((mine_box["x"], mine_box["y"]))
        time.sleep(0.2)

        if not wait_for("resources/hidden_mine.png", self._get_frame, 6):
            raise "mine_box click problem"

        self.controller.confirm()
        self.controller.wait_loading(1)
        if not wait_for("resources/move_mine.png", self._get_frame):
            raise "Mine enter problem"
        self.controller.wait_loading(0.5)
        self.controller.back()
        time.sleep(0.1)

    def fix_disaster(self):
        time.sleep(1)  # wait for any animation to finish
