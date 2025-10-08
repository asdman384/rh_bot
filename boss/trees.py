import logging
import time
from math import hypot

import cv2

from boss.boss import Boss
from controller import Controller
from db import FA_BHALOR
from detect_location import find_tpl, wait_for
from frames import extract_game
from model import Direction
from sensor import FaSensor

logger = logging.getLogger(__name__)


class BossTrees(Boss):
    def __init__(self, controller: Controller, debug: bool = False) -> None:
        super().__init__(controller, debug)
        self._dist_thresh_px = 400
        self.max_moves = 1000
        self.enter_room_clicks = 6
        self.map_xy = None
        self.no_combat_minions = True

    def init_camera(self) -> None:
        self.sensor = FaSensor(
            None,
            None,
            self.fa_dir_threshold,
            debug=self.debug,
        )
        self.sensor.dir_cells = FA_BHALOR
        self.controller.attack()
        time.sleep(0.2)
        self.controller.move_NW()
        time.sleep(0.2)

    def count_enemies(self, frame830x690: cv2.typing.MatLike) -> int:
        self.controller.attack()
        time.sleep(0.2)
        return 0

    def start_fight(self, dir: Direction) -> int:
        return 0

    def open_chest(self, dir: Direction) -> bool:
        return True

    def tavern_Route(self) -> bool:
        if not wait_for("resources/mine.png", self._get_frame, 5, 0.34):
            print("mine not active")

        return True

    def is_near_exit_mask(
        self, hsv: cv2.typing.MatLike
    ) -> tuple[bool, Direction | None]:
        return False, None

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
        time.sleep(0.5)
        self.controller.back()
        time.sleep(0.1)

    def fix_disaster(self):
        self.controller.attack()
        time.sleep(0.2)

    def fix_blockage(self):
        self.controller.attack()
        time.sleep(0.2)
