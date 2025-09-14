import io
import os

import cv2
from PIL import Image

from devices.device import Device


def save_image(img, name: str | None = None):
    filename = (
        name if name is not None else f"images/img_{len(os.listdir('images'))}.png"
    )
    cv2.imwrite(filename, img)


if __name__ == "__main__":
    device = Device("127.0.0.1", 58526)
    device.connect()

    if not os.path.exists("images"):
        os.mkdir("images")
    try:
        # while(True):
        if True:
            raw = device.get_frame()

            img = Image.open(io.BytesIO(raw))
            cropped_img = img.crop((0, 0, 1280, 690))  # Adjust the crop area as needed
            # cropped_img = img.crop((15, 120, 290, 290))  # minimap
            # cropped_img = img.crop((640 - 150, 345 - 80, 640 + 150, 345 + 120))  # center
            cropped_img.save(f"./images/img_{len(os.listdir('images'))}.png")

    finally:
        device.close()
