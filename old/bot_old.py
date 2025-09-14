# C:\Users\opiankov\AppData\Local\Android\Sdk\platform-tools
import cv2
import numpy as np

from devices.device import Device

# ==== DEBUG FLAG ====
DEBUG = True  # поставь False для безоконного режима

# ==== Порог для синей миникарты (маска области поиска) ====
# Синяя заливка на миникарте: подстрой при необходимости
LOWER_BLUE = np.array([95, 40, 40], dtype=np.uint8)
UPPER_BLUE = np.array([130, 255, 255], dtype=np.uint8)
# ==== Порог для розовой точки игрока (с учётом гуляния оттенка) ====
LOWER_PINK = np.array([5, 50, 140], dtype=np.uint8)
UPPER_PINK = np.array([177, 255, 255], dtype=np.uint8)

device = Device("127.0.0.1", 58526)
device.connect()


def extract_minimap(frame):
    """
    Вырезает ROI миникарты из кадра игры.
    frame: numpy-массив (BGR изображение)
    return: minimap (numpy-массив)
    """
    MINIMAP_X = 15
    MINIMAP_Y = 120
    MINIMAP_W = 270 - 15
    MINIMAP_H = 290 - 120
    minimap = frame[
        MINIMAP_Y : MINIMAP_Y + MINIMAP_H, MINIMAP_X : MINIMAP_X + MINIMAP_W
    ]

    # нормализуем размер (например до 256x256)
    minimap = cv2.resize(minimap, (MINIMAP_W, MINIMAP_H))
    return minimap


def detect_player(minimap):
    """
    Находит позицию игрока по розовой точке.
    Возвращает (x, y) в координатах minimap и маску, либо (None, маска) если не найдено.
    """
    hsv = cv2.cvtColor(minimap, cv2.COLOR_BGR2HSV)
    if DEBUG:
        cv2.imshow("Minimap HSV", hsv)

    mask = cv2.inRange(hsv, LOWER_PINK, UPPER_PINK)
    # if DEBUG:
    # cv2.imshow("Pink Mask (raw)", mask)

    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)

    # if DEBUG:
    #     cv2.imshow("Pink Mask (clean)", mask)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if contours:
        c = max(contours, key=cv2.contourArea)
        M = cv2.moments(c)
        if M["m00"] > 0:
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
            return (cx, cy), mask

    return None, mask


# =====================[ ПУНКТ 3: граф из открытой области ]=====================


def segment_open_area(minimap_bgr):
    """
    Сегментирует открытую область лабиринта по синей заливке на миникарте.
    Возвращает бинарную карту (uint8, {0,255}) где 255 = проходимая область.
    """
    hsv = cv2.cvtColor(minimap_bgr, cv2.COLOR_BGR2HSV)
    blue_mask = cv2.inRange(hsv, LOWER_BLUE, UPPER_BLUE)

    # Чистим маску: убираем одиночные шумы, закрываем небольшие дыры
    kernel = np.ones((3, 3), np.uint8)
    blue_mask = cv2.morphologyEx(blue_mask, cv2.MORPH_OPEN, kernel, iterations=1)
    blue_mask = cv2.morphologyEx(blue_mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    # Проходимая область — это «синие коридоры/комнаты»
    walkable = blue_mask.copy()
    # if DEBUG:
    #     cv2.imshow("Open Area (walkable)", walkable)
    return walkable


def skeletonize_binary(bin_img):
    """
    Морфологическое скелетирование бинарного изображения (Zhang-Suen-like через морфологию).
    На входе: uint8 {0,255}. На выходе: uint8 {0,255} — скелет.
    """
    # Приводим к {0,1} для удобства
    img = (bin_img > 0).astype(np.uint8)

    ske = np.zeros_like(img, dtype=np.uint8)
    element = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))

    done = False
    working = img.copy()
    while not done:
        eroded = cv2.erode(working, element)
        opened = cv2.morphologyEx(eroded, cv2.MORPH_OPEN, element)
        temp = cv2.subtract(eroded, opened)
        ske = cv2.bitwise_or(ske, temp)
        working = eroded.copy()
        if cv2.countNonZero(working) == 0:
            done = True

    ske = (ske * 255).astype(np.uint8)
    if DEBUG:
        cv2.imshow("Skeleton", ske)
    return ske


def _neighbors8(img, y, x):
    """
    Возвращает список 8-соседей пикселя (y,x), которые равны 255 на скелете.
    """
    h, w = img.shape
    neigh = []
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and img[ny, nx] > 0:
                neigh.append((ny, nx))
    return neigh


def extract_graph_from_skeleton(skel):
    """
    Извлекает граф из скелета:
      - узлы: конечные точки (степень==1) и перекрестки (степень>=3)
      - рёбра: пути по пикселям скелета между узлами; длина = число пикселей (или евклид. длина)
    Возвращает:
      nodes: dict[node_id] = (x, y, type_str)
      edges: list[(u, v, length)]
    """
    # Найдем узлы
    h, w = skel.shape
    node_map = -np.ones((h, w), dtype=np.int32)  # для быстрых поисков id по координате
    nodes = {}
    next_id = 0

    ys, xs = np.where(skel > 0)
    for y, x in zip(ys, xs):
        deg = len(_neighbors8(skel, y, x))
        if deg == 1 or deg >= 3:
            node_map[y, x] = next_id
            ntype = "end" if deg == 1 else "junction"
            nodes[next_id] = (x, y, ntype)
            next_id += 1

    # Обход рёбер: из каждого узла идём по пикселям до следующего узла
    visited_edges = set()
    edges = []

    def walk_edge(start_y, start_x, prev_y, prev_x):
        """
        Идём по скелету, пока не встретим узел или тупик.
        Возвращает конечную координату (y,x), длину пути и список пикселей.
        """
        length = 0
        path = [(start_y, start_x)]
        cy, cx = start_y, start_x
        py, px = prev_y, prev_x  # откуда пришли

        while True:
            neigh = _neighbors8(skel, cy, cx)
            # Убираем обратный шаг
            if (py, px) in neigh:
                neigh.remove((py, px))

            # Если текущий пиксель — узел (и не старт), завершаем
            if node_map[cy, cx] >= 0 and (cy, cx) != (start_y, start_x):
                return (cy, cx), length, path

            if len(neigh) == 0:
                # тупик (не узел) — тоже завершаем
                return (cy, cx), length, path
            if len(neigh) > 1:
                # Развилка — это должен быть узел, но если не размечен, завершаем здесь
                return (cy, cx), length, path

            ny, nx = neigh[0]
            length += np.hypot(ny - cy, nx - cx)  # евклидова длина
            py, px = cy, cx
            cy, cx = ny, nx
            path.append((cy, cx))

    # Стартуем обход от узлов
    for nid, (x, y, _) in nodes.items():
        neigh = _neighbors8(skel, y, x)
        for ny, nx in neigh:
            # Каждое ребро идёт от узла к следующему узлу вдоль скелета
            end_coord, length, path = walk_edge(ny, nx, y, x)
            ey, ex = end_coord

            # Конечная точка должна быть узлом
            end_id = node_map[ey, ex] if 0 <= ey < h and 0 <= ex < w else -1
            if end_id >= 0 and end_id != nid:
                # Сделаем ключ, чтобы не дублировать рёбра (u,v) и (v,u)
                key = tuple(sorted((nid, end_id)))
                if key in visited_edges:
                    continue
                visited_edges.add(key)
                edges.append((nid, end_id, float(length)))

    return nodes, edges


def draw_graph_debug(minimap_bgr, nodes, edges):
    """
    Рисует узлы и рёбра графа на копии миникарты для отладки.
    """
    vis = minimap_bgr.copy()
    # Рёбра
    for u, v, _ in edges:
        x1, y1, _ = nodes[u]
        x2, y2, _ = nodes[v]
        cv2.line(vis, (x1, y1), (x2, y2), (0, 255, 255), 1, cv2.LINE_AA)
    # Узлы
    for nid, (x, y, ntype) in nodes.items():
        color = (0, 0, 255) if ntype == "junction" else (0, 255, 0)
        cv2.circle(vis, (x, y), 3, color, -1)
    return vis


# =====================[ MAIN LOOP ]=====================

while True:
    frame = device.get_frame2()
    minimap = extract_minimap(frame)
    player_pos, pink_mask = detect_player(minimap)

    # --- П.3: граф из открытой области ---
    open_area = segment_open_area(minimap)
    skeleton = skeletonize_binary(open_area)
    nodes, edges = extract_graph_from_skeleton(skeleton)

    # Визуализация
    vis = minimap.copy()
    if player_pos:
        cv2.circle(vis, player_pos, 5, (0, 255, 0), -1)  # помечаем игрока
    graph_dbg = draw_graph_debug(vis, nodes, edges)

    if DEBUG:
        cv2.imshow("Minimap & Player & Graph", graph_dbg)

    # (Пример: можно напечатать краткую сводку по графу)
    if DEBUG and cv2.waitKey(1) == ord("i"):
        print(f"Граф: узлов={len(nodes)}, рёбер={len(edges)}")

    if cv2.waitKey(1) == ord("q"):
        break

cv2.destroyAllWindows()
device.close()
print("Finished.")
