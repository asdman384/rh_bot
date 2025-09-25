import logging

import cv2
import numpy as np

from db import NE_RECT, NW_RECT, SE_RECT, SW_RECT
from model import Direction
from sensing.utils import check_rect, draw_rect

logger = logging.getLogger(__name__)


_blue_mask = None


def find_blue_mask(bgr, mask_colors, debug=False):
    global _blue_mask
    """Возвращает маску синих коридоров (uint8 0/255)."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, mask_colors["l1"], mask_colors["u1"])
    # Убираем шум, заполняем дырки
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

    if _blue_mask is not None:
        _blue_mask = cv2.bitwise_or(_blue_mask, mask)
    else:
        _blue_mask = mask
        print("Initialized _blue_mask")

    if debug:
        cv2.imshow("_blue_mask", _blue_mask)
        cv2.waitKey(1)

    return _blue_mask


def find_pale_pink_center(bgr, blue_mask, mask_colors, debug=False):
    # ограничиваем поиск по зоне коридоров
    masked = cv2.bitwise_and(bgr, bgr, mask=blue_mask)

    # эталонный бледно-розовый (подтюньте под вашу картинку)
    sample_bgr = np.uint8(
        [[[mask_colors["bgr"][0], mask_colors["bgr"][1], mask_colors["bgr"][2]]]]
    )  # B,G,R пример
    sample_lab = cv2.cvtColor(sample_bgr, cv2.COLOR_BGR2LAB)[0, 0].astype(np.int16)
    lab = cv2.cvtColor(masked, cv2.COLOR_BGR2LAB).astype(np.int16)
    dist = np.sqrt(np.sum((lab - sample_lab) ** 2, axis=2)).astype(np.uint8)

    # инвертируем расстояние в маску похожести (меньше = ближе к эталону)
    _, pink_mask = cv2.threshold(dist, 25, 255, cv2.THRESH_BINARY_INV)
    gray = cv2.cvtColor(masked, cv2.COLOR_BGR2GRAY)
    _, bright = cv2.threshold(gray, 80, 255, cv2.THRESH_BINARY)
    pink_mask = cv2.bitwise_and(pink_mask, bright)

    # убираем шум (стрелка входа)
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
        minRadius=4,
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


_minimap_open_dirs2_initiation = True


def minimap_open_dirs2(bgr: cv2.typing.MatLike, masks, threshold, debug=False):
    global _prev_p_xy
    global _minimap_open_dirs2_initiation
    blue_mask = find_blue_mask(bgr, masks["path"], debug)
    res = find_pale_pink_center(bgr, blue_mask, masks["player"], debug)

    if _minimap_open_dirs2_initiation:
        white_pixels = np.column_stack(np.where(blue_mask == 255))
        y, x = white_pixels[np.argmin(white_pixels[:, 0])]
        logger.debug(f"Initial topmost white pixel coordinates: {(x + 13, y + 33)}")
        _minimap_open_dirs2_initiation = False
        p_xy = (x + 17, y + 37)
    else:
        p_xy = (res[0], res[1]) if res is not None else None

    offset = {"NE": (5, -10), "NW": (-12, -10), "SW": (-12, 2), "SE": (4, 2)}

    ne = 0
    nw = 0
    se = 0
    sw = 0

    if p_xy is None and _prev_p_xy is not None:
        p_xy = _prev_p_xy

    if p_xy is not None:
        ne = check_rect(blue_mask, p_xy, _prev_p_xy, offset["NE"], NE_RECT)
        nw = check_rect(blue_mask, p_xy, _prev_p_xy, offset["NW"], NW_RECT)
        se = check_rect(blue_mask, p_xy, _prev_p_xy, offset["SE"], SE_RECT)
        sw = check_rect(blue_mask, p_xy, _prev_p_xy, offset["SW"], SW_RECT)
        cv2.circle(bgr, p_xy, 1, (255, 255, 255), 1)

    if p_xy is not None:
        _prev_p_xy = p_xy

    if debug:
        draw_rect(
            bgr,
            p_xy,
            _prev_p_xy,
            offset["NE"],
            NE_RECT,
            (0, 255, 0) if ne > threshold["ne"] else (0, 0, 255),
        )
        draw_rect(
            bgr,
            p_xy,
            _prev_p_xy,
            offset["SW"],
            SW_RECT,
            (0, 255, 0) if sw > threshold["sw"] else (0, 0, 255),
        )
        draw_rect(
            bgr,
            p_xy,
            _prev_p_xy,
            offset["NW"],
            NW_RECT,
            (0, 255, 0) if nw > threshold["nw"] else (0, 0, 255),
        )
        draw_rect(
            bgr,
            p_xy,
            _prev_p_xy,
            offset["SE"],
            SE_RECT,
            (0, 255, 0) if se > threshold["se"] else (0, 0, 255),
        )
        cv2.putText(
            bgr,
            f"ne={ne:.1f} nw={nw:.1f} se={se:.1f} sw={sw:.1f}",
            (10, 20),
            0,
            0.6,
            (255, 255, 255),
            1,
        )
        cv2.imshow("minimap/frame", bgr)
        cv2.waitKey(1)

    return {
        Direction.NE.label: ne > threshold["ne"],
        Direction.NW.label: nw > threshold["nw"],
        Direction.SE.label: se > threshold["se"],
        Direction.SW.label: sw > threshold["sw"],
    }


if __name__ == "__main__":
    from boss import BossDain, BossDelingh
    from controller import Controller
    from devices.device import Device
    from frames import extract_game
    from maze_rh import MazeRH

    device = Device("127.0.0.1", 58526)
    device.connect()
    controller = Controller(device)
    boss = BossDain(controller, True)
    maze = MazeRH(controller, boss, True)

    while 1:
        # maze.sense()
        frame830x690 = extract_game(maze.get_frame())
        frame830x690hsv = cv2.cvtColor(frame830x690, cv2.COLOR_BGR2HSV)
        res, _ = boss.is_near_exit(frame830x690hsv, frame830x690)
        print(res, _)
