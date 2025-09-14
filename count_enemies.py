import cv2 as cv
import numpy as np


def count_enemies(hsv: cv.typing.MatLike, show_debug=False) -> int:
    # 2) Красная маска в HSV (две «красные» дуги на круге оттенков)
    # насыщенный яркий красный
    lower1 = np.array([0, 120, 120])
    upper1 = np.array([10, 255, 255])
    lower2 = np.array([170, 120, 120])
    upper2 = np.array([180, 255, 255])
    mask = cv.inRange(hsv, lower1, upper1) | cv.inRange(hsv, lower2, upper2)

    # 4) Находим контуры и фильтруем по «узкая горизонтальная плашка»
    cnts, _ = cv.findContours(mask, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)

    # Пороговые размеры
    min_h = 5
    max_h = 8
    min_w = 60
    max_w = 70

    candidates = []
    for c in cnts:
        x, y, w, h = cv.boundingRect(c)
        if h < min_h or h > max_h:
            continue
        if w < min_w or w > max_w:
            continue
        if w / max(h, 1) < 6.0:  # вытянутость по горизонтали
            continue
        area = cv.contourArea(c)
        if area / (w * h) < 0.5:  # отсекаем «рваные» и рамки
            continue

        # Уточнение ориентации: почти горизонтально
        rect = cv.minAreaRect(c)
        angle = rect[-1]
        angle = angle if angle <= 45 else angle - 90
        if abs(angle) > 12:  # явные вертикали (факел, огонь) отсекаем
            continue

        candidates.append((x, y, w, h))

    if show_debug:
        cv.putText(
            mask,
            f"ememies: {len(candidates)}",
            (10, 10),
            cv.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1,
            cv.LINE_AA,
        )
        cv.imshow("count_enemies/DBG", mask)
        cv.waitKey(1)

    return len(candidates)
