import logging
import time


import cv2

from boss.boss import Boss
from controller import Controller
from detect_location import find_tpl
from model import Direction
from sensor import MinimapSensor

logger = logging.getLogger(__name__)


class BossVolcano(Boss):
    def __init__(self, controller: Controller, debug: bool = False) -> None:
        super().__init__(controller, debug)

        self.max_moves = 170
        self.enter_room_clicks = 10
        self.no_combat_minions = True
        self.exit_check_type = "tpl"  # 'mask' | 'tpl'
        self.exit_tpl_sw_threshold = 0.57
        self.exit_tpl_sw = cv2.imread("resources/dain/sw.png")
        self.exit_tpl_ne = cv2.imread("resources/dain/ne.png")
        self.ensure_movement = False

        self.minimap_masks = {
            "player": {
                "bgr": (132, 113, 156),  # B,G,R
                "l1": (165, 35, 150),
                "u1": (175, 85, 180),
                "l2": (165, 75, 165),
                "u2": (175, 100, 200),
            },
            "path": {
                "l1": (85, 60, 40),
                "u1": (140, 255, 255),
                "l2": (86, 60, 80),
                "u2": (130, 125, 120),
            },
            "wall": {
                "l1": (0, 0, 0),
                "u1": (0, 0, 0),
                "l2": (0, 0, 0),
                "u2": (0, 0, 0),
            },
        }

    def init_camera(self) -> None:
        self.sensor = MinimapSensor(
            None,
            self.minimap_masks,
            {"ne": 50, "nw": 50, "se": 35, "sw": 30},
            debug=self.debug or True,
        )
        self.ensure_movement = True
        self.controller.move_E()
        time.sleep(0.2)
        self.controller.move_SE()

    def count_enemies(self, frame830x690: cv2.typing.MatLike) -> int:
        return 0

    def start_fight(self, dir: Direction) -> int:
        logger.debug(f"Fighting boss Volcano... dir: {dir}")
        self.controller.skill_3(
            (730, 360) if dir == Direction.SW else (640, 430)
        )  # Somersault
        time.sleep(3)
        self.controller.skill_3()  # elven blessing
        time.sleep(1.5)

        routine = [
            self._attk_focus_arrow,  # piercing arrow
            lambda: self._attk_focus_arrow((800, 470)),  # focus arrow
            lambda: self._attk_barrage((800, 470)),  # barrage
            lambda: time.sleep(1.5),
            lambda: self._attk_barrage((800, 470)),  # barrage
            lambda: time.sleep(3),
            self.controller.skill_3,  # elven blessing
            lambda: time.sleep(5),
            lambda: self.controller.skill_3(
                (690, 330) if dir == Direction.SW else (590, 393)
            ),  # Somersault
            lambda: time.sleep(3),
            self.controller.move_SE,
            lambda: time.sleep(2),
            self._attk_focus_arrow,  # piercing arrow
            lambda: time.sleep(2),
            self._attk_focus_arrow,  # focus arrow
            lambda: time.sleep(4),
            self.controller.skill_4,  # slide
            lambda: time.sleep(2),
            self.controller.attack,  # attack
            lambda: time.sleep(1.5),
            self._attk_barrage,  # grenade
            self._attk_barrage,  # barrage
            self._attk_focus_arrow,  # piercing arrow
            lambda: self._attk_focus_arrow(
                (540, 430) if dir == Direction.SW else (770, 260)
            ),  # focus arrow
        ]

        hp = 100
        while hp > 0 and len(routine) > 0:
            method = routine.pop()
            result = method()
            hp = hp if result is None else result
            logger.debug(
                f"steps left: {len(routine)} hp: {hp}% after: {method.__name__}"
            )

        logger.debug(f"Finished boss Volcano... hp: {hp}%")
        return hp

    def open_chest(self, dir: Direction) -> bool:
        boss_chest = cv2.imread("resources/boss_chest.png", cv2.IMREAD_COLOR)
        # start_time = time.time()
        # box = None
        # while box is None and time.time() - start_time < 10:
        #     box, _ = find_tpl(self._get_frame(), boss_chest, score_threshold=0.69)

        # if box is None:
        #     raise Exception("Chest not found")

        # self.controller.attack((box["cx"], box["cy"]))
        self.controller.move_SE()
        time.sleep(0.3)
        self.controller.move_NW()
        time.sleep(0.2)
        self.controller.attack((650, 290) if dir == Direction.SW else (610, 330))
        self.controller.attack((650, 290) if dir == Direction.SW else (610, 330))

        time.sleep(2.3)
        self.controller.move_SE()
        time.sleep(0.2)
        self.controller.move_NW()
        time.sleep(0.2)
        self.controller.move_SE()
        time.sleep(0.2)

        box, _ = find_tpl(self._get_frame(), boss_chest, score_threshold=0.72)
        if box is not None:
            raise Exception("Chest still present")
        cv2.imwrite(
            f"images/dbg_volcano_chest{time.strftime('%H-%M-%S')}.png", self._get_frame()
        )
        return True

    def portal(self) -> None:
        self.controller._tap((1000, 630))  # page +1
        time.sleep(0.4)
        self.controller._tap((1150, 550))  # select Volcano

        time.sleep(2.5)
