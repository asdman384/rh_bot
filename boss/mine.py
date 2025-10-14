import logging
import time
from math import hypot

import cv2

from boss.boss import Boss
from controller import Controller
from detect_location import find_tpl, wait_for
from frames import extract_game
from model import Direction
from sensor import MinimapSensor

logger = logging.getLogger(__name__)
mine = cv2.imread("resources/mine.png", cv2.IMREAD_COLOR)


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
        self._dist_thresh_px = 400
        self.max_moves = 1000
        self.enter_room_clicks = 6
        self.map_xy = None
        self.no_combat_minions = True
        self.exit_check_type = "tpl"  # 'mask' | 'tpl'
        self.exit_tpl_sw = cv2.imread("resources/mine/mine_sw.png")
        self.exit_tpl_sw_threshold = 0.53
        self.exit_tpl_ne = cv2.imread("resources/mine/mine_ne.png")
        self.enemy1 = cv2.imread("resources/mine/enemy1.png")
        self.enemy1_ne = cv2.imread("resources/mine/enemy1-ne.png")
        self.enemy2 = cv2.imread("resources/mine/enemy2.png")

    def init_camera(self) -> None:
        self.sensor = MinimapSensor(
            None,
            self.minimap_masks,
            {"ne": 35, "nw": 35, "se": 35, "sw": 35},
            debug=self.debug,
        )
        self.controller.move_E()

    def count_enemies(self, frame830x690: cv2.typing.MatLike) -> int:
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
                time.sleep(0.07)
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

    def tavern_Route(self) -> bool:
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

        if not wait_for(mine, self._get_frame, 5, 0.30):
            print("mine not active")

        return True

    def _mouse_callback(self, event, x, y, flags, param):
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        self.map_xy = (x, y)
        print(f"map x={x}, y={y}")

    def portal(self) -> None:
        mine_box, _ = find_tpl(self._get_frame(), mine, score_threshold=0.30)

        if mine_box is None:
            raise "mine_box problem"

        self.controller.click((mine_box["x"], mine_box["y"]))
        time.sleep(0.2)

        if not wait_for("resources/hidden_mine.png", self._get_frame, 6):
            raise "mine_box click problem"

        self.controller.confirm()
        self.controller.wait_loading(2, 10)
        if not wait_for("resources/move_mine.png", self._get_frame):
            raise "Mine enter problem"
        self.controller.wait_loading(1)
        self.controller.back()
        time.sleep(0.1)

    def fix_disaster(self):
        time.sleep(1)  # wait for any animation to finish

    def fix_blockage(self):
        time.sleep(0.2)
        self.controller.attack()
        self.controller.attack()
        time.sleep(1)
