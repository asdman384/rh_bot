import time

import cv2

from boss.boss import Boss
from controller import Controller
from db import FA_KHANEL
from detect_location import wait_for
from model import Direction


class BossDain(Boss):
    def __init__(self, controller: Controller, debug: bool = False) -> None:
        super().__init__(controller, debug)
        self._dist_thresh_px = 350
        self.max_moves = 100
        self.fa_dir_cells = FA_KHANEL
        self.exit_door_area_threshold = 300
        self.enter_room_clicks = 10
        self.no_combat_minions = True
        self.exit_check_type = "tpl"  # 'mask' | 'tpl'
        self.exit_tpl_sw = cv2.imread("resources/dain/sw.png")
        self.exit_tpl_ne = cv2.imread("resources/dain/ne.png")

    def start_fight(self, dir: Direction) -> int:
        print("Fighting boss Dain...") if self.debug else None
        self.controller.skill_3(
            (540, 360) if dir == Direction.SW else (640, 290)
        )  # slide
        time.sleep(2)
        self.controller.skill_3()  # elven blessing
        time.sleep(1.5)

        ne_routine = [
            self._attk_focus_arrow,  # piercing arrow
            self._attk_focus_arrow,  # focus arrow
            lambda: self._attk_barrage((730, 300)),  # grenade
            lambda: self._attk_barrage((690, 320)),  # barrage
        ]

        sw_routine = [
            lambda: self._attk_barrage((530, 430)),  # grenade
            self._attk_barrage,  # barrage
            self._attk_focus_arrow,  # piercing arrow
            lambda: self._attk_focus_arrow((480, 470)),  # focus arrow
        ]

        routine = ne_routine if dir == Direction.NE else sw_routine
        hp, prev_hp = 100, 100
        while hp > 0 and len(routine) > 0:
            phase_change = prev_hp > 50 and hp < 50
            print(
                f"steps left: {len(routine)} phase_change: {phase_change}"
            ) if self.debug else None
            time.sleep(1.5) if phase_change or len(routine) == 1 else None
            prev_hp = hp
            hp = routine.pop()()

        print("Finished boss Dain...") if self.debug else None
        return hp

    def open_chest(self, dir: Direction) -> bool:
        self.controller.move_SW() if dir == Direction.SW else self.controller.move_NE()
        time.sleep(0.5)
        self.controller.skill_4()
        time.sleep(2)
        chest = f"resources/dain/{Direction.SW.label.lower()}_chest.png"
        if wait_for(chest, self._get_frame, 1, 0.68, self.debug):
            print("wait_for chest again?")
            self.controller.attack()
            time.sleep(3)

        if wait_for(chest, self._get_frame, 0.1, 0.68, self.debug):
            print("wait_for chest again? False")
            return False

        self.controller.move_S() if dir == Direction.SW else self.controller.move_E()
        time.sleep(0.5)
        return True

    def portal(self) -> None:
        self.controller._tap((1000, 630))  # page +1
        time.sleep(0.4)
        self.controller._tap((1150, 450))  # select Dain
        time.sleep(2.5)
