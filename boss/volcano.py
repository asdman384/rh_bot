import logging
import time


import cv2

from boss.boss import Boss, extract_boss_health, measure_fill_px
from bot_utils.screenshoter import save_image
from controller import Controller
from detect_location import wait_for
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
        raise 'NotImplementedError()'
        logger.debug(f"Fighting boss Dain... dir: {dir}")
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
            phase_change = prev_hp > 50 and hp <= 50.5
            logger.debug(f"steps left: {len(routine)} phase_change: {phase_change}")
            time.sleep(1.4) if phase_change else None
            if len(routine) == 1:
                time.sleep(
                    4.0 if dir == Direction.NE else 2.0
                )  # wait long animation before 4 move
            prev_hp = hp
            hp = routine.pop()()

        if 5 < hp < 13 and dir == Direction.SW:
            save_image(
                self._get_frame(),
                f"fails/dain/multi_shot_{time.strftime('%H-%M-%S')}.png",
            )
            logger.info(f"Finishing with multi shot... {hp}% left")
            time.sleep(1)
            hp = self.controller.skill_4()
            time.sleep(1)
            hp = measure_fill_px(extract_boss_health(self._get_frame()), self.debug)
            logger.info(f"Finished with multi shot... {hp}% left")

        if 0 < hp <= 4:
            logger.info(f"Finishing with basic attack... {hp}% left")
            time.sleep(1)
            self.controller.attack()
            time.sleep(1)
            hp = measure_fill_px(extract_boss_health(self._get_frame()), self.debug)
            logger.info(f"Finished with basic attack... {hp}% left")

        logger.debug("Finished boss Dain...")
        return hp

    def open_chest(self, dir: Direction) -> bool:
        if dir == Direction.NE:
            self.controller.move_NE()
            time.sleep(0.2)

        self.controller.skill_4((590, 390) if dir == Direction.SW else None)
        t0 = time.time()
        time.sleep(1.6)
        chest = f"resources/dain/{Direction.SW.label.lower()}_chest.png"
        if wait_for(chest, self._get_frame, 1, 0.68, self.debug):
            logger.info("wait_for chest again?")
            self.controller.attack()
            time.sleep(3)

        if wait_for(chest, self._get_frame, 0.1, 0.68, self.debug):
            logger.info("wait_for chest again? False")
            return False

        logger.debug(f"Chest opened in {time.time() - t0:.1f}s")
        self.controller.move_S() if dir == Direction.SW else self.controller.move_E()
        time.sleep(0.1)
        self.controller.move_SW() if dir == Direction.SW else self.controller.move_NE()
        time.sleep(0.5)
        return True

    def portal(self) -> None:
        self.controller._tap((1000, 630))  # page +1
        time.sleep(0.4)
        self.controller._tap((1150, 550))  # select Volcano

        time.sleep(2.5)
