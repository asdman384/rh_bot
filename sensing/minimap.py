import cv2
import numpy as np
from db import NE_RECT, NW_RECT, SE_RECT, SW_RECT
from model import Direction
from sensing.utils import check_rect, draw_rect


def player_mask(hsv: cv2.typing.MatLike, masks) -> cv2.typing.MatLike:
    pm1 = cv2.inRange(hsv, masks["l1"], masks["u1"])
    pm2 = cv2.inRange(hsv, masks["l2"], masks["u2"])
    pm = cv2.bitwise_or(pm1, pm2)

    # Чистим от шумов
    kernel = np.ones((3, 3), np.uint8)
    # pm = cv2.morphologyEx(pm, cv2.MORPH_OPEN, kernel, iterations=1)
    pm = cv2.morphologyEx(pm, cv2.MORPH_CLOSE, kernel, iterations=1)
    return pm


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


_prev_p_xy = None


def minimap_open_dirs(
    frame: cv2.typing.MatLike,
    masks,
    threshold,
    debug: bool = False,
):
    global _prev_p_xy
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    pm = player_mask(hsv, masks["player"])
    pm = cv2.dilate(pm, np.ones((5, 5), np.uint8), iterations=1)
    p_xy = find_largest_contour_centroid(pm)

    path_m = cv2.inRange(hsv, masks["path"]["l1"], masks["path"]["u1"])
    # "Утолщаем" маску с помощью морфологического расширения
    path_m = cv2.dilate(path_m, np.ones((3, 3), np.uint8), iterations=1)
    # wall_m1 = cv2.inRange(hsv, masks["wall"]["l1"], masks["wall"]["u1"])
    # wall_m2 = cv2.inRange(hsv, masks["wall"]["l2"], masks["wall"]["u2"])
    # lab = cv2.bitwise_or(path_m, cv2.bitwise_or(wall_m1, wall_m2))
    lab = cv2.bitwise_or(path_m, pm)

    offset = {"NE": (5, -10), "NW": (-12, -10), "SW": (-12, 2), "SE": (4, 2)}

    ne = 0
    nw = 0
    se = 0
    sw = 0

    if p_xy is None and _prev_p_xy is not None:
        p_xy = _prev_p_xy

    if p_xy is not None:
        ne = check_rect(lab, p_xy, _prev_p_xy, offset["NE"], NE_RECT)
        nw = check_rect(lab, p_xy, _prev_p_xy, offset["NW"], NW_RECT)
        se = check_rect(lab, p_xy, _prev_p_xy, offset["SE"], SE_RECT)
        sw = check_rect(lab, p_xy, _prev_p_xy, offset["SW"], SW_RECT)
        cv2.circle(frame, p_xy, 1, (255, 255, 255), 1)

    if p_xy is not None:
        _prev_p_xy = p_xy

    if debug:
        draw_rect(
            frame,
            p_xy,
            _prev_p_xy,
            offset["NE"],
            NE_RECT,
            (0, 255, 0) if ne > threshold["ne"] else (0, 0, 255),
        )
        draw_rect(
            frame,
            p_xy,
            _prev_p_xy,
            offset["SW"],
            SW_RECT,
            (0, 255, 0) if sw > threshold["sw"] else (0, 0, 255),
        )
        draw_rect(
            frame,
            p_xy,
            _prev_p_xy,
            offset["NW"],
            NW_RECT,
            (0, 255, 0) if nw > threshold["nw"] else (0, 0, 255),
        )
        draw_rect(
            frame,
            p_xy,
            _prev_p_xy,
            offset["SE"],
            SE_RECT,
            (0, 255, 0) if se > threshold["se"] else (0, 0, 255),
        )
        cv2.imshow("minimap/frame", frame)
        cv2.imshow("minimap/pm", pm)
        cv2.putText(
            lab,
            f"ne={ne:.1f} nw={nw:.1f} se={se:.1f} sw={sw:.1f}",
            (10, 20),
            0,
            0.6,
            (255, 255, 255),
            1,
        )
        cv2.imshow("minimap/lab", lab)
        cv2.waitKey(10)

    return {
        Direction.NE.label: ne > threshold["ne"],
        Direction.NW.label: nw > threshold["nw"],
        Direction.SE.label: se > threshold["se"],
        Direction.SW.label: sw > threshold["sw"],
    }
