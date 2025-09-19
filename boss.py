import time
from abc import ABC, abstractmethod
from math import hypot

import cv2
import numpy as np

from bot_utils.screenshoter import save_image
from controller import Controller
from db import FA_BHALOR, FA_KHANEL
from detect_location import find_tpl, wait_for, wait_loading
from devices.device import Device
from frames import extract_game
from model import Direction


def extract_boss_health(frame: cv2.typing.MatLike) -> cv2.typing.MatLike:
    X = 408
    Y = 133
    W = 460
    H = 10
    return cv2.resize(frame[Y : Y + H, X : X + W], (W, H))


def measure_fill_px(roi: cv2.typing.MatLike, debug=False) -> float:
    H, W = roi.shape[:2]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

    mask = cv2.inRange(
        hsv,
        np.array([20, 90, 200], dtype=np.uint8),
        np.array([23, 118, 255], dtype=np.uint8),
    )

    # cv2.imshow("mask", mask)
    # cv2.waitKey(0)

    # ys, xs = np.where(mask > 0)

    # if len(xs) == 0 or len(ys) == 0:
    #     x, y, w, h = 0, 0, 0, 0
    # else:
    #     x, y = xs.min(), ys.min()
    #     w, h = xs.max() - xs.min() + 1, ys.max() - ys.min() + 1

    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    # Пороговые размеры
    min_h = 9
    max_h = 11
    min_w = 2
    max_w = 4

    if not cnts or len(cnts) == 0:
        return 0.0

    bx = None
    area = None
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)

        if h < min_h or h > max_h:
            continue
        if w < min_w or w > max_w:
            continue
        if h / max(w, 1) < 2:  # вытянутость по вертикали
            continue
        area = cv2.contourArea(c)
        if area / (w * h) < 0.2:  # отсекаем «рваные» и рамки
            continue

        bx = x + 2

    if debug:
        cv2.putText(
            roi,
            f"bx={bx}, w={W}, area={area}, w={w} h={h}",
            (10, 8),
            0,
            0.4,
            (0, 255, 0),
            1,
        )
        deb = np.vstack((roi, cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)))
        cv2.imshow("DBG/measure_fill_px", deb)
        cv2.waitKey(1)
        # save_image(
        #     deb,
        #     "images\\measure_fill_px\\fail_m" + time.strftime("%H-%M-%S") + ".png",
        # )

    if bx is None:
        return 0.0

    return bx / W * 100


class Boss(ABC):
    masks = None
    fa_dir_cells: dict[str, np.ndarray]
    fa_dir_threshold = {
        "ne": 18,
        "nw": 18,
        "se": 22,
        "sw": 22,
    }
    exit_sw_roi = (0, 260, 415, 640)
    exit_ne_roi = (395, 120, 690, 340)

    def __init__(self, controller: Controller, debug: bool = False) -> None:
        self.controller = controller
        self.debug = debug
        self.minimap_sense = False
        self._dist_thresh_px = 300
        self.max_moves = 500
        self.exit_door_area_threshold = 3000
        self.enter_room_clicks = 12
        self.use_slide = True
        self.exit_dbg_area: list = []
        self.no_combat_minions = False

    @abstractmethod
    def start_fight(self, dir: Direction) -> int:
        pass

    @abstractmethod
    def portal(self) -> None:
        pass

    def open_chest(self, dir: Direction) -> bool:
        # open chest
        self.controller.move_W() if dir == Direction.SW else self.controller.move_N()
        time.sleep(0.5)
        self.controller.skill_4()
        time.sleep(3)
        self.controller.move_W() if dir == Direction.SW else self.controller.move_N()
        time.sleep(0.5)
        return True

    def is_near_exit(
        self, hsv: cv2.typing.MatLike, bgr=None
    ) -> tuple[bool, Direction | None]:
        """
        https://pseudopencv.site/utilities/hsvcolormask/
        """
        H, W = hsv.shape[:2]
        px, py = W // 2, H // 2
        sw1 = cv2.inRange(hsv, self.SW_GATE_LOW1, self.SW_GATE_UPP1)
        sw2 = cv2.inRange(hsv, self.SW_GATE_LOW2, self.SW_GATE_UPP2)
        sw3 = cv2.inRange(hsv, self.SW_GATE_LOW3, self.SW_GATE_UPP3)
        # sw3 = cv2.morphologyEx(sw3, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
        # cv2.imshow("DBG/sw1", sw1)
        # cv2.imshow("DBG/sw2", sw2)
        # cv2.imshow("DBG/sw3", sw3)

        ne1 = cv2.inRange(hsv, self.NE_GATE_LOW1, self.NE_GATE_UPP1)
        ne2 = cv2.inRange(hsv, self.NE_GATE_LOW2, self.NE_GATE_UPP2)

        # cv2.imshow("DBG/ne1ne2", cv2.bitwise_or(ne1, ne2))
        # cv2.imshow("DBG/sw", cv2.bitwise_or(sw1, cv2.bitwise_or(sw2, sw3)))

        m = cv2.bitwise_or(
            cv2.bitwise_or(sw1, cv2.bitwise_or(sw2, sw3)),
            cv2.bitwise_or(ne1, ne2),
        )
        m = cv2.morphologyEx(
            m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8), iterations=2
        )
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=5)

        cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        verdict = False
        cx = None
        cy = None
        area = None
        dist = None
        for c in cnts:
            area = cv2.contourArea(c)
            print(area) if self.debug else None
            if area > self.exit_door_area_threshold:
                M = cv2.moments(c)
                if M["m00"] != 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])
                dist = hypot(cx - px, cy - py)
                verdict = 80 <= dist <= self._dist_thresh_px
                break

        if self.debug:
            cv2.putText(
                m, f"dist={dist}, area={area}", (10, 20), 0, 0.6, (255, 255, 255), 1
            )
            cv2.imshow("DBG/is_near_exit", m)
            cv2.waitKey(1)

            if verdict:
                print(f"dist={dist}, area={area}")

                if cx and cy:
                    self.exit_dbg_area.append((cx, cy))

                dbg = hsv.copy()
                for x, y in self.exit_dbg_area:
                    cv2.circle(dbg, (x, y), 6, (0, 0, 255), -1)
                cv2.imshow("exit/DBG", dbg)
                cv2.waitKey(1)

        return verdict, None

    def count_enemies(self, frame830x690: cv2.typing.MatLike | None = None) -> int:
        return 0

    def _get_frame(self) -> cv2.typing.MatLike:
        return self.controller.device.get_frame2()

    def tavern_Route(self) -> None:
        self.controller.press(315, 500, 1500)  # E
        time.sleep(0.5)
        self.controller.press(270, 460, 1600)  # NE
        time.sleep(0.8)

    def back(self) -> None:
        self.controller.back()
        time.sleep(0.2)
        self.controller._tap((740, 500))  # select yes
        self.controller.wait_loading(1)
        time.sleep(2.5)

    def _attk_focus_arrow(self, p: cv2.typing.Point | None = None) -> float:
        self.controller.skill_1(p)  # focus arrow
        time.sleep(3.2)
        hp = measure_fill_px(extract_boss_health(self._get_frame()), self.debug)
        print(f"Boss health after [focus arrow]: {hp:.1f} %") if self.debug else None
        return hp

    def _attk_barrage(self, p: cv2.typing.Point | None = None) -> float:
        self.controller.skill_2(p)  # barrage
        time.sleep(3.2)
        hp = measure_fill_px(extract_boss_health(self._get_frame()), self.debug)
        print(f"Boss health after [barrage]: {hp:.1f} %") if self.debug else None
        return hp

    def fix_disaster(self):
        time.sleep(2.5)  # wait for any animation to finish


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

    def start_fight(self, dir: Direction) -> int:
        if dir is None:
            return 100

        print("Fighting boss Khanel..." + dir.label)
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


class BossDain(Boss):
    def __init__(self, controller: Controller, debug: bool = False) -> None:
        super().__init__(controller, debug)
        self._dist_thresh_px = 350
        self.max_moves = 100
        self.fa_dir_cells = FA_KHANEL
        self.exit_door_area_threshold = 300
        self.enter_room_clicks = 10
        self.dain_sw = cv2.imread("resources/dain/sw.png")
        self.dain_ne = cv2.imread("resources/dain/ne.png")
        self.no_combat_minions = True

    def is_near_exit(
        self, hsv: cv2.typing.MatLike, bgr=None
    ) -> tuple[bool, Direction | None]:
        X, Y, X2, Y2 = self.exit_sw_roi
        frame = cv2.resize(bgr[Y:Y2, X:X2], (X2 - X, Y2 - Y))
        box, score = find_tpl(
            frame, self.dain_sw, [1.0], score_threshold=0.61, debug=self.debug
        )
        if box is not None:
            return True, Direction.SW

        X, Y, X2, Y2 = self.exit_ne_roi
        frame = cv2.resize(bgr[Y:Y2, X:X2], (X2 - X, Y2 - Y))
        box, score = find_tpl(
            frame, self.dain_ne, [1.0], score_threshold=0.42, debug=self.debug
        )
        if box is not None:
            return True, Direction.NE

        return False, None

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
        self.max_moves = 100
        self.fa_dir_cells = FA_KHANEL
        self.exit_door_area_threshold = 1600
        self.enter_room_clicks = 10
        self.use_slide = False
        self.fa_dir_threshold = {
            "ne": 11,
            "nw": 11,
            "se": 11,
            "sw": 11,
        }

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
        self.controller.move_SW() if dir == Direction.SW else self.controller.move_NE()
        time.sleep(0.5)
        self.controller.skill_4()
        time.sleep(2.6)
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


class BossMine(Boss):
    masks = {
        "player": {
            "l1": (150, 50, 134),
            "u1": (180, 90, 170),
            "l2": (150, 50, 134),
            "u2": (180, 90, 170),
        },
        "path": {
            "l1": (97, 109, 88),
            "u1": (123, 193, 125),
            "l2": (97, 109, 88),
            "u2": (123, 193, 125),
        },
        "wall": {
            "l1": (0, 100, 90),
            "u1": (5, 200, 125),
            "l2": (164, 93, 70),
            "u2": (180, 207, 201),
        },
    }

    def __init__(self, controller: Controller, debug: bool = False) -> None:
        super().__init__(controller, debug)
        self.use_slide = False
        self.fa_sense = False
        self.minimap_sense = True
        self.fa_dir_threshold = {
            "ne": 40,
            "nw": 40,
            "se": 40,
            "sw": 40,
        }
        self._dist_thresh_px = 400
        self.max_moves = 1000
        self.enter_room_clicks = 5
        self.map_xy = None
        self.no_combat_minions = True
        self.mine_sw = cv2.imread("resources/mine/mine_sw.png")
        self.mine_ne = cv2.imread("resources/mine/mine_ne.png")
        self.enemy1 = cv2.imread("resources/mine/enemy1.png")
        self.enemy2 = cv2.imread("resources/mine/enemy2.png")
        self.debug = True

    def is_near_exit(
        self, hsv: cv2.typing.MatLike, bgr=None
    ) -> tuple[bool, Direction | None]:
        X, Y, X2, Y2 = self.exit_sw_roi
        frame = cv2.resize(bgr[Y:Y2, X:X2], (X2 - X, Y2 - Y))
        box, score = find_tpl(
            frame, self.mine_sw, [1.0], score_threshold=0.53, debug=self.debug
        )
        if box is not None:
            return True, Direction.SW

        X, Y, X2, Y2 = self.exit_ne_roi
        frame = cv2.resize(bgr[Y:Y2, X:X2], (X2 - X, Y2 - Y))
        box, score = find_tpl(
            frame, self.mine_ne, [1.0], score_threshold=0.72, debug=self.debug
        )
        if box is not None:
            return True, Direction.NE

        return False, None

    def count_enemies(self, frame830x690: cv2.typing.MatLike) -> int:
        px, py = 830 // 2, 690 // 2
        box, score = find_tpl(
            frame830x690, self.enemy1, [1.0], score_threshold=0.62, debug=self.debug
        )
        if box is not None:
            dist = hypot(box["cx"] - px, box["cy"] - py)
            return 1 if dist < 271 else 0

        box, score = find_tpl(
            frame830x690, self.enemy2, [1.0], score_threshold=0.62, debug=self.debug
        )
        if box is not None:
            dist = hypot(box["cx"] - px, box["cy"] - py)
            return 1 if dist < 271 else 0

        return 0

    def start_fight(self, dir: Direction) -> int:
        if dir is None:
            print("dir not defined, cannot start fight")
            return 100

        print("Fighting boss Mine..." + dir.label)

        ne_route = [
            self.controller.move_N,
            self.controller.move_N,
            self.controller.move_NE,
            self.controller.move_NE,
            self.controller.move_NE,
            self.controller.move_NE,
            self.controller.move_NE,
            self.controller.move_NE,
            self.controller.move_NE,
            self.controller.move_NE,
            self.controller.move_E,
            self.controller.move_SE,
            self.controller.move_S,
            self.controller.move_SW,
            self.controller.move_SW,
            self.controller.move_SW,
            self.controller.move_SW,
            self.controller.move_SW,
            self.controller.move_SW,
            self.controller.move_SW,
        ]
        ne_route.reverse()

        sw_route = [
            self.controller.move_W,
            self.controller.move_W,
            self.controller.move_SW,
            self.controller.move_SW,
            self.controller.move_SW,
            self.controller.move_SW,
            self.controller.move_SW,
            self.controller.move_SW,
            self.controller.move_SW,
            self.controller.move_SW,
            self.controller.move_S,
            self.controller.move_SE,
            self.controller.move_E,
            self.controller.move_NE,
            self.controller.move_NE,
            self.controller.move_NE,
            self.controller.move_NE,
            self.controller.move_NE,
            self.controller.move_NE,
            self.controller.move_NE,
        ]
        sw_route.reverse()

        route = ne_route if dir == Direction.NE else sw_route
        fight_end = cv2.imread("resources/figth_end.png", cv2.IMREAD_COLOR)
        step = 0

        while len(route) > 0:
            route.pop()()
            step += 1
            if step < 12:
                time.sleep(0.1)
                continue
            if wait_for(fight_end, lambda: extract_game(self._get_frame()), 0.6):
                wait_loading(self._get_frame, 0.5)
                break

        print("Finish boss Mine..." + dir.label)
        return 0

    def open_chest(self, dir: Direction) -> bool:
        self.controller.move_NE()
        time.sleep(0.1)
        self.controller.move_SW()
        return True

    def tavern_Route(self) -> None:
        if self.map_xy is None:
            print("go Inventory")
            self.controller._tap((880, 620))  # Inventory button
            time.sleep(0.5)
            frame = self._get_frame()
            cv2.imshow("frame", frame)
            cv2.setMouseCallback("frame", self._mouse_callback)
            cv2.waitKey(0)
            cv2.destroyAllWindows()

            # close inventory
            if wait_for("resources/inventory.png", self._get_frame, 1):
                self.controller.back()
                time.sleep(0.5)

        self.controller._tap((880, 620))  # Inventory button
        if not wait_for("resources/inventory.png", self._get_frame, 1):
            raise "inventory problem 1"

        self.controller._tap(self.map_xy)  # Map item
        time.sleep(0.5)

        self.controller._tap((1150, 630))  # Use button
        time.sleep(0.5)

        wait_loading(self._get_frame)

        if wait_for("resources/inventory.png", self._get_frame, 1):
            time.sleep(1)
            self.controller.back()
        else:
            raise "inventory problem 2"

        if not wait_for("resources/mine.png", self._get_frame, 5, 0.74):
            print("mine not active")

    def _mouse_callback(self, event, x, y, flags, param):
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        self.map_xy = (x, y)
        print(f"map x={x}, y={y}")

    def portal(self) -> None:
        mine = cv2.imread("resources/mine.png", cv2.IMREAD_COLOR)
        mine_box, _ = find_tpl(self._get_frame(), mine, score_threshold=0.7)

        if mine_box is None:
            raise "mine_box problem"

        self.controller.click((mine_box["x"], mine_box["y"]))
        time.sleep(0.2)

        if not wait_for("resources/hidden_mine.png", self._get_frame, 6):
            raise "mine_box click problem"

        self.controller.confirm()
        self.controller.wait_loading(1)
        if not wait_for("resources/move_mine.png", self._get_frame):
            raise "Mine enter problem"
        self.controller.wait_loading(0.5)
        self.controller.back()
        time.sleep(0.1)

    def fix_disaster(self):
        time.sleep(1)  # wait for any animation to finish


if __name__ == "__main__":
    device = Device("127.0.0.1", 58526)
    device.connect()
    boss = BossDain(Controller(device), True)
    boss.start_fight(Direction.SW)

    # mine = cv2.imread("resources/mine.png", cv2.IMREAD_COLOR)
    # mine_box, _ = find_tpl(boss._get_frame(), mine, score_threshold=0.7, debug=True)
    cv2.waitKey(0)
    # boss.controller.click((mine_box["x"], mine_box["y"]))
    # cv2.waitKey(0)

    # res = wait_for(
    #     "resources/dain/sw_chest.png", lambda: boss._get_frame(), 1, 0.3, True
    # )

    # print(res)
    # cv2.waitKey(0)
    # boss.start_fight(Direction.NE)

    # while 1:
    # hp = measure_fill_px(extract_boss_health(device.get_frame2()), True)
    # if hp == 0:
    #     cv2.waitKey(0)
    # print(hp)
