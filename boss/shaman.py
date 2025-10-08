import logging
import time
from math import hypot

import cv2
import numpy as np

from boss.boss import Boss
from controller import Controller
from db import FA_BHALOR
from model import Direction
from sensor import FaSensor, MinimapSensor

logger = logging.getLogger(__name__)


# TODO:
class BossShaman(Boss):
    initial_minimap_open_dirs2 = {
        Direction.NE.label: False,
        Direction.NW.label: False,
        Direction.SE.label: True,
        Direction.SW.label: False,
    }

    def __init__(self, controller: Controller, debug: bool = False) -> None:
        super().__init__(controller, debug)

        self.max_moves = 150
        self.enter_room_clicks = 9
        self.no_combat_minions = True
        self.exit_check_type = "tpl"  # 'mask' | 'tpl'
        self.exit_tpl_sw_threshold = 0.57
        self.exit_tpl_sw = cv2.imread("resources/dain/sw.png")
        self.exit_tpl_ne = cv2.imread("resources/dain/ne.png")
        self.fa_dir_threshold = {"ne": 23, "nw": 23, "se": 23, "sw": 23}
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
        self.controller.move_N()
        time.sleep(0.2)
        self.sensor = FaSensor(
            None,
            None,
            self.fa_dir_threshold,
            debug=self.debug,
        )
        self.sensor.dir_cells = FA_BHALOR
        return
        self.sensor = MinimapSensor(
            None,
            self.minimap_masks,
            {"ne": 50, "nw": 50, "se": 35, "sw": 30},
            debug=self.debug,  # or True,
        )
        self.ensure_movement = True
        self.controller.move_E()
        time.sleep(0.2)
        self.controller.move_SE()

    def count_enemies(self, frame830x690: cv2.typing.MatLike) -> int:
        return 0

    def find_purple_marker(self, hsv):
        mask = cv2.inRange(hsv, (139, 183, 50), (152, 255, 85))

        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
            mask, connectivity=8
        )
        if num_labels <= 1:
            return None, mask  # не нашли

        # Самый крупный «фиолетовый» компонент (кроме фона)
        idx = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
        x, y, w, h, area = stats[idx]
        cx, cy = centroids[idx]

        # Быстрые фильтры по размеру/форме, чтобы отсеять мусор
        if area < 200 or w < 15 or h < 15:
            return None, mask

        box = (x, y, w, h)
        center = (int(cx), int(cy))
        return (center, box), mask

    def is_near_exit(self, hsv, bgr=None) -> tuple[bool, Direction | None]:
        H, W = hsv.shape[:2]
        # 1) находим фиолетовую метку
        hit, mask = self.find_purple_marker(hsv)
        if hit is None:
            return False, None

        (mx, my), (x, y, w, h) = hit

        # 3) дистанция до персонажа (персонаж всегда в центре камеры)
        px, py = W // 2, H // 2
        dist = hypot(mx - px, my - py)

        verdict = dist <= self._dist_thresh_px
        # 4) направление выхода относительно персонажа (центр кадра)
        if (0 <= mx <= 330 and 135 <= my <= 594) or (
            0 <= mx <= 460 and 180 <= my <= 594
        ):
            dir = Direction.SW
        else:
            dir = Direction.NE

        if (340 <= mx <= 785 and 0 <= my <= 170) or (
            470 <= mx <= 785 and 0 <= my <= 388
        ):
            dir = Direction.NE
        else:
            dir = Direction.SW

        if not self.debug:
            return verdict, dir

        # Отрисовка для отладки
        dbg = hsv.copy()
        cv2.circle(dbg, (mx, my), 8, (255, 0, 255), 2)
        cv2.circle(dbg, (px, py), 6, (0, 255, 0), -1)
        # Direction.SW
        cv2.rectangle(dbg, (0, 135), (330, 594), (0, 255, 0), 1)
        cv2.rectangle(dbg, (0, 180), (460, 594), (0, 255, 0), 1)

        # Direction.NE
        cv2.rectangle(dbg, (340, 0), (785, 170), (255, 0, 0), 1)
        cv2.rectangle(dbg, (470, 0), (785, 388), (255, 0, 0), 1)

        cv2.putText(
            dbg,
            f"dist={int(dist)}",
            (10, 30),
            0,
            0.9,
            (0, 255, 0),
            2,
        )
        print(
            f"Purple marker at ({mx},{my}), dist={dist:.1f}px, exit={verdict}, dir={dir}"
        )
        cv2.imshow("exit/DBG", dbg)
        cv2.waitKey(1)
        return verdict, dir

    def start_fight(self, dir: Direction) -> int:
        self.controller.use_click = False
        logger.debug(f"Fighting boss Shaman... dir: {dir}")
        time.sleep(0.1)
        self.controller.yes()
        time.sleep(0.1)
        self.controller.yes()
        time.sleep(0.1)
        self.controller.move_NW()
        time.sleep(0.5)
        # Somersault
        self.controller.skill_3((680, 330) if dir == Direction.SW else (590, 400))
        time.sleep(3.2)
        self.controller.skill_3()  # elven blessing
        time.sleep(1.5)

        ne_routine = [
            self._attk_focus_arrow,  # piercing arrow
            lambda: self._attk_focus_arrow((770, 270)),  # focus arrow
            lambda: self._attk_barrage((680, 260)),  # grenade
            lambda: self._attk_barrage((680, 330)),  # barrage
        ]

        sw_routine = [
            self._attk_focus_arrow,  # piercing arrow
            lambda: self._attk_focus_arrow((420, 510)),  # focus arrow
            lambda: self._attk_barrage((430, 430)),  # grenade
            lambda: self._attk_barrage((590, 400)),  # barrage
        ]

        routine = ne_routine if dir == Direction.NE else sw_routine
        hp = 100
        while hp > 0 and len(routine) > 0:
            logger.debug(f"steps left: {len(routine)} hp left: {hp}")
            time.sleep(1) if len(routine) == 2 else time.sleep(0.1)
            hp = routine.pop()()

        logger.debug("Finished boss Shaman...")
        self.controller.use_click = True
        return hp

    def portal(self) -> None:
        self.controller._tap((1000, 630))  # page +1
        time.sleep(0.2)
        self.controller._tap((1000, 630))  # page +1
        time.sleep(0.2)
        self.controller._tap((1150, 270))  # select Shaman
        time.sleep(2.5)
