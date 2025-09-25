import logging
import time

import cv2
import numpy as np

from boss.boss import Boss
from controller import Controller
from count_enemies import count_enemies
from devices.device import Device
from edges_diff import bytes_hamming, roi_edge_signature
from frames import extract_game
from model import Direction
from sensing.minimap import minimap_open_dirs

LOWER = np.array([95, 90, 99])
UPPER = np.array([105, 137, 181])

LOWER_1 = np.array([94, 54, 115])
UPPER_2 = np.array([108, 102, 181])

THRESHOLD_BITS = 38

logger = logging.getLogger(__name__)


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


def direction_possibility(dir: np.ndarray[tuple[int, int]], mask: np.ndarray) -> float:
    vals = mask[tuple(dir.T)]
    i = int((vals > 220).sum())
    return i / len(dir) * 100


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
        self.debug = debug
        self.moves = 0
        self.last_combat = 0
        self._init_minimap_sense_dirs = True

    def init_camera(self) -> None:
        # Initial move to get the camera right
        global _blue_mask
        global _prev_p_xy
        global _minimap_open_dirs2_initiation
        _blue_mask = None
        _prev_p_xy = None
        _minimap_open_dirs2_initiation = True
        self._init_minimap_sense_dirs = True
        self._last_frame = None
        self.boss.init_camera()
        self._is_exit = (False, None)
        self.moves = 0
        self.last_combat = 0
        time.sleep(0.25)
        self.sense()

    def is_exit(self) -> tuple[bool, Direction | None]:
        return self._is_exit

    def move(self, d: Direction) -> tuple[bool, bool]:
        """
        return (move)
        """
        self.moves += 2
        move = getattr(self.controller, f"move_{d.label}", None)
        if move is None:
            raise AttributeError(f"Movement has no method move_{d.label}")

        steps = 2 if self.boss.minimap_sense else 3
        for _ in range(steps):
            if self._enemies > 0:
                self._clear_enemies(self.boss.use_slide)
            move()

            if not self.boss.minimap_sense and _ != 2:
                frame830x690 = extract_game(self.get_frame())
                frame830x690hsv = cv2.cvtColor(frame830x690, cv2.COLOR_BGR2HSV)
                self._enemies = self._count_enemies(frame830x690hsv, frame830x690)
                self._is_exit = self.boss.is_near_exit(frame830x690hsv, frame830x690)
            else:
                time.sleep(0.02)

            if self._is_exit[0] and self._enemies == 0:
                return True

        time.sleep(0 if self.boss.minimap_sense else 0.15)

        newFrame = self.sense()
        return not self.boss.ensure_movement or self._is_moved(newFrame, d)

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

    def _clear_enemies(self, use_skills=True) -> bool:
        attacks_count = 0
        while self._enemies > 0 and attacks_count < 50:
            if (
                attacks_count == 8
                and use_skills
                and (self.moves - self.last_combat > 3)
            ):
                time.sleep(0.5)
                print("Using skill 4")
                self.controller.skill_4()  # multi arrow
                self.controller.skill_4()  # multi arrow
                time.sleep(1)

            self.controller.attack()
            self._enemies = self._count_enemies()
            attacks_count += 1
        time.sleep(1)
        self.moves += 1
        self.last_combat = self.moves
        return False

    def _count_enemies(
        self,
        frame830x690hsv: cv2.typing.MatLike | None = None,
        frame830x690: cv2.typing.MatLike | None = None,
    ) -> int:
        if self.boss.no_combat_minions:
            return self.boss.count_enemies(
                extract_game(self.get_frame()) if frame830x690 is None else frame830x690
            )

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
        if not self.boss.minimap_sense:
            self.controller._tap(self.controller.skill_1_point)
            time.sleep(0.1)

        frame = self.get_frame()

        if not self.boss.minimap_sense:
            self.controller._tap(self.controller.skill_1_point_cancel)
            time.sleep(0.05)

        return frame

    def _open_dirs(self, bgr_full_frame):
        if self.boss.minimap_sense:
            return minimap_open_dirs(
                extract_minimap(bgr_full_frame),
                self.boss.minimap_masks,
                self.boss.fa_dir_threshold,
                self.debug,
            )

        return fa_get_open_dirs(
            bgr_full_frame,
            self.boss.fa_dir_cells,
            self.boss.fa_dir_threshold,
            self.debug,
        )

    def sense(self) -> cv2.typing.MatLike:
        decoded = self._get_frame_fa()
        frame830x690 = extract_game(decoded)

        frame830x690hsv = cv2.cvtColor(frame830x690, cv2.COLOR_BGR2HSV)
        # detect exit
        self._is_exit = self.boss.is_near_exit(frame830x690hsv, frame830x690)
        # detect enemies
        self._enemies = self._count_enemies(frame830x690hsv, frame830x690)
        if self._enemies > 0:
            self._clear_enemies(self.boss.use_slide)
            time.sleep(0.5 if self.boss.minimap_sense else 1)

        # detect possible directions
        self._direction_dict = self._open_dirs(
            frame830x690 if not self.boss.minimap_sense else decoded
        )

        # Check if all directions are zero
        if all(not v for v in self._direction_dict.values()):
            logger.debug(
                "Warning: All direction possibilities are zero. Sensing again..."
            )
            self.boss.fix_disaster()
            decoded = self._get_frame_fa()
            frame830x690 = extract_game(decoded)
            self._direction_dict = self._open_dirs(
                frame830x690 if not self.boss.minimap_sense else decoded
            )

        return decoded


if __name__ == "__main__":
    from boss import BossDelingh, BossDain

    device = Device("127.0.0.1", 58526)
    device.connect()
    controller = Controller(device)
    boss = BossDain(controller, True)
    maze = MazeRH(controller, boss, True)

    # # TEST is_near_exit
    while 1:
        # maze.sense()
        frame830x690 = extract_game(maze.get_frame())
        frame830x690hsv = cv2.cvtColor(frame830x690, cv2.COLOR_BGR2HSV)
        res, _ = boss.is_near_exit(frame830x690hsv, frame830x690)
        print(res, _)

    # # TEST is_near_exit thresolds
    # frame = extract_game(device.get_frame2())

    # # Direction.SW
    # cv2.rectangle(frame, (0, 260), (415, 630), (0, 255, 0), 1)
    # cv2.rectangle(frame, (0, 260), (415, 630), (0, 255, 0), 1)

    # # Direction.NE
    # cv2.rectangle(frame, (395, 120), (830, 330), (255, 0, 0), 1)
    # cv2.rectangle(frame, (395, 120), (830, 330), (255, 0, 0), 1)
    # cv2.imshow("frame", frame)
    # cv2.waitKey(0)
