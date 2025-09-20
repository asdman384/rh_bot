import time
from abc import ABC, abstractmethod
from math import hypot

import cv2
import numpy as np

from controller import Controller
from detect_location import find_tpl
from devices.device import Device
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
    # exit_sw_tpl_roi = (0, 260, 415, 640) # old
    exit_sw_tpl_roi = (60, 290, 365, 600)
    exit_ne_tpl_roi = (395, 120, 690, 340)

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
        self.exit_check_type = "mask"  # 'mask' | 'tpl'
        self.exit_tpl_sw = None
        self.exit_tpl_ne = None

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
        self, hsv: cv2.typing.MatLike, bgr: cv2.typing.MatLike
    ) -> tuple[bool, Direction | None]:
        if self.exit_check_type == "mask":
            return self.is_near_exit_mask(hsv)
        if self.exit_check_type == "tpl":
            return self.is_near_exit_tpl(bgr)

        near, dir = self.is_near_exit_mask(hsv)
        if near:
            return near, dir

        return self.is_near_exit_tpl(bgr)

    def is_near_exit_mask(
        self, hsv: cv2.typing.MatLike
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

    def is_near_exit_tpl(
        self, bgr: cv2.typing.MatLike
    ) -> tuple[bool, Direction | None]:
        if self.exit_tpl_sw is None or self.exit_tpl_ne is None:
            raise ValueError("Exit templates not set")

        X, Y, X2, Y2 = self.exit_sw_tpl_roi
        frame = cv2.resize(bgr[Y:Y2, X:X2], (X2 - X, Y2 - Y))
        box, score = find_tpl(
            frame, self.exit_tpl_sw, [1.0], score_threshold=0.74, debug=self.debug
        )
        if box is not None:
            return True, Direction.SW

        X, Y, X2, Y2 = self.exit_ne_tpl_roi
        frame = cv2.resize(bgr[Y:Y2, X:X2], (X2 - X, Y2 - Y))
        box, score = find_tpl(
            frame, self.exit_tpl_ne, [1.0], score_threshold=0.67, debug=self.debug
        )
        if box is not None:
            return True, Direction.NE

        return False, None

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


if __name__ == "__main__":
    try:
        from boss.dain import BossDain
    except ImportError:
        from dain import BossDain

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
