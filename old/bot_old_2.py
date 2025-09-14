import time
import cv2
import numpy as np
from collections import deque

from Device import connect_device
from controller import Controller

"""
Реализация краткой идеи из requirements.md:
- Находим игрока (розовая точка) на миникарте (ROI фиксирован).
- Детектим тонкие красные линии стен (двойной диапазон HSV для красного).
- Двигаемся по правилу левой руки: держим стену слева и идём вперёд, пока не распознано всплывающее окно (выход).
- Управление устройством через Movement (тапы/свайпы по экранным координатам стика).

Заметки по калибровке:
- При необходимости подстройте HSV диапазоны для pink/red под свою игру/дисплей.
- Если миникарта масштабируется, оставьте ROI как есть (оно в относительных px исходного экрана). Если масштаб иной — подправьте константы ROI.
"""

DEBUG = True

# ---------------------- ADB & control ----------------------

device = connect_device()
m = Controller(device)

# ---------------------- Minimap ROI ------------------------
# Из исходного кода: ROI миникарты на полном скриншоте
MINIMAP_X = 15
MINIMAP_Y = 120
MINIMAP_W = 270 - 15
MINIMAP_H = 290 - 120

# Нормализованный размер (оставляем исходный обрезанный размер)
NORM_W, NORM_H = MINIMAP_W, MINIMAP_H

# ---------------------- HSV Ranges -------------------------
# Красные стены (red) — два диапазона из-за кругового тона
RED_LO_1 = np.array([0, 120, 120])
RED_HI_1 = np.array([10, 255, 255])
RED_LO_2 = np.array([165, 120, 120])
RED_HI_2 = np.array([185, 255, 255])

# Игрок (розовая/малиновая точка). Подберите под свою игру.
# Обычно розовый: H ~ 150–175, S/V высокие
PINK_LO = np.array([135, 55, 120])
PINK_HI = np.array([175, 255, 255])

# ---------------------- Headings ---------------------------
# 8 направлений (dx, dy) в координатах изображения (x вправо, y вниз)
HEADINGS = [
    (0, -1),  # N   # ↑
    (1, -1),  # NE  # ↗
    (1, 0),  # E    # →
    (1, 1),  # SE   # ↘
    (0, 1),  # S    # ↓
    (-1, 1),  # SW  # ↙
    (-1, 0),  # W   # ←
    (-1, -1),  # NW # ↖
]
HEADING_NAMES = [
    "N # ↑",
    "NE # ↗",
    "E # →",
    "SE # ↘",
    "S # ↓",
    "SW # ↙",
    "W # ←",
    "NW # ↖",
]

# Карта направления -> функция движения
MOVE_FN = {
    0: lambda k=1: m.move_up(k),
    1: lambda k=1: m.move_right_up(k),
    2: lambda k=1: m.move_right(k),
    3: lambda k=1: m.move_right_down(k),
    4: lambda k=1: m.move_down(k),
    5: lambda k=1: m.move_left_down(k),
    6: lambda k=1: m.move_left(k),
    7: lambda k=1: m.move_left_up(k),
}

# Сколько пикселей смотреть вперёд/в сторону для локальной оценки
AHEAD_DIST = 5
SIDE_DIST = 3

# Размер шага (в "клетках" для Movement) — подберите под длину коридора
MOVE_CELL = 1

# Храним текущее предпочтительное направление (начинаем на East)
heading_idx = 3

# Небольшая история для стабилизации центра игрока
player_history = deque(maxlen=5)

# ---------------------- Core functions ---------------------


def get_frame_from_device(device):
    """Скриншот с Android через ADB и конвертация в OpenCV (BGR)."""
    raw = device.shell("screencap -p", decode=False)
    img_array = np.frombuffer(raw, dtype=np.uint8)
    frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    return frame


def extract_minimap(frame):
    """Вырезает ROI миникарты и масштабирует до предсказуемого размера."""
    minimap = frame[
        MINIMAP_Y : MINIMAP_Y + MINIMAP_H, MINIMAP_X : MINIMAP_X + MINIMAP_W
    ]
    minimap = cv2.resize(minimap, (NORM_W, NORM_H), interpolation=cv2.INTER_NEAREST)
    return minimap


def bgr_to_hsv(img_bgr):
    return cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)


def mask_red(hsv):
    m1 = cv2.inRange(hsv, RED_LO_1, RED_HI_1)
    m2 = cv2.inRange(hsv, RED_LO_2, RED_HI_2)
    mask = cv2.bitwise_or(m1, m2)
    # Тонкие линии усилим морфологией (расширение → сужение)
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
    return mask


def mask_player(hsv):
    mask = cv2.inRange(hsv, PINK_LO, PINK_HI)
    # Чистим от шумов
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    # mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)

    return mask


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


def clamp_point(x, y, w, h):
    return max(0, min(x, w - 1)), max(0, min(y, h - 1))


def sample_mask(mask, x, y):
    h, w = mask.shape[:2]
    x, y = clamp_point(x, y, w, h)
    return mask[y, x] > 0


def rotate_left(idx):
    return (idx - 2) % len(HEADINGS)  # поворот на 90° влево (две позиции из 8)


def rotate_right(idx):
    return (idx + 2) % len(HEADINGS)


def back(idx):
    return (idx + 4) % len(HEADINGS)


def left_of(idx):
    # Вектор слева от направления (повернуть на 90° влево)
    return rotate_left(idx)


def choose_next_heading(player_xy, red_mask, current_idx):
    """
    Выбор направления с учётом, что в игре нет поворотов — просто 8 кнопок.
    Стратегия: среди всех 8 направлений выбираем то, где ВПЕРЕДИ свободно,
    а слева от выбранного направления — стена (маска красного). Это реализует
    правило левой руки без учёта необходимости "поворачивать".

    При равенстве кандидатур тянемся к текущему направлению (инерция),
    чтобы снизить дрожание. Если направлений со стеной слева нет, берём
    любое со свободным ходом. Если нигде не свободно — возвращаемся.
    """
    px, py = player_xy
    h, w = red_mask.shape[:2]

    def ahead_score(idx):
        """Сколько зондов вперёд (из 3) свободны от стены."""
        dx, dy = HEADINGS[idx]
        score = 0
        for k in (1, 2, 3):
            ax, ay = clamp_point(
                px + dx * AHEAD_DIST * k, py + dy * AHEAD_DIST * k, w, h
            )
            if sample_mask(red_mask, ax, ay):
                break  # упёрлись в стену
            score += 1
        return score  # 0..3

    def has_left_wall(idx):
        lidx = left_of(idx)
        ldx, ldy = HEADINGS[lidx]
        lx, ly = clamp_point(px + ldx * SIDE_DIST, py + ldy * SIDE_DIST, w, h)
        return sample_mask(red_mask, lx, ly)

    def ang_deviation(a, b):
        d = abs(a - b) % 8
        return min(d, 8 - d)

    # Оцениваем все 8 направлений
    candidates = []
    for idx in range(8):
        a_score = ahead_score(idx)
        l_wall = has_left_wall(idx)
        inertia = -ang_deviation(
            current_idx, idx
        )  # меньше девиация — лучше (ближе к 0)
        # Приоритет кортежом: (есть_левая_стена, дальность_вперёд, инерция)
        priority = (1 if l_wall else 0, a_score, inertia)
        candidates.append((priority, idx))

    # Сортируем по приоритету убыв.
    candidates.sort(reverse=True)

    # 1) Пытаемся выбрать с левой стеной и свободным ходом
    for p, idx in candidates:
        if p[0] == 1 and p[1] > 0:
            return idx

    # 2) Если левой стены нет, но есть свобода вперёд — берём лучший
    for p, idx in candidates:
        if p[1] > 0:
            return idx

    # 3) В безвыходной ситуации — назад
    return back(current_idx)


# ---------------------- Popup detection --------------------


def detect_exit_popup(full_frame):
    """
    Грубая эвристика всплывающего окна: большая светлая/сероватая область в центре.
    Подстройте ROI/порог под свою игру, если нужно.
    """
    h, w = full_frame.shape[:2]
    cx0, cy0 = int(w * 0.2), int(h * 0.2)
    cx1, cy1 = int(w * 0.8), int(h * 0.8)
    roi = full_frame[cy0:cy1, cx0:cx1]

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    # Низкая насыщенность, высокая яркость → белые/серые панели
    lo = np.array([0, 0, 180])
    hi = np.array([180, 60, 255])
    mask = cv2.inRange(hsv, lo, hi)
    ratio = mask.mean() / 255.0  # доля светлых пикселей
    if DEBUG:
        cv2.imshow("PopupMask", mask)
    return ratio > 0.35  # порог подстройте при необходимости


# ---------------------- Main loop --------------------------

try:
    while True:
        frame = get_frame_from_device(device)
        if frame is None:
            continue

        # if detect_exit_popup(frame):
        #     print("[INFO] Обнаружено окно выхода. Останавливаемся.")
        #     break

        minimap = extract_minimap(frame)
        hsv = bgr_to_hsv(minimap)
        red_mask = mask_red(hsv)
        player_mask = mask_player(hsv)
        player_xy = find_largest_contour_centroid(player_mask)

        if player_xy is None:
            # нет уверенного детекта игрока — пропускаем шаг
            if DEBUG:
                cv2.imshow("Minimap", minimap)
                cv2.imshow("RedMask", red_mask)
                cv2.imshow("PlayerMask", player_mask)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
            continue

        # Стабилизуем позицию усреднением
        player_history.append(player_xy)
        avg_px = int(np.mean([p[0] for p in player_history]))
        avg_py = int(np.mean([p[1] for p in player_history]))
        player_xy = (avg_px, avg_py)

        # Выбираем направление по правилу левой руки
        heading_idx = choose_next_heading(player_xy, red_mask, heading_idx)
        MOOOOOOVE_CELL = HEADING_NAMES[heading_idx]

        if DEBUG:
            dbg = minimap.copy()
            # Отладочная отрисовка
            cv2.circle(dbg, player_xy, 5, (0, 255, 255), -1)
            cv2.putText(
                dbg,
                HEADING_NAMES[heading_idx],
                (5, 12),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (255, 255, 255),
                1,
            )

            # Показ мест, где проверяем "слева стена"
            lidx = left_of(heading_idx)
            ldx, ldy = HEADINGS[lidx]
            lx, ly = clamp_point(
                player_xy[0] + ldx * SIDE_DIST,
                player_xy[1] + ldy * SIDE_DIST,
                NORM_W,
                NORM_H,
            )
            cv2.circle(dbg, (lx, ly), 3, (0, 0, 255), -1)

            # Показ точки вперёд
            dx, dy = HEADINGS[heading_idx]
            ax, ay = clamp_point(
                player_xy[0] + dx * AHEAD_DIST,
                player_xy[1] + dy * AHEAD_DIST,
                NORM_W,
                NORM_H,
            )
            cv2.circle(dbg, (ax, ay), 1, (0, 255, 0), -1)

            cv2.imshow("Minimap/DBG", dbg)
            cv2.imshow("RedMask", red_mask)
            cv2.imshow("PlayerMask", player_mask)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

        # Отправляем движение
        MOVE_FN[heading_idx](MOVE_CELL)

        time.sleep(0.1)  # Задержка для снижения нагрузки

finally:
    cv2.destroyAllWindows()
    device.close()
    print("Finished.")
