from ctypes import windll

import cv2
import numpy as np
import win32gui
import win32ui

# Сделаем процесс DPI-aware, чтобы размеры не «плыли» на масштабировании Windows
try:
    windll.shcore.SetProcessDpiAwareness(2)  # Per-monitor v2 (Win 8.1+)
except Exception:
    try:
        windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def find_window_by_title(substring: str) -> int:
    """Возвращает HWND первого видимого окна, заголовок которого содержит substring."""
    matches = []

    def enum_handler(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if substring.lower() in title.lower():
                matches.append((len(title), hwnd))

    win32gui.EnumWindows(enum_handler, None)
    if not matches:
        raise RuntimeError(f"Окно с заголовком, содержащим '{substring}', не найдено.")
    return sorted(matches, reverse=True)[0][1]


def screenshot_window_np(hwnd: int, client_only: bool = False) -> np.ndarray:
    """
    Скриншот окна по HWND -> numpy.ndarray (H, W, 3) в формате **BGR** для OpenCV.
    Если client_only=True — только клиентская область (без рамки/тени).
    """
    # Координаты области
    if client_only:
        left, top, right, bottom = win32gui.GetClientRect(hwnd)
        left, top = win32gui.ClientToScreen(hwnd, (left - 3, top))
        right, bottom = win32gui.ClientToScreen(hwnd, (right, bottom))
    else:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)

    width, height = right - left, bottom - top
    if width <= 0 or height <= 0:
        raise RuntimeError("Некорректные размеры окна (возможно, оно минимизировано).")

    # DC / Bitmap
    hdc_screen = win32gui.GetDC(0)
    dc_screen = win32ui.CreateDCFromHandle(hdc_screen)
    dc_mem = dc_screen.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(dc_screen, width, height)
    dc_mem.SelectObject(bmp)

    # PrintWindow флаги
    PW_CLIENTONLY = 0x00000001
    PW_RENDERFULLCONTENT = 0x00000002
    flags = PW_RENDERFULLCONTENT | (PW_CLIENTONLY if client_only else 0)

    # Захват
    ok = windll.user32.PrintWindow(hwnd, dc_mem.GetSafeHdc(), flags)
    if ok != 1:
        # Фолбэк — без RENDERFULLCONTENT
        ok = windll.user32.PrintWindow(
            hwnd, dc_mem.GetSafeHdc(), (PW_CLIENTONLY if client_only else 0)
        )

    # Извлечение пикселей
    bmpinfo = bmp.GetInfo()
    bmpbytes = bmp.GetBitmapBits(True)

    # В Windows битмапы обычно идут в BGRX и "вверх дном" (bottom-up) — перевернём
    arr = np.frombuffer(bmpbytes, dtype=np.uint8)
    # Если битность 32 bpp — ожидаем 4 канала, иначе попытаемся угадать 3 канала
    channels = 4 if len(bmpbytes) == bmpinfo["bmWidth"] * bmpinfo["bmHeight"] * 4 else 3
    arr = arr.reshape((bmpinfo["bmHeight"], bmpinfo["bmWidth"], channels))
    # arr = np.flipud(arr)  # bottom-up -> top-down

    # Оставляем BGR (OpenCV-friendly)
    if channels == 4:
        arr = arr[:, :, :3]  # отбрасываем X/Alpha канал

    # Уборка ресурсов
    win32gui.DeleteObject(bmp.GetHandle())
    dc_mem.DeleteDC()
    dc_screen.DeleteDC()
    win32gui.ReleaseDC(0, hdc_screen)

    if ok != 1:
        # Некоторые GPU-ускоряемые окна не отдают буфер через GDI
        raise RuntimeError(
            "PrintWindow вернул пустой/частичный кадр (окно может не поддерживать захват)."
        )
    return arr  # np.ndarray BGR


if __name__ == "__main__":
    import time

    def limit_fps(last_time: float, max_fps: float) -> float:
        """Ограничить FPS простым сном; вернуть новый last_time."""
        if max_fps <= 0:
            return time.time()
        min_interval = 1.0 / max_fps
        now = time.time()
        dt = now - last_time
        if dt < min_interval:
            time.sleep(min_interval - dt)
            now = time.time()
        return now

    # Пример использования
    hwnd = find_window_by_title("Rogue Hearts")  # или часть названия: "Notepad"
    last = 0.0
    # while True:
    if True:
        last = limit_fps(last, 30)
        frame_bgr = screenshot_window_np(
            hwnd, client_only=False
        )  # np.ndarray (H,W,3) BGR
        cv2.imwrite("notepad.png", frame_bgr)
        cv2.waitKey(1)
