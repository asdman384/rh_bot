import time

import cv2
import numpy as np

from frames import extract_game


def preprocess(img_bgr):
    # Упор на форму светлой ленты: серый + лёгкое сглаживание + контраст
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    # cv2.imshow("g", gray)
    # cv2.waitKey(0)
    return gray


def crop_loader_roi(frame: cv2.typing.MatLike) -> cv2.typing.MatLike:
    X = 550
    Y = 600
    W = 200
    H = 40
    return cv2.resize(frame[Y : Y + H, X : X + W], (W, H))


def find_tpl(
    frame: cv2.typing.MatLike,
    tpl: cv2.typing.MatLike,  # IMREAD_COLOR
    scales=[1.0],  # np.linspace(1.0, 1.0, 3)
    method=cv2.TM_CCOEFF_NORMED,
    score_threshold=0.9,
    debug=False,
):
    img_p = preprocess(frame)
    tpl_p0 = preprocess(tpl)

    best = dict(score=-1, rect=None, scale=None, loc=None)
    for s in scales:
        w = max(1, int(tpl_p0.shape[1] * s))
        h = max(1, int(tpl_p0.shape[0] * s))
        tpl_p = cv2.resize(tpl_p0, (w, h), interpolation=cv2.INTER_AREA)

        res = cv2.matchTemplate(img_p, tpl_p, method)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        score = (
            max_val
            if method in (cv2.TM_CCOEFF_NORMED, cv2.TM_CCORR_NORMED)
            else -min_val
        )
        if score > best["score"]:
            best.update(
                score=score, rect=(max_loc[0], max_loc[1], w, h), scale=s, loc=max_loc
            )

    if best["score"] < score_threshold:
        return None, best["score"]

    x, y, w, h = best["rect"]
    cx, cy = x + w // 2, y + h // 2

    if debug:
        out = frame.copy()
        cv2.rectangle(out, (x, y), (x + w, y + h), (0, 255, 0), 2)
        cv2.circle(out, (cx, cy), 3, (0, 0, 255), -1)
        cv2.putText(
            out,
            f"score={best['score']:.2f}, scale={best['scale']:.2f}",
            (max(0, x - 20), max(20, y - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 235, 0),
            1,
        )
        cv2.imshow("DBG/find_tpl", out)
        cv2.waitKey(1)

    # Возвращаем координаты прямоугольника и центра
    return {
        "x": x,
        "y": y,
        "w": w,
        "h": h,
        "cx": cx,
        "cy": cy,
        "score": best["score"],
        "scale": best["scale"],
    }, best["score"]


def wait_for(
    tpl_path: str | cv2.typing.MatLike,
    get_frame,
    timeout_s=8,
    score_threshold=0.9,
    debug=False,
):
    """
    get_frame() -> BGR кадр (np.ndarray).
    Ждём появления баннера до timeout_s. Возвращаем True/False.
    """
    if type(tpl_path) is str:
        tpl = cv2.imread(str(tpl_path), cv2.IMREAD_COLOR)
    else:
        tpl = tpl_path

    t0 = time.time()
    while time.time() - t0 < timeout_s:
        frame = get_frame()
        if frame is None:
            time.sleep(0.02)
            continue

        box, _ = find_tpl(frame, tpl, score_threshold=score_threshold, debug=debug)
        if box is not None:
            print(f"{tpl_path} detected t={time.time() - t0:.1f}s") if debug else None
            return True

        time.sleep(0.1)
    return False


def wait_loading(get_frame, wait_appearance=3, timeout=30, retry=None, debug=False):
    print("start wait_loading") if debug else None
    loader_1 = cv2.imread("resources/loader_1.png", cv2.IMREAD_COLOR)
    loader_2 = cv2.imread("resources/loader_2.png", cv2.IMREAD_COLOR)
    loader_3 = cv2.imread("resources/loader_3.png", cv2.IMREAD_COLOR)
    net_error = cv2.imread("resources/net_error.png", cv2.IMREAD_COLOR)

    def found(frame: cv2.typing.MatLike) -> bool:
        box1, _ = find_tpl(frame, loader_1, score_threshold=0.95, debug=debug)
        box2, _ = find_tpl(frame, loader_2, score_threshold=0.95, debug=debug)
        box3, _ = find_tpl(frame, loader_3, score_threshold=0.95, debug=debug)
        return ((box1 is not None) + (box2 is not None) + (box3 is not None)) > 0

    t0 = time.time()
    while time.time() - t0 < wait_appearance:
        frame = get_frame()
        if find_tpl(extract_game(frame), net_error)[0] is not None:
            retry() if retry is not None else None
            wait_loading(get_frame, wait_appearance, timeout, retry, debug)

        if found(crop_loader_roi(frame)):
            print(f"found loader after {time.time() - t0}s") if debug else None
            t1 = time.time()
            while time.time() - t1 < timeout:
                frame = get_frame()
                if find_tpl(extract_game(frame), net_error)[0] is not None:
                    retry() if retry is not None else None
                    wait_loading(get_frame, wait_appearance, timeout, retry, debug)

                if not found(crop_loader_roi(frame)):
                    print(
                        f"disappeared loader after {time.time() - t1}s"
                    ) if debug else None
                    # TODO: check network connection and retry if tpl found
                    return True
            print(f"Loader still exists after {timeout}s") if debug else None

    print(f"Loader did not found after {wait_appearance}s") if debug else None
    return False


if __name__ == "__main__":
    from devices.device import Device
    from controller import Controller

    device = Device("127.0.0.1", 58526)
    device.connect()
    controller = Controller(device, True)

    def flush_bag():
        black = cv2.imread("resources/black.png", cv2.IMREAD_COLOR)
        black_box, _ = find_tpl(device.get_frame2(), black, score_threshold=0.9)
        if black_box is None:
            print("failed to flush bag")
            return False

        # sort
        controller._tap((880, 620))  # Inventory button
        time.sleep(0.5)
        controller._tap((1170, 650))  # Sort button
        controller.wait_loading(1)
        controller.back()
        time.sleep(0.5)

        # go blacksmith
        controller._tap((black_box["x"], black_box["y"]))
        time.sleep(1)

        # Decompose routine
        controller._tap((1060, 320))  # Decompose button
        time.sleep(1)
        for x in range(680, 1081, 300):
            controller._tap((x, 450))  # Select Items
            time.sleep(0.05)

        controller._tap((1140, 360))  # Decompose action button
        time.sleep(0.5)
        check_box, _ = find_tpl(
            device.get_frame2(),
            cv2.imread("resources/check_grade.png", cv2.IMREAD_COLOR),
            score_threshold=0.9,
        )
        if check_box is not None:
            controller._tap((740, 500))  # Confirm button

        controller.wait_loading(2)
        time.sleep(0.5)
        controller.back()
        time.sleep(0.5)

        # Trade routine
        controller._tap((1060, 390))  # Trade button
        time.sleep(1)
        controller._tap((1170, 375))  # Sell button
        time.sleep(0.5)
        controller._tap((1150, 115))  # Sell the grade button
        time.sleep(0.5)
        controller._tap((400, 260))  # Increase grade button
        time.sleep(0.05)
        controller._tap((400, 260))  # Increase grade button
        time.sleep(0.05)
        controller._tap((850, 490))  # OK button
        controller.wait_loading(2)
        time.sleep(0.5)
        controller.back()
        time.sleep(0.5)
        controller.back()
        time.sleep(0.5)

    flush_bag()
    wait_loading(lambda: device.get_frame2(), wait_appearance=0.5, debug=True)

    cv2.destroyAllWindows()
