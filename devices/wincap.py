from ctypes import windll

import numpy as np
import win32gui
import win32ui
import win32con

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
        raise RuntimeError(f"Окно '{substring}', не найдено.")
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


def _lparam(x, y):
    return (y << 16) | (x & 0xFFFF)


def _resolve_target_hwnd_and_point(hwnd, x, y):
    """
    По (x,y) в клиентских координатах hwnd находим реальный целевой дочерний hwnd,
    который получил бы клик, и переводим точку в его клиентские координаты.
    """
    # (x,y) клиента -> экран
    sx, sy = win32gui.ClientToScreen(hwnd, (x, y))

    # Постараемся найти «реальный» дочерний, который получает мышь
    child = None
    if hasattr(win32gui, "RealChildWindowFromPoint"):
        try:
            child = win32gui.RealChildWindowFromPoint(hwnd, (sx, sy))
        except Exception:
            child = None

    if not child or not win32gui.IsWindow(child):
        # Фолбэк: ищем потомка относительно родителя
        px, py = win32gui.ScreenToClient(hwnd, (sx, sy))
        try:
            child = win32gui.ChildWindowFromPoint(hwnd, (px, py))
        except Exception:
            child = None

    target = child if child and win32gui.IsWindow(child) else hwnd
    # Переведём точку в клиентские координаты target
    tx, ty = win32gui.ScreenToClient(target, (sx, sy))
    return target, tx, ty


def click_in_window(hwnd, x, y, button="left", double=False, route_to_child=True):
    """
    Клик в окне по клиентским координатам (x,y).
    - hwnd: дескриптор окна (HWND)
    - x, y: координаты в СООБЩАЕМОМ окну (клиентская область top-level hwnd)
    - button: "left" | "right" | "middle"
    - double: True для двойного клика
    - route_to_child: направлять сообщения непосредственно дочернему контролу под точкой
    Работает без вывода окна на передний план.
    """
    if route_to_child:
        target, tx, ty = _resolve_target_hwnd_and_point(hwnd, x, y)
    else:
        target, tx, ty = hwnd, x, y

    btn = button.lower()
    if btn == "left":
        DOWN, UP, DBL, MK = (
            win32con.WM_LBUTTONDOWN,
            win32con.WM_LBUTTONUP,
            win32con.WM_LBUTTONDBLCLK,
            win32con.MK_LBUTTON,
        )
    elif btn == "right":
        DOWN, UP, DBL, MK = (
            win32con.WM_RBUTTONDOWN,
            win32con.WM_RBUTTONUP,
            win32con.WM_RBUTTONDBLCLK,
            win32con.MK_RBUTTON,
        )
    elif btn == "middle":
        DOWN, UP, DBL, MK = (
            win32con.WM_MBUTTONDOWN,
            win32con.WM_MBUTTONUP,
            win32con.WM_MBUTTONDBLCLK,
            win32con.MK_MBUTTON,
        )
    else:
        raise ValueError("button must be 'left', 'right', or 'middle'")

    lp = _lparam(tx, ty)

    # Небольшая «прелюдия» — переместим мышь, чтобы некоторые UI корректно приняли координаты
    win32gui.SendMessage(target, win32con.WM_MOUSEMOVE, 0, lp)

    # Клик/даблклик
    if double:
        # Общепринятая последовательность двойного клика:
        win32gui.SendMessage(target, DOWN, MK, lp)
        win32gui.SendMessage(target, UP, 0, lp)
        win32gui.SendMessage(target, DBL, MK, lp)
        win32gui.SendMessage(target, UP, 0, lp)
    else:
        win32gui.SendMessage(target, DOWN, MK, lp)
        win32gui.SendMessage(target, UP, 0, lp)


if __name__ == "__main__":
    import cv2

    hwnd = find_window_by_title("Rogue Hearts")
    frame = screenshot_window_np(hwnd, client_only=False)
    print(f"Frame shape: {frame.shape}")

    cv2.imwrite("screenshot.png", frame)
