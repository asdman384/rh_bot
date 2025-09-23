import cv2


ne_img = cv2.imread("bot_utils/sense_utils/ne_mask.png", cv2.IMREAD_GRAYSCALE)
nw_img = cv2.imread("bot_utils/sense_utils/nw_mask.png", cv2.IMREAD_GRAYSCALE)
se_img = cv2.imread("bot_utils/sense_utils/se_mask.png", cv2.IMREAD_GRAYSCALE)
sw_img = cv2.imread("bot_utils/sense_utils/sw_mask.png", cv2.IMREAD_GRAYSCALE)


ys, xs = (sw_img > 200).nonzero()
for x, y in zip(xs, ys):
    print(f"({x}, {y}),")
