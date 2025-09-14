import cv2
import numpy as np
import math

from devices.device import Device
from maze_rh import MazeRH


# ---------- 1) Маски: стены и игрок ----------
def _build_masks(
    frame_bgr,
    red_dom_delta=25,
    pink_hsv_lo1=(0, 5, 130),  # H,S,V   — мягкие пороги для бледно-розового
    pink_hsv_hi1=(20, 220, 255),
    pink_hsv_lo2=(160, 5, 130),
    pink_hsv_hi2=(180, 220, 255),
    lab_a_min=135,
):
    """
    Возвращает:
      mask_walls (uint8 0/255), mask_player (uint8 0/255), center (x,y) или None
    """
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    lab = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2LAB)

    # --- стены: "R-доминантные" пиксели (красные линии по всей карте)
    B, G, R = cv2.split(frame_bgr)
    red_dom = (R.astype(np.int16) - np.maximum(B, G).astype(np.int16)) > 50
    dom_mask_wals = np.zeros(R.shape, np.uint8)
    dom_mask_wals[red_dom] = 255
    dom_mask_wals = cv2.morphologyEx(
        dom_mask_wals, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8), iterations=1
    )

    # Создание масок для каждого диапазона и их объединение.
    mask1 = cv2.inRange(hsv, np.array([0, 100, 80]), np.array([20, 255, 255]))
    mask2 = cv2.inRange(hsv, np.array([165, 100, 80]), np.array([180, 255, 255]))
    range_mask_walls = cv2.bitwise_or(mask1, mask2)

    final_mask_walls = cv2.bitwise_or(dom_mask_wals, range_mask_walls)
    cv2.imshow("final_mask_walls", final_mask_walls)

    # --- игрок: бледно-розовый (низкая/средняя насыщенность + высокий 'a' в Lab)

    m1 = cv2.inRange(
        hsv, np.array(pink_hsv_lo1, np.uint8), np.array(pink_hsv_hi1, np.uint8)
    )
    m2 = cv2.inRange(
        hsv, np.array(pink_hsv_lo2, np.uint8), np.array(pink_hsv_hi2, np.uint8)
    )
    mask_pink_hsv = cv2.bitwise_or(m1, m2)
    mask_a = cv2.inRange(lab[:, :, 1], lab_a_min, 255)
    mask_player = cv2.bitwise_and(mask_pink_hsv, mask_a)

    # Убираем тонкие линии (стены) и склеиваем пятно игрока
    mask_player = cv2.morphologyEx(
        mask_player, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8), iterations=1
    )
    mask_player = cv2.morphologyEx(
        mask_player, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8), iterations=1
    )

    # --- центр игрока
    cnts, _ = cv2.findContours(mask_player, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    center = None
    if cnts:
        # берём наиболее «круглый» крупный контур
        for cnt in sorted(cnts, key=cv2.contourArea, reverse=True)[:5]:
            area = cv2.contourArea(cnt)
            if area < 8:
                continue
            peri = cv2.arcLength(cnt, True) or 1.0
            circularity = 4 * math.pi * area / (peri * peri)
            if circularity < 0.3:  # отсечь линию/блик
                continue
            M = cv2.moments(cnt)
            if M["m00"]:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                center = (cx, cy)
                break

    # чтобы «луч» не упирался в сам значок игрока — вычтем его из маски стен
    if center is not None and np.any(mask_player):
        dil = cv2.dilate(mask_player, np.ones((9, 9), np.uint8), iterations=1)
        final_mask_walls = cv2.bitwise_and(final_mask_walls, cv2.bitwise_not(dil))

    return final_mask_walls, mask_player, center


# ---------- 2) Простой рейкаст до первой стены ----------
def _first_hit_distance(
    mask_binary, start_xy, angle_deg, max_len=None, ignore_radius=8
):
    """
    mask_binary: uint8 (0/255), стены=255
    start_xy: (x, y) центра игрока
    Возвращает длину в пикселях до первого пикселя стены вдоль луча под углом angle_deg,
    либо None, если вышли за кадр не встретив стену.
    """
    h, w = mask_binary.shape[:2]
    if max_len is None:
        max_len = int(math.hypot(w, h)) + 5

    x, y = float(start_xy[0]), float(start_xy[1])
    dx = math.cos(math.radians(angle_deg))
    dy = math.sin(
        math.radians(angle_deg)
    )  # В OpenCV вниз = +Y, поэтому знак естественный

    ir2 = ignore_radius * ignore_radius
    for _ in range(1, max_len + 1):
        x += dx
        y += dy
        xi, yi = int(round(x)), int(round(y))
        if xi < 0 or yi < 0 or xi >= w or yi >= h:
            return None
        # пропускаем окрестность игрока
        if (xi - start_xy[0]) ** 2 + (yi - start_xy[1]) ** 2 <= ir2:
            continue
        if mask_binary[yi, xi] != 0:
            return math.hypot(x - start_xy[0], y - start_xy[1])
    return None


# ---------- 3) Основная функция ----------
def measure_diagonal_distances(frame_bgr, return_masks=False, ignore_radius=8):
    """
    frame_bgr: цветной BGR кадр (numpy)
    Возвращает словарь расстояний до стен в пикселях:
      {'NE': float|None, 'SE': float|None, 'SW': float|None, 'NW': float|None,
       'center': (x,y) or None}
    Если return_masks=True, дополнительно вернёт (mask_walls, mask_player).
    """
    mask_walls, mask_player, center = _build_masks(frame_bgr, red_dom_delta=25)

    result = {"NE": None, "SE": None, "SW": None, "NW": None, "center": center}
    if center is None:
        return (result, mask_walls, mask_player) if return_masks else result

    # Ось NE–SW под 35°, ось NW–SE под 145°.
    # В координатах изображения (x вправо, y вниз):
    ANG = 35.0
    angles = {
        "NE": -ANG,  # вправо-вверх
        "SE": +ANG,  # вправо-вниз
        "SW": 180.0 - ANG,  # влево-вниз
        "NW": 180.0 + ANG,  # влево-вверх
    }

    for k, a in angles.items():
        result[k] = _first_hit_distance(
            mask_walls, center, a, ignore_radius=ignore_radius
        )

    return (result, mask_walls, mask_player) if return_masks else result


def extract_minimap(frame: cv2.typing.MatLike) -> cv2.typing.MatLike:
    X = 50
    Y = 110
    W = 250
    H = 200
    return cv2.resize(frame[Y : Y + H, X : X + W], (W, H))


if __name__ == "__main__":
    device = Device("127.0.0.1", 58526)
    device.connect()
    maze = MazeRH(device, True)

    while 1:
        mini_map = extract_minimap(maze.get_frame())
        result = measure_diagonal_distances(mini_map)
        print(result)
        cv2.waitKey(111)
