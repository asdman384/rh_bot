import time

import cv2

from boss.boss import Boss
from controller import Controller
from db import FA_BHALOR
from detect_location import find_tpl
from model import Direction
from sensor import FaSensor, MinimapSensor


class BossElvira(Boss):
    def __init__(self, controller: Controller, debug: bool = False) -> None:
        super().__init__(controller, debug)
        self._dist_thresh_px = 350
        self.max_moves = 150
        self.exit_door_area_threshold = 1600
        self.enter_room_clicks = 10
        self.enter_room_clicks = 18

        self.exit_check_type = "tpl"  # 'mask' | 'tpl'
        self.exit_tpl_sw_threshold = 0.70
        self.exit_tpl_ne_threshold = 0.78
        self.exit_tpl_sw = cv2.imread("resources/elvira/sw.png")
        self.exit_tpl_ne = cv2.imread("resources/elvira/ne.png")

    def init_camera(self) -> None:
        # self.sensor = MinimapSensor(
        #     None,
        #     self.minimap_masks,
        #     {"ne": 50, "nw": 50, "se": 35, "sw": 30},
        #     debug=self.debug or True,
        # )
        # self.ensure_movement = True
        # self.controller.move_E()
        # return
        self.sensor = FaSensor(
            None,
            None,
            {"ne": 20, "nw": 20, "se": 20, "sw": 20},
            debug=self.debug,
        )
        self.sensor.dir_cells = FA_BHALOR
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
        time.sleep(0.7)  # wait for any animation to finish
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
