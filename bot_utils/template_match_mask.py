import time
import cv2
import numpy as np


def _mask_red(hsv):
    m1 = cv2.inRange(hsv, (0, 120, 130), (10, 255, 255))
    m2 = cv2.inRange(hsv, (170, 120, 130), (180, 255, 255))
    m = cv2.bitwise_or(m1, m2)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    return m


def crop(frame: cv2.typing.MatLike) -> cv2.typing.MatLike:
    X = 440
    Y = 190
    W = 145
    H = 50
    return cv2.resize(frame[Y : Y + H, X : X + W], (W, H))


def find_subset_locations(erode, mask):
    """
    Ищет позиции (x, y) в большой маске mask, где все единицы erode
    попадают на единицы mask (без масштабирования шаблона).
    Возвращает: found(bool), hits[list[(x,y)]]
    (x, y) — координата ЛЕВОГО-ВЕРХНЕГО угла попадания erode на mask.
    """

    h, w = erode.shape
    H, W = mask.shape
    if h > H or w > W:
        return False, []  # шаблон больше, чем изображение — вхождений нет

    target_sum = float(erode.sum())  # число единичных пикселей в шаблоне
    if target_sum == 0.0:
        # Пустой шаблон — формально «всегда присутствует»
        return True, [(0, 0)]

    # Корреляция по шаблону 0/1 даёт сумму совпавших единиц.
    # Там, где сумма == target_sum, все 1 из E попали на 1 в M.
    res = cv2.matchTemplate(erode, mask, method=cv2.TM_CCORR)  # размер: (H-h+1, W-w+1)

    # Из-за float сравниваем с небольшим запасом
    eps = 1e-6
    ys, xs = np.where(res >= target_sum - eps)
    hits = list(zip(xs.tolist(), ys.tolist()))
    return (len(hits) > 0), hits


frame = cv2.imread("resources/BOSS.png", cv2.IMREAD_COLOR)
# frame = crop(frame)

hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
mask = _mask_red(hsv)
cv2.imshow("mask", mask)

# erode = cv2.erode(mask, np.ones((3, 3), np.uint8), iterations=1)
# cv2.imshow("erode", erode)
# np.save("resources/boss_label_eroded.npy", erode)
erode = np.load("resources/boss_label_eroded.npy")
cv2.imshow("erode_loaded", erode)


# Можем продолжить логику с загруженной версией
t0 = time.time()
res = find_subset_locations(erode, mask)
print(res[0], time.time() - t0)
if res[0]:
    print("Eroded mask is present in the original mask.")
else:
    print("Eroded mask is not present in the original mask.")

cv2.waitKey(0)
