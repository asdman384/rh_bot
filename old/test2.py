import cv2
import numpy as np

from devices.device import Device


def create_wall_mask(image: np.ndarray) -> np.ndarray:
    """
    Создает маску стен лабиринта на основе цветного изображения.

    Эта функция выделяет красноватые линии стен, игнорируя при этом
    розовые пятна и шум от огня.

    Args:
        image: Входное изображение в формате BGR (стандарт OpenCV).

    Returns:
        Бинарная маска, где белым цветом обозначены стены, а черным - все остальное.
    """
    # 1. Преобразование изображения из BGR в HSV для более удобной работы с цветом.
    hsv_image = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

    # 2. Определение диапазонов для красного цвета в HSV.
    # Красный цвет находится на краях спектра Hue (0 и 180), поэтому нужно два диапазона.
    # Диапазоны подобраны так, чтобы захватывать яркие и насыщенные красные/розовые оттенки стен.

    # Нижний диапазон красного
    lower_red_1 = np.array([0, 100, 80])
    upper_red_1 = np.array([20, 255, 255])

    # Верхний диапазон красного
    lower_red_2 = np.array([165, 100, 80])
    upper_red_2 = np.array([180, 255, 255])

    # 3. Создание масок для каждого диапазона и их объединение.
    mask1 = cv2.inRange(hsv_image, lower_red_1, upper_red_1)
    mask2 = cv2.inRange(hsv_image, lower_red_2, upper_red_2)
    combined_mask = cv2.bitwise_or(mask1, mask2)
    cv2.imshow("combined_mask", combined_mask)

    # 4. Морфологические операции для очистки маски.
    # a) "Открытие" (Opening) - убирает мелкий шум и точки (эрозия -> расширение).
    kernel_open = np.ones((3, 3), np.uint8)
    clean_mask = cv2.morphologyEx(combined_mask, cv2.MORPH_OPEN, kernel_open)
    cv2.imshow("clean_mask", clean_mask)

    # b) "Расширение" (Dilation) - немного утолщает линии стен, чтобы сделать их сплошными.
    kernel_dilate = np.ones((5, 5), np.uint8)
    dilated_mask = cv2.dilate(clean_mask, kernel_dilate, iterations=1)

    # 5. Фильтрация контуров по площади для удаления оставшихся артефактов (например, розового пятна).
    contours, _ = cv2.findContours(dilated_mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    final_mask = np.zeros_like(dilated_mask)

    if contours:
        # Устанавливаем порог минимальной площади контура.
        # Стены обычно образуют один большой контур.
        min_area_threshold = 500

        large_contours = [
            cnt for cnt in contours if cv2.contourArea(cnt) > min_area_threshold
        ]

        # Рисуем только большие контуры на финальной маске.
        cv2.drawContours(final_mask, large_contours, -1, (255), thickness=cv2.FILLED)

    return final_mask


def extract_minimap(frame: cv2.typing.MatLike) -> cv2.typing.MatLike:
    X = 50
    Y = 110
    W = 250
    H = 200
    return cv2.resize(frame[Y : Y + H, X : X + W], (W, H))


# --- Пример использования ---
if __name__ == "__main__":
    device = Device("127.0.0.1", 58526)
    device.connect()

    while 1:
        mini_map = extract_minimap(device.get_frame2())
        wall_mask = create_wall_mask(mini_map)
        # Создание маски

        # Создание изображения для сравнения
        # Уменьшим размер для удобного отображения
        scale = 0.8
        width = int(mini_map.shape[1] * scale)
        height = int(mini_map.shape[0] * scale)
        dim = (width, height)

        img_resized = cv2.resize(mini_map, dim, interpolation=cv2.INTER_AREA)
        mask_resized_bgr = cv2.cvtColor(
            cv2.resize(wall_mask, dim, interpolation=cv2.INTER_AREA), cv2.COLOR_GRAY2BGR
        )

        # Наложение маски на оригинал для наглядности
        overlay = cv2.addWeighted(img_resized, 0.7, mask_resized_bgr, 0.3, 0)

        # Соединение изображений для вывода
        comparison_image = np.hstack((img_resized, mask_resized_bgr, overlay))

        # Показ результата
        cv2.imshow("Result", comparison_image)

        cv2.waitKey(111)

    cv2.destroyAllWindows()
