import time

import cv2
import numpy as np

from detect_location import find_tpl
from devices.device import Device
from maze_rh import extract_game

# SIZE = 10
# BUTTON_PLUS = (10, 10)
# BUTTON_MINUS = (10, 40)
# v = 255
# def mouse_callback(event, x, y, flags, param):
#     global v
#     if event != cv2.EVENT_LBUTTONDOWN:
#         return

#     if (BUTTON_PLUS[0] <= x <= BUTTON_PLUS[0] + SIZE) and (
#         BUTTON_PLUS[1] <= y <= BUTTON_PLUS[1] + SIZE
#     ):
#         v = v + 1
#         print(f"lower {v}")

#     if (BUTTON_MINUS[0] <= x <= BUTTON_MINUS[0] + SIZE) and (
#         BUTTON_MINUS[1] <= y <= BUTTON_MINUS[1] + SIZE
#     ):
#         v = v - 1
#         print(f"lower {v}")

#     mask = cv2.inRange(
#         hsv, np.array([90, 173, v]), np.array([99, 198, 255])
#     )  # | cv2.inRange(hsv, LOWER_1, UPPER_2)
#     cv2.imshow("center/DBG", mask)


# panel = np.zeros((100, 200, 3), dtype=np.uint8)
# cv2.rectangle(
#     panel, BUTTON_PLUS, (BUTTON_PLUS[0] + SIZE, BUTTON_PLUS[1] + SIZE), (255, 0, 255), 1
# )
# cv2.rectangle(
#     panel,
#     BUTTON_MINUS,
#     (BUTTON_MINUS[0] + SIZE, BUTTON_MINUS[1] + SIZE),
#     (255, 0, 255),
#     1,
# )
# cv2.imshow("empty", panel)
# cv2.setMouseCallback("empty", mouse_callback)


def mouse_callback(event, x, y, flags, param):
    if event != cv2.EVENT_LBUTTONDOWN:
        return
    print(f"x={x}, y={y}")


device = Device("127.0.0.1", 58526)
device.connect()

dain_sw_roi = (0, 260, 415, 640)
dain_ne_roi = (395, 120, 690, 340)


dain_sw = cv2.imread("resources/dain/sw.png")
dain_ne = cv2.imread("resources/dain/ne.png")

while 1:
    frame_game = extract_game(device.get_frame2())

    t0 = time.time()
    X, Y, X2, Y2 = dain_ne_roi
    frame = cv2.resize(frame_game[Y:Y2, X:X2], (X2 - X, Y2 - Y))
    box, score = find_tpl(frame, dain_ne, [1.0], score_threshold=0.42, debug=True)
    print("ne: ", box is not None, score)

    X, Y, X2, Y2 = dain_sw_roi
    frame = cv2.resize(frame_game[Y:Y2, X:X2], (X2 - X, Y2 - Y))
    box, score = find_tpl(frame, dain_sw, [1.0], score_threshold=0.42, debug=True)
    print("sw: ", box is not None, score, time.time() - t0)

cv2.circle(frame, (640, 290), 6, (0, 255, 0), -1)
cv2.imshow("frame", frame)
cv2.setMouseCallback("frame", mouse_callback)
cv2.waitKey(0)

# i = 0
# while 1:
#     i += 1
#     frame = device.get_frame2().copy()
#     cv2.imshow("frame", frame)
#     cv2.imwrite(f"images/{i}.png", frame)
#     cv2.waitKey(0)
