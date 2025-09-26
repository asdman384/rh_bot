import time

import cv2

from boss.boss import Boss
from controller import Controller
from model import Direction
from sensor import MinimapSensor


class BossDelingh(Boss):
    def __init__(self, controller: Controller, debug: bool = False) -> None:
        super().__init__(controller, debug)
        self.max_moves = 200
        self.use_slide = False

        self.enter_room_clicks = 10
        self.ensure_movement = True

        self.exit_check_type = "tpl"  # 'mask' | 'tpl'
        self.exit_tpl_sw = cv2.imread("resources/delingh/exit_sw.png")
        self.exit_tpl_ne = cv2.imread("resources/delingh/exit_ne.png")
        self.exit_tpl_ne_threshold = 0.62

        self.minimap_masks = {
            "player": {
                "l1": (161, 50, 134),
                "u1": (180, 112, 170),
                "l2": (161, 50, 134),
                "u2": (180, 112, 170),
            },
            "path": {
                "l1": (105, 126, 85),
                "u1": (111, 172, 134),
                "l2": (105, 126, 85),
                "u2": (111, 172, 134),
            },
            "wall": {
                "l1": (105, 126, 85),
                "u1": (111, 172, 134),
                "l2": (105, 126, 85),
                "u2": (111, 172, 134),
            },
        }

    def init_camera(self) -> None:
        self.sensor = MinimapSensor(
            None,
            self.minimap_masks,
            {"ne": 50, "nw": 50, "se": 45, "sw": 45},
            debug=self.debug,
        )
        self.controller.move_SE()
        self.controller.move_NW()

    def start_fight(self, dir: Direction) -> int:
        print("Fighting boss Delingh...") if self.debug else None
        self.controller.skill_3(
            (540, 360) if dir == Direction.SW else (640, 290)
        )  # slide
        time.sleep(2)

        ne_routine = [self._attk_barrage, lambda: self._attk_focus_arrow((860, 260))]
        sw_routine = [self._attk_barrage, lambda: self._attk_focus_arrow((530, 510))]
        routine = ne_routine if dir == Direction.NE else sw_routine
        hp = 100
        while hp > 0 and len(routine) > 0:
            hp = routine.pop()()

        print("Finished boss Delingh...") if self.debug else None
        return hp

    def open_chest(self, dir: Direction) -> bool:
        None if dir == Direction.SW else self.controller.move_NE()
        time.sleep(0.2) if dir == Direction.NE else None
        self.controller.skill_4()
        time.sleep(2.7)
        self.controller.move_S() if dir == Direction.SW else self.controller.move_E()
        time.sleep(0.5)
        return True

    def portal(self) -> None:
        self.controller._tap((1150, 540))  # select Delingh
        time.sleep(2)

    def fix_disaster(self):
        self.controller.move_SE()
        time.sleep(0.2)
