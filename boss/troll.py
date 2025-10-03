import time

import cv2

from boss.boss import Boss
from controller import Controller
from db import FA_BHALOR
from model import Direction
from sensor import FaSensor


class BossTroll(Boss):
    def __init__(self, controller: Controller, debug: bool = False) -> None:
        super().__init__(controller, debug)
        self._dist_thresh_px = 350
        self.max_moves = 150
        self.exit_door_area_threshold = 1600
        self.enter_room_clicks = 10
        self.enter_room_clicks = 18
        self.ensure_movement = False
        self.exit_check_type = "tpl"  # 'mask' | 'tpl'
        self.exit_tpl_sw_threshold = 0.75
        self.exit_tpl_ne_threshold = 0.8
        self.exit_tpl_sw = cv2.imread("resources/troll/sw.png")
        self.exit_tpl_ne = cv2.imread("resources/troll/ne.png")

    def init_camera(self) -> None:
        self.sensor = FaSensor(
            None,
            None,
            {"ne": 15, "nw": 15, "se": 15, "sw": 15},
            debug=self.debug,
        )
        self.sensor.dir_cells = FA_BHALOR
        self.controller.move_E()

    def start_fight(self, dir: Direction) -> int:
        self.controller.skill_3(
            (540, 360) if dir == Direction.SW else (640, 290)
        )  # slide
        time.sleep(2)
        hp = 100

        if dir == Direction.NE:
            hp = self._attk_focus_arrow((920, 290))  # focus arrow

            if hp != 0:
                hp = self._attk_barrage((920, 290))  # barrage

        elif dir == Direction.SW:
            hp = self._attk_focus_arrow((640, 530))  # focus arrow

            if hp != 0:
                hp = self._attk_focus_arrow()  # piercing arrow

        return hp

    def open_chest(self, dir: Direction) -> bool:
        if dir == Direction.NE:
            self.controller.move_NE()
            time.sleep(0.5)

        self.controller.skill_4((590, 390) if dir == Direction.SW else None)

        time.sleep(2.7)
        self.controller.move_S() if dir == Direction.SW else self.controller.move_E()
        time.sleep(0.5)
        return True

    def portal(self) -> None:
        self.controller._tap((1150, 170))  # select Troll
        time.sleep(2)

    def fix_disaster(self):
        pass
