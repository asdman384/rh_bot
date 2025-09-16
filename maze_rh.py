import time

import cv2
import numpy as np

from boss import Boss, BossDain, BossElvira, BossKhanel, BossMine
from bot_utils.drafts import print_pixels_array
from controller import Controller
from count_enemies import count_enemies
from db import (
    RECT,
    NE_square,
    NW_square,
    SE_square,
    SW_square,
)
from devices.device import Device
from edges_diff import bytes_hamming, roi_edge_signature
from model import Direction

LOWER = np.array([95, 90, 99])
UPPER = np.array([105, 137, 181])

LOWER_1 = np.array([94, 54, 115])
UPPER_2 = np.array([108, 102, 181])

THRESHOLD_BITS = 38


def put_labels(
    frame: cv2.typing.MatLike, text: str, p: cv2.typing.Point
) -> cv2.typing.MatLike:
    cv2.putText(
        frame,
        text,
        p,
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (255,),
        1,
        cv2.LINE_AA,
    )


def extract_center(frame: cv2.typing.MatLike) -> cv2.typing.MatLike:
    X = 640 - 150 - 1
    Y = 345 - 80
    W = 300
    H = 200
    return cv2.resize(frame[Y : Y + H, X : X + W], (W, H))


def extract_minimap(frame: cv2.typing.MatLike) -> cv2.typing.MatLike:
    X = 0
    Y = 100
    W = 350
    H = 300
    return cv2.resize(frame[Y : Y + H, X : X + W], (W, H))


def extract_game(frame: cv2.typing.MatLike) -> cv2.typing.MatLike:
    X = 240
    Y = 0
    W = 830
    H = 690
    return cv2.resize(frame[Y : Y + H, X : X + W], (W, H))


def direction_possibility(dir: np.ndarray[tuple[int, int]], mask: np.ndarray) -> float:
    vals = mask[tuple(dir.T)]
    i = int((vals > 220).sum())
    return i / len(dir) * 100


def get_open_dirs(frame300x200, debug=False):
    hsv = cv2.cvtColor(frame300x200, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, LOWER, UPPER) | cv2.inRange(hsv, LOWER_1, UPPER_2)

    ne = direction_possibility(NE_square, mask)
    nw = direction_possibility(NW_square, mask)
    se = direction_possibility(SE_square, mask)
    sw = direction_possibility(SW_square, mask)

    if debug:
        put_labels(mask, f"NE:{ne:.1f}", (220, 35))
        put_labels(mask, f"NW:{nw:.1f}", (10, 35))
        put_labels(mask, f"SE:{se:.1f}", (220, 170))
        put_labels(mask, f"SW:{sw:.1f}", (10, 170))
        cv2.imshow("get_open_dirs/DBG", mask)
        cv2.waitKey(1)

    return {
        Direction.NE.label: ne > 17,
        Direction.NW.label: nw > 17,
        Direction.SE.label: se > 17,
        Direction.SW.label: sw > 17,
    }


def fa_get_open_dirs(
    bgr_img, dir_cells: dict[str, np.ndarray], dir_threshold, debug=False
):
    """
    Focused arrow sensing.

    bgr_img - image with 'Focused arrow' grid applied
    """
    gray = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    g = clahe.apply(gray)
    # выделяем тонкие яркие линии сетки
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    tophat = cv2.morphologyEx(g, cv2.MORPH_TOPHAT, kernel)
    tophat = cv2.GaussianBlur(tophat, (3, 3), 0)
    th = max(30, int(0.35 * tophat.max()))
    _, mask = cv2.threshold(tophat, th, 255, cv2.THRESH_BINARY)

    # print_pixels_array(mask)
    # clean ?
    # mask = cv2.medianBlur(mask, 3)
    # cv2.imshow("mask", mask)
    # cv2.waitKey(0)
    # more clean ?
    # mask = cv2.morphologyEx(
    #     mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    # )
    # cv2.imshow("mask", mask)
    # cv2.waitKey(0)

    ne = direction_possibility(dir_cells["NE_RECT"], mask)
    se = direction_possibility(dir_cells["SE_RECT"], mask)
    sw = direction_possibility(dir_cells["SW_RECT"], mask)
    nw = direction_possibility(dir_cells["NW_RECT"], mask)

    if debug:
        put_labels(mask, f"NE:{ne:.1f}", (220 + 250, 300))
        put_labels(mask, f"NW:{nw:.1f}", (10 + 250, 300))
        put_labels(mask, f"SE:{se:.1f}", (220 + 250, 170 + 265))
        put_labels(mask, f"SW:{sw:.1f}", (10 + 250, 170 + 265))
        cv2.imshow("get_open_dirs/DBG", mask)
        cv2.waitKey(1)

    return {
        Direction.NE.label: ne > dir_threshold["ne"],
        Direction.NW.label: nw > dir_threshold["nw"],
        Direction.SE.label: se > dir_threshold["se"],
        Direction.SW.label: sw > dir_threshold["sw"],
    }


def minimap_open_dirs(hsv: cv2.typing.MatLike):
    pass


class MazeRH:
    _is_exit: tuple[bool, Direction | None] = (False, None)
    _enemies = 0
    _last_frame: bytes | None = None
    _direction_dict = {
        Direction.NE.label: False,
        Direction.NW.label: False,
        Direction.SE.label: False,
        Direction.SW.label: False,
    }

    def __init__(
        self,
        controller: Controller,
        boss: Boss = None,
        debug: bool = False,
    ) -> None:
        self.controller = controller
        self.boss = boss
        self.fa_sense = boss.fa_sense
        self.debug = debug
        self.moves = 0
        self.last_combat = 0

    def init_camera(self) -> None:
        # Initial move to get the camera right
        self.controller.move_SE()
        self.controller.move_NW()
        self._is_exit = (False, None)
        self.moves = 0
        self.last_combat = 0
        time.sleep(0.5)
        self.sense()

    def is_exit(self) -> tuple[bool, Direction | None]:
        return self._is_exit

    def move(self, d: Direction) -> tuple[bool, bool]:
        """
        return (moved, slided)
        """
        slided = False
        self.moves += 2
        move = getattr(self.controller, f"move_{d.label}", None)
        if move is None:
            raise AttributeError(f"Movement has no method move_{d.label}")

        for _ in range(3 if self.fa_sense else 1):
            if self._enemies > 0:
                slided = self._clear_enemies()
            move()
            if self.fa_sense and _ != 2:
                frame830x690 = extract_game(self.get_frame())
                frame830x690hsv = cv2.cvtColor(frame830x690, cv2.COLOR_BGR2HSV)
                self._enemies = self._count_enemies(frame830x690hsv)
                self._is_exit = self.boss.is_near_exit(frame830x690hsv)

            if self._is_exit[0] and self._enemies == 0:
                return True, slided

        time.sleep(0.15)
        newFrame = self.sense()
        return self.fa_sense or self._is_moved(newFrame, d), slided

    def _is_moved(self, frame: cv2.typing.MatLike, d: Direction):
        # ttt = newFrame.copy()
        # cv2.rectangle(ttt, (15, 120), (15 + 1255, 120 + 415), (0, 255, 0), 1)
        # cv2.imshow("newFrame", ttt)
        # cv2.waitKey(0)

        # newFrame = roi_edge_signature(self.sense(), (365, 150, 570, 400)) # Bhalor works OK
        newFrame = roi_edge_signature(frame, (15, 120, 1255, 415))

        diff = True
        if self._last_frame is not None:
            bytess = bytes_hamming(self._last_frame, newFrame)
            if self.debug:
                print(f"Moved {d.label}, diff bits: {bytess} > {THRESHOLD_BITS}")
            diff = bytess >= THRESHOLD_BITS

        self._last_frame = newFrame
        del newFrame
        return diff

    def _clear_enemies(self, use_slide=True) -> bool:
        slided = False
        if (self.moves - self.last_combat > 3) and self.boss.use_slide and use_slide:
            time.sleep(0.2)
            self.controller.skill_3()  # slide
            slided = True
            self.last_combat = self.moves

        attacks_count = 0
        while self._enemies > 0 and attacks_count < 50:
            self.controller.attack()
            self._enemies = self._count_enemies()
            attacks_count += 1
        time.sleep(1)

        return slided

    def _count_enemies(self, frame830x690hsv: cv2.typing.MatLike | None = None) -> int:
        if frame830x690hsv is None:
            frame830x690hsv = cv2.cvtColor(
                extract_game(self.get_frame()), cv2.COLOR_BGR2HSV
            )
        return count_enemies(frame830x690hsv, self.debug)

    def can_move(self, d: Direction) -> bool:
        return self._direction_dict.get(d.label, False)

    def get_frame(self) -> cv2.typing.MatLike:
        return self.controller.device.get_frame2()

    def _get_frame_fa(self) -> cv2.typing.MatLike:
        if self.fa_sense:
            self.controller._tap(self.controller.skill_1_point)
            time.sleep(0.1)

        frame = self.get_frame()

        if self.fa_sense:
            self.controller._tap(self.controller.skill_1_point_cancel)
            time.sleep(0.05)

        return frame

    def _open_dirs(self, bgr_full_frame):
        if self.fa_sense:
            return fa_get_open_dirs(
                bgr_full_frame,
                self.boss.fa_dir_cells,
                self.boss.fa_dir_threshold,
                self.debug,
            )
        return get_open_dirs(extract_center(bgr_full_frame), self.debug)

    def sense(self) -> cv2.typing.MatLike:
        decoded = self._get_frame_fa()
        frame830x690 = extract_game(decoded)

        frame830x690hsv = cv2.cvtColor(frame830x690, cv2.COLOR_BGR2HSV)
        # detect exit
        self._is_exit = self.boss.is_near_exit(frame830x690hsv)
        # detect enemies
        self._enemies = self._count_enemies(frame830x690hsv)
        if self._enemies > 0:
            self._clear_enemies(False)
            time.sleep(1)

        # detect possible directions
        self._direction_dict = self._open_dirs(
            frame830x690 if self.fa_sense else decoded
        )

        # Check if all directions are zero
        if all(not v for v in self._direction_dict.values()):
            print("Warning: All direction possibilities are zero. Sensing again...")
            self.boss.fix_disaster()
            decoded = self._get_frame_fa()
            frame830x690 = extract_game(decoded)
            self._direction_dict = self._open_dirs(
                frame830x690 if self.fa_sense else decoded
            )

        return decoded


if __name__ == "__main__":
    device = Device("127.0.0.1", 58526)
    device.connect()
    controller = Controller(device)
    # boss = BossKhanel(controller, False)
    boss = BossMine(controller, True)
    maze = MazeRH(controller, boss, True)

    def find_largest_contour_centroid(mask):
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cnts:
            return None
        c = max(cnts, key=cv2.contourArea)
        M = cv2.moments(c)
        if M["m00"] == 0:
            return None
        cx = int(M["m10"] / M["m00"])
        cy = int(M["m01"] / M["m00"])
        return (cx, cy)

    def player_mask(hsv: cv2.typing.MatLike) -> cv2.typing.MatLike:
        pm1 = cv2.inRange(hsv, (0, 66, 116), (7, 109, 170))
        pm2 = cv2.inRange(hsv, (151, 21, 114), (180, 127, 206))
        pm = cv2.bitwise_or(pm1, pm2)

        # Чистим от шумов
        kernel = np.ones((5, 5), np.uint8)
        pm = cv2.morphologyEx(pm, cv2.MORPH_OPEN, kernel, iterations=1)
        # pm = cv2.morphologyEx(pm, cv2.MORPH_CLOSE, kernel, iterations=1)
        return pm

    def check_rect(frame, p_xy, prev_p_xy, offset) -> float:
        white_count = 0
        for x, y in RECT:
            if prev_p_xy is not None:
                p_xy = (
                    prev_p_xy[0] if abs(prev_p_xy[0] - p_xy[0]) > 10 else p_xy[0],
                    prev_p_xy[1] if abs(prev_p_xy[1] - p_xy[1]) > 10 else p_xy[1],
                )

            rect_x = x + p_xy[0] + offset[0]
            rect_y = y + p_xy[1] + offset[1]

            if rect_y >= 300 or rect_x >= 350:
                continue

            # frame[rect_y, rect_x] = 0

            if frame[rect_y, rect_x] == 255:
                white_count += 1

        return white_count / len(RECT) * 100

    frame = cv2.imread("frame.png", cv2.IMREAD_COLOR)

    ## new sense
    prev_p_xy = None
    while 1:
        frame = extract_minimap(maze.get_frame())
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        pm = player_mask(hsv)
        cv2.imshow("minimap/pm", pm)

        p_xy = find_largest_contour_centroid(pm)

        path_m = cv2.inRange(hsv, (97, 109, 88), (123, 193, 125))
        wall_m1 = cv2.inRange(hsv, (0, 100, 90), (5, 200, 125))
        wall_m2 = cv2.inRange(hsv, (164, 93, 70), (180, 207, 201))
        lab = cv2.bitwise_or(path_m, cv2.bitwise_or(wall_m1, wall_m2))
        cv2.imshow("minimap/lab", lab)

        ne = 0
        nw = 0
        se = 0
        sw = 0

        if p_xy is not None:
            ne = check_rect(lab, p_xy, prev_p_xy, boss.offset["NE"])
            nw = check_rect(lab, p_xy, prev_p_xy, boss.offset["NW"])
            se = check_rect(lab, p_xy, prev_p_xy, boss.offset["SE"])
            sw = check_rect(lab, p_xy, prev_p_xy, boss.offset["SW"])

            cv2.circle(frame, p_xy, 2, (255, 255, 255), 2)
            cv2.imshow("minimap/frame", frame)

        print(f"ne={ne:.1f} nw={nw:.1f} se={se:.1f} sw={sw:.1f}")
        cv2.waitKey(10)

        if p_xy is not None:
            prev_p_xy = p_xy

    # # TEST is_near_exit
    # while 1:
    #     res, _ = boss.is_near_exit(
    #         cv2.cvtColor(extract_game(maze.get_frame()), cv2.COLOR_BGR2HSV)
    #     )
    #     print(res)

    ## TEST is_near_exit thresolds
    # frame = extract_game(device.get_frame2())

    # # Direction.SW
    # cv2.rectangle(frame, (0, 260), (415, 630), (0, 255, 0), 1)
    # cv2.rectangle(frame, (0, 260), (415, 630), (0, 255, 0), 1)

    # # Direction.NE
    # cv2.rectangle(frame, (395, 120), (830, 330), (255, 0, 0), 1)
    # cv2.rectangle(frame, (395, 120), (830, 330), (255, 0, 0), 1)
    # cv2.imshow("frame", frame)
    # cv2.waitKey(0)
