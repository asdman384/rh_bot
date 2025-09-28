import logging
from math import hypot
import time

import cv2
from boss.dain import BossDain
from controller import Controller
from detect_location import find_tpl
from model import Direction

logger = logging.getLogger(__name__)


class BossKrokust(BossDain):
    def __init__(self, controller: Controller, debug: bool = False) -> None:
        super().__init__(controller, debug)
        self.fa_dir_threshold = {
            "ne": 18,
            "nw": 18,
            "se": 18,
            "sw": 18,
        }
        self.exit_tpl_sw_threshold = 0.83
        self.exit_tpl_ne_threshold = 0.83
        self.exit_tpl_sw = cv2.imread("resources/krokust/sw.png")
        self.exit_tpl_ne = cv2.imread("resources/krokust/ne.png")
        self.sw_combat_pos = cv2.imread("resources/krokust/sw_combat_pos.png")
        self.ne_combat_pos = cv2.imread("resources/krokust/ne_combat_pos.png")
        self.enemy1 = cv2.imread("resources/krokust/se_chest.png")
        self.enemy2 = cv2.imread("resources/krokust/sw_chest.png")
        self.controller._delay = 0.166

    def portal(self) -> None:
        self.controller._tap((1000, 630))  # page +1
        time.sleep(0.2)
        self.controller._tap((1000, 630))  # page +1
        time.sleep(0.2)
        self.controller._tap((1150, 550))  # select Krokust
        time.sleep(2.5)

    def start_fight(self, dir: Direction) -> int:
        logger.debug("Fighting boss Krokust...")

        ne_routine = [
            self._attk_focus_arrow,  # piercing arrow Krokust
            lambda: self._attk_focus_arrow(
                self._find_combat_pos(dir)
            ),  # focus arrow Krokust
            lambda: time.sleep(1.5),  # wait lag
            lambda: self._attk_barrage((750, 510)),  # grenade
            lambda: time.sleep(1),  # wait lag
            lambda: self._attk_barrage((750, 510)),  # barrage
            lambda: time.sleep(1.5),  # wait for Krokust buff animation
            lambda: time.sleep(1.5),  # wait for battle focus buff animation
            self.controller.skill_3,  # battle focus
            lambda: time.sleep(4.2),  # wait for strafe and krokust spinning animation
            lambda: self.controller.skill_3((640, 430)),  # strafe
            lambda: self._attk_focus_arrow((730, 300)),  # piercing arrow Krokust
            lambda: time.sleep(1.5),  # wait for jump animation
            lambda: self._attk_focus_arrow((490, 400)),  # focus arrow door
            lambda: time.sleep(0.5),  # wait move
            self.controller.move_NE,
        ]

        sw_routine = [
            self._attk_focus_arrow,  # piercing arrow Krokust
            lambda: self._attk_focus_arrow(
                self._find_combat_pos(dir)
            ),  # focus arrow Krokust
            lambda: time.sleep(1.5),  # wait lag
            lambda: self._attk_barrage((840, 430)),  # grenade
            lambda: time.sleep(1),  # wait lag
            lambda: self._attk_barrage((740, 430)),  # barrage
            lambda: time.sleep(1.5),  # wait for Krokust buff animation
            lambda: time.sleep(1.5),  # wait for battle focus buff animation
            self.controller.skill_3,  # battle focus
            lambda: time.sleep(4.2),  # wait for strafe and krokust spinning animation
            lambda: self.controller.skill_3((740, 360)),  # strafe
            lambda: self._attk_focus_arrow((535, 430)),  # piercing arrow Krokust
            lambda: time.sleep(1.5),  # wait for jump animation
            lambda: self._attk_focus_arrow((250, 360)),  # destroy crate
            lambda: time.sleep(1.5),  # wait for possible buff animation
            self.controller.attack,  # skip 1 turn
        ]

        routine = ne_routine if dir == Direction.NE else sw_routine
        hp = 100
        while hp > 0 and len(routine) > 0:
            result = routine.pop()()
            hp = hp if result is None else result
            logger.debug(f"steps left: {len(routine)}, hp left: {hp}")

        logger.debug(f"Finished boss Krokust... {hp}")
        return hp

    def _find_combat_pos(self, dir: Direction) -> tuple[int, int]:
        logger.debug("Finding Krokust position...")
        box = None
        # TODO: add timeout
        while box is None:
            box, _ = find_tpl(
                self._get_frame(),
                self.sw_combat_pos if dir == Direction.SW else self.ne_combat_pos,
                score_threshold=0.8,
                debug=self.debug,
            )

        if box is None:
            if dir == Direction.SW:
                return 840, 430
            else:
                return 750, 510
        logger.debug("found krokust:", box["cx"], box["cy"])
        return box["cx"], box["cy"]

    def open_chest(self, dir: Direction) -> bool:
        if dir == Direction.SW:
            self.controller.move_SW()
            time.sleep(0.2)
        return super().open_chest(dir)

    def count_enemies(self, frame830x690: cv2.typing.MatLike) -> int:
        px, py = 830 // 2, 690 // 2
        box, score = find_tpl(
            frame830x690, self.enemy1, [1.0], score_threshold=0.83, debug=self.debug
        )
        if box is not None:
            dist = hypot(box["cx"] - px, box["cy"] - py)
            return 1 if dist < 255 else 0

        box, score = find_tpl(
            frame830x690, self.enemy2, [1.0], score_threshold=0.83, debug=self.debug
        )
        if box is not None:
            dist = hypot(box["cx"] - px, box["cy"] - py)
            return 1 if dist < 255 else 0

        return 0

    # def back(self):
    #     logger.debug("Exiting Krokust...")
    #     cv2.waitKey(0)
    #     super().back()
