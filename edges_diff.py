import cv2 as cv
import numpy as np


def bytes_hamming(a: bytes, b: bytes) -> int:
    n = min(len(a), len(b))
    return sum((x ^ y).bit_count() for x, y in zip(a[:n], b[:n]))


def _dhash_bytes(gray, hash_size=16):  # 16→256 бит
    small = cv.resize(gray, (hash_size + 1, hash_size), interpolation=cv.INTER_AREA)
    diff = (small[:, 1:] > small[:, :-1]).astype(np.uint8).ravel()
    out, acc, k = [], 0, 0
    for bit in diff:
        acc = (acc << 1) | int(bit)
        k += 1
        if k == 8:
            out.append(acc)
            acc = 0
            k = 0
    if k:
        out.append(acc << (8 - k))
    return bytes(out)


def _edge_image(gray):
    gray = cv.GaussianBlur(gray, (3, 3), 0)
    edges = cv.Canny(gray, 60, 120)
    return cv.resize(edges, (32, 32), interpolation=cv.INTER_AREA)


def _phash_bytes(img32):
    hasher = cv.img_hash.PHash_create()
    h = hasher.compute(img32).flatten()  # 8 байт (64 бита)
    return bytes(h.tolist())


def roi_edge_signature(frame_bgr: cv.typing.MatLike, rect) -> bytes:
    """rect = (x, y, w, h). Возвращает устойчивую «контрольную сумму» контура в ROI."""
    x, y, w, h = rect
    roi = frame_bgr[y : y + h, x : x + w]
    hsv = cv.cvtColor(roi, cv.COLOR_BGR2HSV)
    img32 = _edge_image(hsv)
    return _dhash_bytes(img32)
