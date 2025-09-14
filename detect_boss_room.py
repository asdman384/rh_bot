import cv2
import numpy as np
import time

from devices.device import Device

_boss_label = np.load("resources/boss_label_eroded.npy")


def _mask_red(hsv):
    m1 = cv2.inRange(hsv, (0, 120, 130), (10, 255, 255))
    m2 = cv2.inRange(hsv, (170, 120, 130), (180, 255, 255))
    m = cv2.bitwise_or(m1, m2)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    return m


def _mask01(img):
    """-> бинарная маска 0/1, uint8, 1 канал"""
    if img.ndim == 3:
        if img.shape[2] == 4:
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
        else:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, m = cv2.threshold(img, 127, 255, cv2.THRESH_BINARY)
    return (m // 255).astype(np.uint8)


def _find_mask_tm(big_mask, small_mask, tolerance=0.0, debug=False):
    """
    Корреляция 0/1: совпадение там, где сумма совпавших единиц
    >= (1 - tolerance) * sum(единиц в шаблоне)
    """
    M = _mask01(big_mask).astype(np.float32)
    E = _mask01(small_mask).astype(np.float32)
    res = cv2.matchTemplate(M, E, cv2.TM_CCORR)  # сумма совпавших 1
    target = float(E.sum())
    thr = target * (1.0 - float(tolerance))
    ys, xs = np.where(res >= thr)
    hits = list(zip(xs.tolist(), ys.tolist()))

    if not debug:
        return hits, res

    for x, y in hits:
        cv2.rectangle(
            M,
            (x, y),
            (x + small_mask.shape[1] - 1, y + small_mask.shape[0] - 1),
            (255, 255, 255),
            1,
        )
    cv2.putText(M, f"hits={len(hits)}", (10, 20), 0, 0.8, (255, 255, 255), 1)
    cv2.imshow("hits", M)

    return hits, res


def wait_for_boss_popup(get_frame, timeout_s=8, debug=False):
    """
    get_frame() -> BGR кадр (np.ndarray).
    Ждём появления баннера до timeout_s. Возвращаем True/False.
    """
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        frame = get_frame()
        if frame is None:
            time.sleep(0.02)
            continue

        mask = _mask_red(cv2.cvtColor(frame, cv2.COLOR_BGR2HSV))
        hits, _ = _find_mask_tm(mask, _boss_label, debug=False)
        if len(hits) > 0:
            print(f"Boss popup detected t={time.time() - t0:.1f}s") if debug else None
            return True

        time.sleep(0.1)
    return False


if __name__ == "__main__":
    device = Device("127.0.0.1", 58526)
    device.connect()
    # frame = device.get_frame2()
    # mask = _mask_red(cv2.cvtColor(frame, cv2.COLOR_BGR2HSV))
    # hits, _ = _find_mask_tm(mask, _boss_label, debug=True)
    # print(hits)

    # cv2.imshow("wait_for_boss_popup/boss_label", _boss_label)
    # cv2.imshow("wait_for_boss_popup/mask", mask)
    # cv2.waitKey(0)

    found = wait_for_boss_popup(lambda: device.get_frame2(), timeout_s=8, debug=True)
    print(found)

    cv2.waitKey(0)
