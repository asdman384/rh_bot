import time
import cv2

from detect_location import find_tpl, wait_for, wait_loading
from devices.device import Device


class Controller:
    _delay = 0.170  # Default delay between movements
    skill_1_point = (920, 600)
    skill_1_point_cancel = (930, 510)
    skill_2_point = (1020, 600)
    skill_3_point = (1120, 600)
    skill_4_point = (1220, 600)

    def __init__(self, device: Device, debug=False):
        self.device: Device = device
        self.debug = debug
        self.use_click = False

    def press(self, x, y, time_ms=_delay):
        self.device.device.shell(f"input swipe {x} {y} {x} {y} {time_ms}")

    def move_W(self, cell=1):
        for _ in range(cell):
            self._tap((115, 500))
            time.sleep(self._delay)

    def move_E(self, cell=1):
        for _ in range(cell):
            self._tap((315, 500))
            time.sleep(self._delay)

    def move_N(self, cell=1):
        for _ in range(cell):
            self._tap((220, 425))
            time.sleep(self._delay)

    def move_S(self, cell=1):
        for _ in range(cell):
            self._tap((220, 580))
            time.sleep(self._delay)

    # Diagonal movements
    # ↖
    def move_NW(self, cell=1):
        for _ in range(cell):
            self._tap((170, 460))
            time.sleep(self._delay)

    # ↗
    def move_NE(self, cell=1):
        for _ in range(cell):
            self._tap((270, 460))
            time.sleep(self._delay)

    # ↙
    def move_SW(self, cell=1):
        for _ in range(cell):
            self._tap((170, 540))
            time.sleep(self._delay)

    # ↘
    def move_SE(self, cell=1):
        for _ in range(cell):
            self._tap((270, 540))
            time.sleep(self._delay)

    def skill_1(self, p: cv2.typing.Point | None = None):
        self._tap(self.skill_1_point)
        time.sleep(0.1)
        self._tap(self.skill_1_point if p is None else p)

    def skill_2(self, p: cv2.typing.Point | None = None):
        self._tap(self.skill_2_point)
        time.sleep(0.1)
        self._tap(self.skill_2_point if p is None else p)

    def skill_3(self, p: cv2.typing.Point | None = None):
        self._tap(self.skill_3_point)
        time.sleep(0.1)
        self._tap(self.skill_3_point if p is None else p)

    def skill_4(self, p: cv2.typing.Point | None = None):
        self._tap(self.skill_4_point)
        time.sleep(0.1)
        self._tap(self.skill_4_point if p is None else p)

    def _tap(self, xy: cv2.typing.Point):
        if self.use_click:
            self.click(xy)
        else:
            self.device.device.shell(f"input tap {xy[0]} {xy[1]}", decode=False)

    def click(self, xy: cv2.typing.Point):
        self.device.click(xy)

    # Back button
    def back(self):
        return self.device.device.shell("input keyevent 4")

    def yes(self):
        return self._tap((740, 500))

    def confirm(self):
        return self._tap((740, 530))

    def attack(self):
        res = self.device.device.shell("input tap 1100 450")
        # time.sleep(0.6) # bhalor
        time.sleep(0.2)  # khanel
        return res

    def wait_loading(self, wait_appearance=0.5, timeout=1):
        wait_loading(
            self.device.get_frame2,
            wait_appearance=wait_appearance,
            timeout=timeout,
            retry=self.yes,
            debug=self.debug,
        )

    def full_back(self, close_game=False):
        def get_frame():
            return self.device.get_frame2()

        exit = "resources/exit.png"
        monetia = cv2.imread("resources/monetia.png", cv2.IMREAD_COLOR)
        monetia_box, _ = find_tpl(get_frame(), monetia, debug=self.debug)
        while monetia_box is None:
            self.back()
            if wait_for(exit, get_frame, 1, debug=self.debug):
                self.yes()
            if wait_loading(get_frame, 3, debug=self.debug):
                time.sleep(3)
            monetia_box, _ = find_tpl(get_frame(), monetia, debug=self.debug)

    def flush_bag(self, decompose=True) -> bool:
        print("flush bag")
        black = cv2.imread("resources/black.png", cv2.IMREAD_COLOR)
        black_box, _ = find_tpl(self.device.get_frame2(), black, score_threshold=0.9)
        if black_box is None:
            print("failed to flush bag")
            return False

        # sort
        print("sort Inventory")
        self._tap((880, 620))  # Inventory button
        time.sleep(0.5)
        self._tap((1170, 650))  # Sort button
        self.wait_loading(1)
        self.back()
        time.sleep(0.5)

        # go blacksmith
        print("go blacksmith")
        self._tap((black_box["x"], black_box["y"]))
        time.sleep(1)

        # Decompose routine
        if decompose:
            print("decompose items")
            self._tap((1060, 320))  # Decompose button
            time.sleep(1)
            for x in range(680, 1081, 100):
                self._tap((x, 450))  # Select Items
                time.sleep(0.05)

            self._tap((1140, 360))  # Decompose action button
            time.sleep(0.5)
            check_box, _ = find_tpl(
                self.device.get_frame2(),
                cv2.imread("resources/check_grade.png", cv2.IMREAD_COLOR),
                score_threshold=0.9,
            )
            if check_box is not None:
                self._tap((740, 500))  # Confirm button

            self.wait_loading(2)
            time.sleep(0.5)
            self.back()
            time.sleep(0.5)

        # Trade routine
        print("trade items")
        self._tap((1060, 390))  # Trade button
        time.sleep(0.5)
        self._tap((700, 380))  # Equip tab
        time.sleep(0.5)
        self._tap((1170, 375))  # Sell button
        time.sleep(0.5)
        self._tap((1150, 115))  # Sell the grade button
        time.sleep(0.5)
        self._tap((400, 260))  # Increase grade button
        time.sleep(0.05)
        self._tap((400, 260))  # Increase grade button
        time.sleep(0.05)
        self._tap((850, 490))  # OK button
        self.wait_loading(2)

        self.full_back()

        return True
