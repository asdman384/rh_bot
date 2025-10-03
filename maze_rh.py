import logging
import time

import cv2

from boss.boss import Boss
from controller import Controller
from devices.device import Device
from edges_diff import bytes_hamming, roi_edge_signature
from frames import extract_game
from model import Direction


THRESHOLD_BITS = 31

logger = logging.getLogger(__name__)


def extract_center(frame: cv2.typing.MatLike) -> cv2.typing.MatLike:
    X = 640 - 150 - 1
    Y = 345 - 80
    W = 300
    H = 200
    return cv2.resize(frame[Y : Y + H, X : X + W], (W, H))


class MazeRH:
    _is_exit: tuple[bool, Direction | None] = (False, None)
    _enemies = 0
    _last_frame: bytes | None = None
    _direction_dict = {
        Direction.NE: False,
        Direction.NW: False,
        Direction.SE: False,
        Direction.SW: False,
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

    def init_camera(self) -> None:
        # Initial move to get the camera right
        self._last_frame = None
        self.boss.init_camera()
        self._is_exit = (False, None)
        self.moves = 0
        self.last_combat = 0
        time.sleep(0.25)
        self._sense()

    def is_exit(self) -> tuple[bool, Direction | None]:
        return self._is_exit

    def move(self, d: Direction, disaster_recovered=False) -> bool:
        """
        return is moved
        """
        self.moves += 2
        move = getattr(self.controller, f"move_{d.label}", None)
        if move is None:
            raise AttributeError(f"Movement has no method move_{d.label}")

        for _ in range(self.boss.sensor.steps):
            if self._enemies > 0:
                self._clear_enemies(self.boss.use_slide)
            move()
            self.boss.sensor.move(d)

            if _ != self.boss.sensor.steps - 1:
                frame830x690 = extract_game(self.get_frame())
                frame830x690hsv = cv2.cvtColor(frame830x690, cv2.COLOR_BGR2HSV)
                self._enemies = self._count_enemies(frame830x690)
                self._is_exit = self.boss.is_near_exit(frame830x690hsv, frame830x690)

            if self._is_exit[0] and self._enemies == 0:
                return True

        time.sleep(0.15 if self.boss.sensor.fa else 0)

        new_frame = self._sense()
        if not self.boss.ensure_movement:
            return True

        is_moved = self._is_moved(new_frame, d)

        if not is_moved and not disaster_recovered:
            self.boss.fix_blockage()
            return self.move(d, True)

        return is_moved

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
        time.sleep(2.5)
        self.moves += 1
        self.last_combat = self.moves
        return False

    def _count_enemies(self, frame830x690: cv2.typing.MatLike | None = None) -> int:
        return self.boss.count_enemies(
            extract_game(self.get_frame()) if frame830x690 is None else frame830x690
        )

    def can_move(self, d: Direction) -> bool:
        return self._direction_dict.get(d, False)

    def get_frame(self) -> cv2.typing.MatLike:
        return self.controller.device.get_frame2()

    def _get_frame_fa(self) -> cv2.typing.MatLike:
        if self.boss.sensor.fa:
            self.controller.click(self.controller.skill_1_point)
            time.sleep(0.1)

        frame = self.get_frame()

        if self.boss.sensor.fa:
            self.controller.click(self.controller.skill_1_point_cancel)
            time.sleep(0.055)

        return frame

    def _open_dirs(self, frame):
        return self.boss.sensor.open_dirs(frame)

    def _sense(self) -> cv2.typing.MatLike:
        decoded = self._get_frame_fa()
        frame830x690 = extract_game(decoded)

        frame830x690hsv = cv2.cvtColor(frame830x690, cv2.COLOR_BGR2HSV)
        # detect exit
        self._is_exit = self.boss.is_near_exit(frame830x690hsv, frame830x690)
        # detect enemies
        self._enemies = self._count_enemies(frame830x690)
        if self._enemies > 0:
            self._clear_enemies(self.boss.use_slide)

        # detect possible directions
        self._direction_dict = self._open_dirs(decoded)

        # Check if all directions are zero
        if all(not v for v in self._direction_dict.values()):
            logger.debug(
                "Warning: All direction possibilities are zero. Sensing again..."
            )
            self.boss.fix_disaster()
            decoded = self._get_frame_fa()
            frame830x690 = extract_game(decoded)
            self._direction_dict = self._open_dirs(decoded)

        return decoded


if __name__ == "__main__":
    from boss import (
        BossDelingh,
        BossDain,
        BossElvira,
        BossMine,
        BossKhanel,
        BossBhalor,
        BossKrokust,
    )

    device = Device("127.0.0.1", 58526)
    device.connect()
    controller = Controller(device)
    boss = BossDelingh(controller, True)
    maze = MazeRH(controller, boss, True)
    boss.init_camera()
    boss.sensor.use_nogo = False
    boss.sensor.moves = 3
    time.sleep(0.2)

    # boss.start_fight(Direction.SW)
    # raise
    # # TEST is_near_exit
    while 1:
        maze._sense()
        # frame830x690 = extract_game(maze.get_frame())
        # frame830x690hsv = cv2.cvtColor(frame830x690, cv2.COLOR_BGR2HSV)
        # res, _ = boss.is_near_exit(frame830x690hsv, frame830x690)
        # _enemies = maze._count_enemies(frame830x690hsv, frame830x690)
        # print(res, _, _enemies)

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
