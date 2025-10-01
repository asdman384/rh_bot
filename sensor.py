from abc import ABC, abstractmethod
import math
import cv2
import numpy as np
from db import NE_RECT, NW_RECT, SE_RECT, SW_RECT
from frames import extract_game
from model import Direction


# cv2.imwrite("minimap24.png", maze.get_frame())
# frame = maze.get_frame()
# # TEST is_near_exit

## Define a set where the key is a tuple (x, y)
# visited_points = set()
# def mouse_callback(event, x_, y_, flags, param):
#     global visited_points
#     if event != cv2.EVENT_LBUTTONDOWN:
#         return
#     x, y = x_, y_
#     visited_points.add((x, y))
#     print(f"x={x_}, y={y_}")


class Sensor(ABC):
    def __init__(self, frame, mask_colors, thresholds=None, debug=False) -> None:
        self.first_open_dirs_call = True
        self.mask_colors = mask_colors
        self.debug = debug
        self._blue_mask = None
        self.last_move_dir = Direction.SE
        self.thresholds = thresholds
        self.steps = 1
        self.fa = False
        self.moves = 0

    def move(self, dir: Direction) -> tuple[float, float]:
        self.last_move_dir = dir
        self.moves += 1
        return 0.0, 0.0

    @abstractmethod
    def open_dirs(self, frame: cv2.typing.MatLike) -> dict:
        return {
            Direction.NE: False,
            Direction.NW: False,
            Direction.SE: False,
            Direction.SW: False,
        }

    def extract_minimap(self, frame: cv2.typing.MatLike) -> cv2.typing.MatLike:
        X = 0
        Y = 100
        W = 350
        H = 300
        return cv2.resize(frame[Y : Y + H, X : X + W], (W, H))

    def find_blue_mask(self, hsv, mask_colors):
        """Возвращает маску синих коридоров (uint8 0/255)."""
        mask = cv2.inRange(hsv, mask_colors["l1"], mask_colors["u1"])
        # Убираем шум, заполняем дырки
        # create a custom diamond-shaped kernel
        kernel = np.array(
            [
                [0, 0, 0, 0, 1, 0, 0, 0, 0],
                [0, 0, 1, 1, 1, 1, 1, 0, 0],
                [0, 1, 1, 1, 1, 1, 1, 1, 0],
                [1, 1, 1, 1, 1, 1, 1, 1, 1],
                [0, 1, 1, 1, 1, 1, 1, 1, 0],
                [0, 0, 1, 1, 1, 1, 1, 0, 0],
                [0, 0, 0, 0, 1, 0, 0, 0, 0],
            ],
            dtype=np.uint8,
        )
        # kernel = cv2.getStructuringElement(cv2.MORPH_DIAMOND, (7, 7))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

        if self._blue_mask is not None:
            self._blue_mask = cv2.bitwise_or(self._blue_mask, mask)
        else:
            self._blue_mask = mask

        return self._blue_mask


class MinimapSensor2(Sensor):
    max_len = 20
    step = 3.33

    dirs_angle = {
        Direction.SE: 35.5,
        Direction.SW: 144.5,
        Direction.NW: 215.5,
        Direction.NE: 324.5,
    }

    def find_pale_pink_center(self, bgr, blue_mask, debug=False):
        # ограничиваем поиск по зоне коридоров
        masked = cv2.bitwise_and(bgr, bgr, mask=blue_mask)

        # эталонный бледно-розовый (подтюньте под вашу картинку)
        sample_bgr = np.uint8([[[132, 113, 148]]])  # B,G,R пример
        sample_lab = cv2.cvtColor(sample_bgr, cv2.COLOR_BGR2LAB)[0, 0].astype(np.int16)

        lab = cv2.cvtColor(masked, cv2.COLOR_BGR2LAB).astype(np.int16)
        dist = np.sqrt(np.sum((lab - sample_lab) ** 2, axis=2)).astype(np.uint8)

        # инвертируем расстояние в маску похожести (меньше = ближе к эталону)
        _, pink_mask = cv2.threshold(dist, 25, 255, cv2.THRESH_BINARY_INV)
        gray = cv2.cvtColor(masked, cv2.COLOR_BGR2GRAY)
        _, bright = cv2.threshold(gray, 80, 255, cv2.THRESH_BINARY)
        pink_mask = cv2.bitwise_and(pink_mask, bright)

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        pink_mask = cv2.morphologyEx(pink_mask, cv2.MORPH_OPEN, kernel, iterations=1)
        pink_mask = cv2.morphologyEx(pink_mask, cv2.MORPH_CLOSE, kernel, iterations=2)

        if debug:
            cv2.imshow("masked", masked)
            cv2.imshow("pink_mask", pink_mask)
            cv2.waitKey(1)

        # Попытка Hough на области с pink_mask
        masked_for_hough = cv2.bitwise_and(
            cv2.cvtColor(masked, cv2.COLOR_BGR2GRAY), pink_mask
        )
        blurred = cv2.GaussianBlur(masked_for_hough, (7, 7), 1.5)

        circles = cv2.HoughCircles(
            blurred,
            cv2.HOUGH_GRADIENT,
            dp=1.2,
            minDist=10,
            param1=50,
            param2=18,
            minRadius=6,
            maxRadius=80,
        )
        if circles is not None:
            circles = np.round(circles[0, :]).astype("int")
            best = None
            best_score = -1
            h, w = pink_mask.shape[:2]
            for x, y, r in circles:
                # создаём булеву маску круга той же формы, что и изображение
                yy, xx = np.ogrid[-y : h - y, -x : w - x]
                circle_mask = (xx * xx + yy * yy) <= r * r
                circle_mask_u8 = circle_mask.astype(np.uint8) * 255
                inter = cv2.bitwise_and(pink_mask, pink_mask, mask=circle_mask_u8)
                score = cv2.countNonZero(inter)
                if score > best_score:
                    best_score = score
                    best = (x, y, r)
            if best is not None and best_score > 10:
                return best

        # fallback: контуры
        contours, _ = cv2.findContours(
            pink_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        if not contours:
            return None
        contours = sorted(contours, key=cv2.contourArea, reverse=True)
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 20:
                continue
            (x, y), r = cv2.minEnclosingCircle(cnt)
            circ_area = np.pi * (r**2)
            if circ_area <= 0:
                continue
            fill_ratio = area / circ_area
            if fill_ratio > 0.25 and r >= 4:
                return (int(x), int(y), int(r))
        return None

    def __init__(self, frame, mask_colors, thresholds=None, debug=False):
        super().__init__(frame, mask_colors, thresholds, debug)

        minimap = self.extract_minimap(frame)
        hsv = cv2.cvtColor(minimap, cv2.COLOR_BGR2HSV)
        blue_mask = self.find_blue_mask(hsv, self.mask_colors["path"])
        h, w = blue_mask.shape[:2]
        white_pixels = np.column_stack(np.where(blue_mask == 255))
        if white_pixels.size == 0:
            raise ValueError("No white pixels found in blue_mask.")

        y, x = white_pixels[np.argmin(white_pixels[:, 0])]
        self.current_xy = (x + 19, y + 33)
        self.max_xy = (w, h)
        if debug:
            cv2.circle(minimap, self.current_xy, 2, (0, 255, 255), 1)
            cv2.imshow("Sensor/start", minimap)
            cv2.waitKey(0)

    def _calibrate_initial_xy(self, blue_mask):
        print("Calibrating initial position...")
        ne_length = self.ray_len(
            blue_mask, *self.current_xy, self.dirs_angle[Direction.NE]
        )
        sw_length = self.ray_len(
            blue_mask, *self.current_xy, self.dirs_angle[Direction.SW]
        )
        diff = (ne_length - sw_length) / 2
        dx = diff * math.cos(math.radians(self.dirs_angle[Direction.NE]))
        dy = diff * math.sin(math.radians(self.dirs_angle[Direction.NE]))
        self.current_xy = (self.current_xy[0] + dx, self.current_xy[1] + dy)
        pass

    def move(self, dir: Direction) -> tuple[float, float]:
        dx = math.cos(math.radians(self.dirs_angle[dir])) * self.step
        dy = math.sin(math.radians(self.dirs_angle[dir])) * self.step
        self.current_xy = (self.current_xy[0] + dx, self.current_xy[1] + dy)
        self.moves += 1
        if self.moves == 2:
            self._calibrate_initial_xy(self._blue_mask)
        return self.current_xy

    def open_dirs(
        self,
        frame: cv2.typing.MatLike,
    ) -> dict:
        if self.first_open_dirs_call:
            self.first_open_dirs_call = False
            return {
                Direction.NW: False,
                Direction.SE: True,
                Direction.SW: False,
                Direction.NE: False,
            }

        lengths = {}
        minimap = self.extract_minimap(frame)
        hsv = cv2.cvtColor(minimap, cv2.COLOR_BGR2HSV)
        mask = self.find_blue_mask(hsv, self.mask_colors["path"])

        for dir in self.dirs_angle.keys():
            lengths[dir] = self._test_direction(
                mask, dir, minimap if self.debug else None
            )

        if self.debug:
            cv2.putText(
                minimap,
                f"se={lengths[Direction.SE][0]:.1f},{lengths[Direction.SE][1]:.1f}, sw={lengths[Direction.SW][0]:.1f},{lengths[Direction.SW][1]:.1f}, nw={lengths[Direction.NW][0]:.1f},{lengths[Direction.NW][1]:.1f}, ne={lengths[Direction.NE][0]:.1f},{lengths[Direction.NE][1]:.1f}",
                (10, 20),
                0,
                0.5,
                (255, 255, 255),
                1,
            )
            cv2.imshow("Sensor/open_dirs", minimap)
            cv2.waitKey(1)

        open_dirs = {}
        for dir in self.dirs_angle.keys():
            open_dirs[dir] = (8.1 < lengths[dir][0] <= 22) and (
                8.1 < lengths[dir][1] <= 22
            )

        print(
            f"se={lengths[Direction.SE][0]:.1f},{lengths[Direction.SE][1]:.1f}, sw={lengths[Direction.SW][0]:.1f},{lengths[Direction.SW][1]:.1f}, nw={lengths[Direction.NW][0]:.1f},{lengths[Direction.NW][1]:.1f}, ne={lengths[Direction.NE][0]:.1f},{lengths[Direction.NE][1]:.1f}",
        )
        print(open_dirs)
        # cv2.waitKey(0)
        return open_dirs

    def _test_direction(
        self,
        mask: cv2.typing.MatLike,
        dir: Direction,
        debug_minimap: cv2.typing.MatLike = None,
    ) -> tuple[float, float]:
        angle = self.dirs_angle[dir]  # degrees
        self.ray_len(mask, *self.current_xy, angle, debug_minimap)

        if dir == Direction.SE:
            left_angle = angle - 19
            right_angle = angle + 21
        elif dir == Direction.SW:
            left_angle = angle - 21
            right_angle = angle + 19
        elif dir == Direction.NW:
            left_angle = angle - 19
            right_angle = angle + 21
        elif dir == Direction.NE:
            left_angle = angle - 21
            right_angle = angle + 19

        left_length = self.ray_len(mask, *self.current_xy, left_angle, debug_minimap)
        right_length = self.ray_len(mask, *self.current_xy, right_angle, debug_minimap)

        return left_length, right_length

    def ray_len(
        self,
        mask: cv2.typing.MatLike,
        x: float,
        y: float,
        angle: float,
        debug_minimap: cv2.typing.MatLike = None,
    ) -> float:
        length = 0
        dx = math.cos(math.radians(angle))
        dy = math.sin(math.radians(angle))
        len_sealed = False
        for _ in range(1, self.max_len + 1):
            x += dx
            y += dy
            xi, yi = int(round(x)), int(round(y))
            if xi < 0 or yi < 0 or xi >= self.max_xy[0] or yi >= self.max_xy[1]:
                break
            if mask[yi, xi] == 255:
                length = (
                    math.hypot(x - self.current_xy[0], y - self.current_xy[1])
                    if not len_sealed
                    else length
                )
                if debug_minimap is not None:
                    debug_minimap[yi, xi] = (0, 255, 0)
            else:
                len_sealed = True
                if debug_minimap is not None:
                    debug_minimap[yi, xi] = (0, 0, 255)

        return length


class MinimapSensor(Sensor):
    def __init__(
        self,
        frame,
        mask_colors,
        thresholds=None,
        minimap=None,
        use_nogo=True,
        debug=False,
    ):
        super().__init__(frame, mask_colors, thresholds, debug)
        self._prev_p_xy = None
        self.steps = 2
        self.straight_corridor = True
        self.nogo = list()
        self.use_nogo = use_nogo

    def open_dirs(self, frame: cv2.typing.MatLike):
        minimap = self.extract_minimap(frame)
        hsv = cv2.cvtColor(minimap, cv2.COLOR_BGR2HSV)
        lab = self.find_blue_mask(hsv, self.mask_colors["path"])
        pm = self.player_mask(hsv, self.mask_colors["player"])
        p_xy = self.find_largest_contour_centroid(pm)

        if self.moves < 2:
            if self.use_nogo and p_xy is not None:
                self.nogo.append(
                    ((p_xy[0] - 6, p_xy[1] - 6), (p_xy[0] + 6, p_xy[1] + 6))
                )

            return {
                Direction.NW: False,
                Direction.SE: True,
                Direction.SW: False,
                Direction.NE: False,
            }

        offset = {"NE": (5, -10), "NW": (-12, -10), "SW": (-12, 2), "SE": (3, 1)}

        ne = 0
        nw = 0
        se = 0
        sw = 0

        if p_xy is None and self._prev_p_xy is not None:
            p_xy = self._prev_p_xy

        if p_xy is not None:
            ne = self.check_rect(lab, p_xy, self._prev_p_xy, offset["NE"], NE_RECT)
            nw = self.check_rect(lab, p_xy, self._prev_p_xy, offset["NW"], NW_RECT)
            se = self.check_rect(lab, p_xy, self._prev_p_xy, offset["SE"], SE_RECT)
            sw = self.check_rect(lab, p_xy, self._prev_p_xy, offset["SW"], SW_RECT)

        result = {
            Direction.NE: ne > self.thresholds["ne"],
            Direction.NW: nw > self.thresholds["nw"],
            Direction.SE: se > self.thresholds["se"],
            Direction.SW: sw > self.thresholds["sw"],
        }

        if self.use_nogo:
            if self.straight_corridor:
                self.straight_corridor = list(result.values()).count(True) <= 2
                if self.straight_corridor and p_xy is not None:
                    self.nogo.append(
                        ((p_xy[0] - 4, p_xy[1] - 4), (p_xy[0] + 4, p_xy[1] + 4))
                    )

        if p_xy is not None:
            self._prev_p_xy = p_xy

        if self.use_nogo:
            nogo_match = False
            if not self.straight_corridor:
                for (x1, y1), (x2, y2) in self.nogo:
                    if x1 <= p_xy[0] <= x2 and y1 <= p_xy[1] <= y2:
                        nogo_match = True
                        break

                if nogo_match:
                    for d in result.keys():
                        result[d] = False
                    result[self.last_move_dir.opposite] = True

        if self.debug:
            cv2.circle(minimap, p_xy, 1, (255, 255, 255), 1)
            if self.use_nogo:
                for ng in self.nogo:
                    cv2.rectangle(minimap, ng[0], ng[1], (0, 0, 255), 1)

                if nogo_match:
                    cv2.putText(
                        minimap,
                        "NOGO",
                        (10, 50),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        1,
                        (0, 0, 255),
                        2,
                    )

            self.draw_rect(
                minimap,
                p_xy,
                self._prev_p_xy,
                offset["NE"],
                NE_RECT,
                (0, 255, 0) if ne > self.thresholds["ne"] else (0, 0, 255),
            )
            self.draw_rect(
                minimap,
                p_xy,
                self._prev_p_xy,
                offset["SW"],
                SW_RECT,
                (0, 255, 0) if sw > self.thresholds["sw"] else (0, 0, 255),
            )
            self.draw_rect(
                minimap,
                p_xy,
                self._prev_p_xy,
                offset["NW"],
                NW_RECT,
                (0, 255, 0) if nw > self.thresholds["nw"] else (0, 0, 255),
            )
            self.draw_rect(
                minimap,
                p_xy,
                self._prev_p_xy,
                offset["SE"],
                SE_RECT,
                (0, 255, 0) if se > self.thresholds["se"] else (0, 0, 255),
            )
            cv2.putText(
                minimap,
                f"ne={ne:.1f} nw={nw:.1f} se={se:.1f} sw={sw:.1f}",
                (10, 20),
                0,
                0.5,
                (255, 255, 255),
                1,
            )

            debug = np.hstack(
                (
                    minimap,
                    cv2.cvtColor(lab, cv2.COLOR_GRAY2BGR),
                    cv2.cvtColor(pm, cv2.COLOR_GRAY2BGR),
                )
            )
            cv2.imshow("open_dirs/debug", debug)
            cv2.waitKey(1)

        return result

    def player_mask(self, hsv: cv2.typing.MatLike, masks) -> cv2.typing.MatLike:
        pm1 = cv2.inRange(hsv, masks["l1"], masks["u1"])
        pm2 = cv2.inRange(hsv, masks["l2"], masks["u2"])
        pm = cv2.bitwise_or(pm1, pm2)

        # Чистим от шумов
        # kernel = np.ones((3, 3), np.uint8)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        # pm = cv2.morphologyEx(pm, cv2.MORPH_OPEN, kernel, iterations=1)
        pm = cv2.morphologyEx(pm, cv2.MORPH_CLOSE, kernel, iterations=1)
        pm = cv2.dilate(pm, np.ones((3, 3), np.uint8), iterations=1)

        return pm

    def find_largest_contour_centroid(self, mask):
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

    def draw_rect(self, frame, p_xy, prev_p_xy, offset, rect, color=(255, 255, 255)):
        for x, y in rect:
            if prev_p_xy is not None:
                p_xy = (
                    prev_p_xy[0] if abs(prev_p_xy[0] - p_xy[0]) > 10 else p_xy[0],
                    prev_p_xy[1] if abs(prev_p_xy[1] - p_xy[1]) > 10 else p_xy[1],
                )

            rect_x = x + p_xy[0] + offset[0]
            rect_y = y + p_xy[1] + offset[1]

            if rect_y >= 300 or rect_x >= 350:
                continue

            frame[rect_y, rect_x] = color

    def check_rect(self, frame, p_xy, prev_p_xy, offset, rect) -> float:
        white_count = 0
        for x, y in rect:
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

        return white_count / len(rect) * 100


class FaSensor(Sensor):
    dir_cells = None

    def __init__(self, frame, mask_colors, thresholds=None, debug=False):
        super().__init__(frame, mask_colors, thresholds, debug)
        self.steps = 3
        self.fa = True

    def open_dirs(self, frame):
        bgr_img = extract_game(frame)

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

        ne = self.direction_possibility(self.dir_cells["NE_RECT"], mask)
        se = self.direction_possibility(self.dir_cells["SE_RECT"], mask)
        sw = self.direction_possibility(self.dir_cells["SW_RECT"], mask)
        nw = self.direction_possibility(self.dir_cells["NW_RECT"], mask)

        if self.debug:
            self.put_labels(mask, f"NE:{ne:.1f}", (220 + 250, 300))
            self.put_labels(mask, f"NW:{nw:.1f}", (10 + 250, 300))
            self.put_labels(mask, f"SE:{se:.1f}", (220 + 250, 170 + 265))
            self.put_labels(mask, f"SW:{sw:.1f}", (10 + 250, 170 + 265))
            cv2.imshow("get_open_dirs/DBG", mask)
            cv2.waitKey(1)

        return {
            Direction.NE: ne > self.thresholds["ne"],
            Direction.NW: nw > self.thresholds["nw"],
            Direction.SE: se > self.thresholds["se"],
            Direction.SW: sw > self.thresholds["sw"],
        }

    def direction_possibility(
        self, dir: np.ndarray[tuple[int, int]], mask: np.ndarray
    ) -> float:
        vals = mask[tuple(dir.T)]
        i = int((vals > 220).sum())
        return i / len(dir) * 100

    def put_labels(
        self, frame: cv2.typing.MatLike, text: str, p: cv2.typing.Point
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


if __name__ == "__main__":
    from controller import Controller
    from devices.device import Device

    device = Device("127.0.0.1", 58526)
    device.connect()
    controller = Controller(device)

    frame = device.get_frame2()
    sensor = MinimapSensor2(
        frame, {"path": {"l1": (85, 60, 40), "u1": (140, 255, 255)}}, debug=True
    )

    # while 1:
    #     frame = device.get_frame2()
    #     sensor.open_dirs(frame)
    #     cv2.waitKey(10)

    steps = 5
    while steps != 0:
        controller.move_SE()
        sensor.move(Direction.SE)

        frame = device.get_frame2()
        sensor.open_dirs(frame)

        cv2.waitKey(70)
        steps -= 1

    cv2.waitKey(0)

    steps = 12
    while steps != 0:
        controller.move_SW()
        sensor.move(Direction.SW)

        frame = device.get_frame2()
        sensor.open_dirs(frame)

        cv2.waitKey(70)
        steps -= 1

    cv2.waitKey(0)
    raise Exception("stop")

    steps = 26
    while steps != 0:
        controller.move_NE()
        sensor.move(Direction.NE)

        frame = device.get_frame2()
        sensor.open_dirs(frame)

        cv2.waitKey(70)
        steps -= 1

    cv2.waitKey(0)

    steps = 30
    while steps != 0:
        controller.move_SW()
        sensor.move(Direction.SW)

        frame = device.get_frame2()
        sensor.open_dirs(frame)

        cv2.waitKey(70)
        steps -= 1
    # steps = 41
    # while steps != 0:
    #     controller.move_NW()
    #     sensor.move(Direction.NW)

    #     frame = device.get_frame2()
    #     sensor.open_dirs(frame)

    #     cv2.waitKey(70)
    #     steps -= 1

    cv2.waitKey(0)
