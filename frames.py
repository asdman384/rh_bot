import cv2


def extract_game(frame: cv2.typing.MatLike) -> cv2.typing.MatLike:
    X = 240
    Y = 0
    W = 830
    H = 690
    return cv2.resize(frame[Y : Y + H, X : X + W], (W, H))
