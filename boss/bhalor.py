import time
from math import hypot

import cv2
import numpy as np

from boss.boss import Boss
from controller import Controller
from db import FA_BHALOR
from model import Direction


class BossBhalor(Boss):
    def __init__(self, controller: Controller, debug: bool = False) -> None:
        super().__init__(controller, debug)
        self._dist_thresh_px = 400
        self.fa_dir_cells = FA_BHALOR
        self.use_slide = False

    def start_fight(self, dir: Direction) -> int:
        print("Fighting boss Bhalor...") if self.debug else None
        self.controller.skill_3(
            (590, 390) if dir == Direction.SW else (690, 320)
        )  # slide
        time.sleep(2)
        self.controller.skill_3()  # elven blessing
        time.sleep(1.4)

        if dir == Direction.NE:
            hp = self._attk_focus_arrow((640, 230))  # focus arrow

            if hp != 0:
                hp = self._attk_barrage((690, 320))  # barrage

            if hp != 0:
                hp = self._attk_barrage()  # grenade

        elif dir == Direction.SW:
            hp = self._attk_barrage((590, 390))  # barrage

            if hp != 0:
                hp = self._attk_barrage()  # grenade

            if hp != 0:
                hp = self._attk_focus_arrow((430, 430))  # focus arrow

        return hp

    # ##На кадре «выход» имеет два устойчивых признака:
    #  - фиолетовая метка-череп над воротами
    #  - «решётка» вертикальных досок (сильные вертикальные грани)
    # ##Самый практичный пайплайн на OpenCV:
    #  - Найти фиолетовую метку в HSV (маска по цвету + морфология).
    #  - Вокруг найденной метки взять ROI и убедиться, что в нём преобладают вертикальные грани (Sobel по x/y или HoughLinesP).
    #  - Оценить расстояние от центра персонажа (обычно центр кадра) до метки и вернуть true, если оно меньше порога.
    # Код даёт True/False и, при желании, рисует отладочную картинку.
    def find_purple_marker(self, hsv):
        # Диапазоны для пурпурного/фиолетового (можно подстроить под вашу игру)
        lower1 = np.array([129, 220, 100])  # H,S,V
        upper1 = np.array([137, 235, 150])

        mask = cv2.inRange(hsv, lower1, upper1)
        ## remove noise
        # mask = cv.morphologyEx(mask, cv.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=2)
        # mask = cv.morphologyEx(
        #     mask, cv.MORPH_CLOSE, np.ones((5, 5), np.uint8), iterations=2
        # )

        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
            mask, connectivity=8
        )
        if num_labels <= 1:
            return None, mask  # не нашли

        # Самый крупный «фиолетовый» компонент (кроме фона)
        idx = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
        x, y, w, h, area = stats[idx]
        cx, cy = centroids[idx]

        # print(f"Purple marker: area={area} box=({w}x{h})")
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

    def portal(self) -> None:
        self.controller._tap((1000, 630))  # page +1
        time.sleep(0.4)
        self.controller._tap((1150, 350))  # select Bhalor
        time.sleep(2.5)
