import time

from boss.boss import Boss, extract_boss_health, measure_fill_px
from controller import Controller
from db import FA_KHANEL
from model import Direction


class BossKhanel(Boss):
    SW_GATE_LOW1 = (100, 255, 24)
    SW_GATE_UPP1 = (102, 255, 33)
    SW_GATE_LOW2 = (105, 205, 41)
    SW_GATE_UPP2 = (109, 205, 41)
    SW_GATE_LOW3 = (110, 155, 33)
    SW_GATE_UPP3 = (115, 193, 41)

    NE_GATE_LOW1 = (98, 255, 33)
    NE_GATE_UPP1 = (102, 255, 41)
    NE_GATE_LOW2 = (105, 213, 49)
    NE_GATE_UPP2 = (108, 224, 66)

    def __init__(self, controller: Controller, debug: bool = False) -> None:
        super().__init__(controller, debug)
        self._dist_thresh_px = 350
        self.max_moves = 100
        self.fa_dir_cells = FA_KHANEL
        self.exit_door_area_threshold = 5900
        self.ensure_movement = False

    def start_fight(self, dir: Direction) -> int:
        if dir is None:
            return 100

        print("Fighting boss Khanel..." + dir.label) if self.debug else None
        self.controller.skill_3(
            (590, 390) if dir == Direction.SW else (690, 320)
        )  # slide
        time.sleep(2)
        self.controller.skill_3()  # elven blessing
        time.sleep(1.4)

        if dir == Direction.NE:
            hp = self._attk_barrage((690, 320))  # barrage

            if hp != 0:
                hp = self._attk_focus_arrow((640, 230))  # focus arrow

            if hp != 0:
                hp = self._attk_focus_arrow()  # piercing arrow

        elif dir == Direction.SW:
            hp = self._attk_barrage((590, 390))  # barrage

            if hp != 0:
                hp = self._attk_focus_arrow((450, 350))  # focus arrow

            if hp != 0:
                hp = self._attk_focus_arrow()  # piercing arrow

        while hp != 0:
            self.controller.attack()
            hp = measure_fill_px(extract_boss_health(self._get_frame()), self.debug)

        return hp

    def portal(self) -> None:
        self.controller._tap((1000, 630))  # page +1
        time.sleep(0.4)
        self.controller._tap((1150, 170))  # select Khanhel
        time.sleep(2.5)
