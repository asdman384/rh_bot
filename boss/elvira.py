import time

import cv2

from boss.boss import Boss
from controller import Controller
from db import FA_BHALOR
from detect_location import find_tpl
from model import Direction


class BossElvira(Boss):
    SW_GATE_LOW1 = (144, 209, 25)
    SW_GATE_UPP1 = (150, 220, 29)
    SW_GATE_LOW2 = (141, 220, 30)
    SW_GATE_UPP2 = (151, 230, 33)
    SW_GATE_LOW3 = (136, 244, 17)
    SW_GATE_UPP3 = (151, 255, 32)

    NE_GATE_LOW1 = (134, 173, 42)
    NE_GATE_UPP1 = (138, 221, 75)
    NE_GATE_LOW2 = (134, 173, 42)
    NE_GATE_UPP2 = (138, 221, 75)

    def __init__(self, controller: Controller, debug: bool = False) -> None:
        super().__init__(controller, debug)
        self._dist_thresh_px = 350
        self.max_moves = 150
        self.fa_dir_cells = FA_BHALOR
        self.exit_door_area_threshold = 1600
        self.enter_room_clicks = 10
        self.use_slide = False
        self.enter_room_clicks = 18
        self.fa_dir_threshold = {
            "ne": 11,
            "nw": 11,
            "se": 11,
            "sw": 11,
        }

    def init_camera(self) -> None:
        self.controller.move_E()

    def start_fight(self, dir: Direction) -> int:
        if dir == Direction.NE:
            self.controller.move_NE()
            time.sleep(0.4)

        self.controller.skill_3(
            (540, 360) if dir == Direction.SW else (640, 290)
        )  # slide
        time.sleep(2)
        hp = 100

        if dir == Direction.NE:
            hp = self._attk_focus_arrow((820, 290))  # focus arrow

            if hp != 0:
                hp = self._attk_barrage((690, 320))  # barrage
                time.sleep(0.3)

            if hp != 0:
                hp = self._attk_barrage()  # greanade

        elif dir == Direction.SW:
            hp = self._attk_focus_arrow((530, 510))  # focus arrow

            if hp != 0:
                hp = self._attk_barrage((590, 390))  # barrage
                time.sleep(0.3)

            if hp != 0:
                hp = self._attk_barrage()  # greanade

        return hp

    def open_chest(self, dir: Direction) -> bool:
        self.controller.skill_4()
        time.sleep(2.7)
        self.controller.move_S() if dir == Direction.SW else self.controller.move_E()
        time.sleep(0.5)
        return True

    def portal(self) -> None:
        self.controller._tap((1150, 450))  # select Elvira
        time.sleep(2)

    def fix_disaster(self):
        time.sleep(0.5)  # wait for any animation to finish
        exit_ban = cv2.imread("resources/elvira_exit_ban.png", cv2.IMREAD_COLOR)
        exit_ban_box, _ = find_tpl(
            self._get_frame(), exit_ban, score_threshold=0.9, debug=self.debug
        )
        if exit_ban_box is not None:
            self.controller.back()  # close banner
            time.sleep(0.2)
            self.controller.move_SE()
            time.sleep(0.15)
            return

        time.sleep(1.5)  # wait for any animation to finish
