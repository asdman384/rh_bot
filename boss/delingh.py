import time

import cv2

from boss.boss import Boss
from controller import Controller
from db import FA_BHALOR
from model import Direction


class BossDelingh(Boss):
    def __init__(self, controller: Controller, debug: bool = False) -> None:
        super().__init__(controller, debug)
        self.max_moves = 150
        self.fa_dir_cells = FA_BHALOR
        self.enter_room_clicks = 10
        self.use_slide = True
        self.fa_dir_threshold = {
            "ne": 30,
            "nw": 30,
            "se": 30,
            "sw": 30,
        }
        self.exit_check_type = "tpl"  # 'mask' | 'tpl'
        self.exit_tpl_sw = cv2.imread("resources/delingh/exit_sw.png")
        self.exit_tpl_ne = cv2.imread("resources/delingh/exit_ne.png")

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
        self.controller.move_SW() if dir == Direction.SW else self.controller.move_NE()
        time.sleep(0.2)
        self.controller.skill_4()
        time.sleep(2.7)
        self.controller.move_S() if dir == Direction.SW else self.controller.move_E()
        time.sleep(0.5)
        return True

    def portal(self) -> None:
        self.controller._tap((1150, 540))  # select Delingh
        time.sleep(2)

    def fix_disaster(self):
        time.sleep(0.5)  # wait for any animation to finish
        time.sleep(1.5)  # wait for any animation to finish
