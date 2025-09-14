import cv2
import numpy as np

# Загружаем изображение
# mask = cv2.imread("images/img_1.png")

# NWroi = mask[1:64, 12:106]
# cv2.imshow("NWroi", NWroi)

# NEroi = mask[1:64, 194:286]
# cv2.imshow("NEroi", NEroi)

# SWroi = mask[130:200, 0:100]
# cv2.imshow("SWroi", SWroi)

# SEroi = mask[130:200, 199:300]
# cv2.imshow("SEroi", SEroi)


def white_pixels(mask):
    white_pixels = np.argwhere(mask > 220)
    white_pixels = white_pixels[::3]

    if len(white_pixels) > 0:
        print(f"Нашли {len(white_pixels)} белых пикселей")
        # Перебираем найденные пиксели и красим их в красный
        for y, x in white_pixels:
            if 130 <= y < 200 and 199 <= x < 300:
                print(f"({y}, {x}),")
                mask[y, x] = (0, 0, 255)  # BGR: красный
    else:
        print("Белых пикселей в верхнем левом квадрате нет")

    # Сохраняем результат
    cv2.imshow("mask-red", mask)
    cv2.waitKey(0)


def print_pixels_array(mask):
    dbg = mask.copy()
    #         ((X,     Y), (W,   H))
    # SW_RECT_meta_khanel = ((186, 429), (100, 78))
    # SE_RECT_meta_khanel = ((500, 429), (100, 78))
    # NW_RECT_meta_bhalor = ((224, 239), (82, 55))
    RECT_meta = ((224, 239), (82, 55))

    X = RECT_meta[0][0]
    Y = RECT_meta[0][1]
    W = RECT_meta[1][0]
    H = RECT_meta[1][1]

    cv2.rectangle(dbg, (X, Y), (X + W, Y + H), (255, 255, 255), 1)
    cv2.imshow("mask", dbg)
    cv2.waitKey(0)
    # Print coordinates of all white pixels in NE_RECT
    roi = mask[Y : Y + H, X : X + W]
    ys, xs = np.where(roi == 255)

    coords = list(zip(xs + X, ys + Y))
    print(f"Coordinates of white pixels in NE_RECT: {coords}")
    for i in range(len(xs)):
        print(f"({ys[i] + Y}, {xs[i] + X}),")
