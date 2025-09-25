import time
import cv2
import numpy as np

from boss.dain import BossDain
from controller import Controller
from devices.device import Device
from maze_rh import MazeRH, extract_minimap
from sensing.minimap2 import find_blue_mask


device = Device("127.0.0.1", 58526)
device.connect()
controller = Controller(device)
boss = BossDain(controller, True)
maze = MazeRH(controller, boss, True)

frame = cv2.imread("frame.png")
# frame = maze.get_frame()
# # TEST is_near_exit

# Define a set where the key is a tuple (x, y)
visited_points = set()


def mouse_callback(event, x_, y_, flags, param):
    global x, y
    if event != cv2.EVENT_LBUTTONDOWN:
        return
    x, y = x_, y_
    visited_points.add((x, y))
    print(f"x={x_}, y={y_}")


while 1:
    # frame = maze.get_frame()
    frame830x690 = extract_minimap(frame)

    blue_mask = find_blue_mask(frame830x690, boss.minimap_masks["path"], debug=True)

    # Find the coordinates of the topmost white pixel in blue_mask
    white_pixels = np.column_stack(np.where(blue_mask == 255))
    if white_pixels.size > 0:
        y, x = white_pixels[np.argmin(white_pixels[:, 0])]
        cv2.circle(frame830x690, (x + 13, y + 33), 2, (0, 0, 255), -1)
        cv2.imshow("frame830x690", frame830x690)
    else:
        print("No white pixels found in blue_mask.")
