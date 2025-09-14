import cv2
import numpy as np


def rgb_to_hsv(r, g, b):
    # OpenCV uses BGR format
    color_bgr = np.uint8([[[b, g, r]]])
    color_hsv = cv2.cvtColor(color_bgr, cv2.COLOR_BGR2HSV)
    return color_hsv[0][0].tolist()


def hex_to_hsv(hex_code):
    hex_code = hex_code.lstrip("#")
    if len(hex_code) != 6:
        raise ValueError("Hex code must be 6 characters long.")
    r = int(hex_code[0:2], 16)
    g = int(hex_code[2:4], 16)
    b = int(hex_code[4:6], 16)
    return rgb_to_hsv(r, g, b)


# Example usage: replace with your own values


# print("HSV:", hex_to_hsv("#5A454A")) 
# print("HSV:", hex_to_hsv("#5A3839")) 
# # print('----------------------------')
# print("HSV:", hex_to_hsv("#5A4142"))
# print("HSV:", hex_to_hsv("#523C42"))
# print('----------------------------')
# print("HSV:", hex_to_hsv("#4A2C31"))
# print("HSV:", hex_to_hsv("#422831"))
# print('----------------------------')
# print("HSV:", hex_to_hsv("#523839"))
# print("HSV:", hex_to_hsv("#523439"))
# print('----------------------------')

# print('----------------------------')
# print("HSV:", hex_to_hsv("#5A494A"))
# print("HSV:", hex_to_hsv("#5A4142"))
# print('----------------------------')
# print("HSV:", hex_to_hsv("#735573"))
# print("HSV:", hex_to_hsv("#63455A"))
# print('----------------------------')
print('----------------------------')
print("HSV:", hex_to_hsv("#4A3439"))
print("HSV:", hex_to_hsv("#4A3031"))
print('----------------------------')

def hsv_float_to_opencv(h, s, v):
    """
    Convert HSV in [0-1, 0-1, 0-1] format to OpenCV HSV [0-179, 0-255, 0-255] format.
    """
    h_cv = int(round(h * 179))
    s_cv = int(round(s * 255))
    v_cv = int(round(v * 255))
    print(f"{[h_cv, s_cv, v_cv]},")
    return [h_cv, s_cv, v_cv]
