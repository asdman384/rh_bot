import socket
import struct
from typing import Optional


class MinicapClient:
    """
    Клиент для чтения потока JPEG-кадров от minicap через локальный TCP,
    например после: adb forward tcp:1313 localabstract:minicap
    Протокол: https://github.com/openstf/minicap
    """

    def __init__(self, host="127.0.0.1", port=1313, connect_timeout=5.0):
        self.host = host
        self.port = port
        self.connect_timeout = connect_timeout
        self.sock: Optional[socket.socket] = None
        self.banner = {}
        self._buf = bytearray()

    def connect(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(self.connect_timeout)
        s.connect((self.host, self.port))
        s.settimeout(None)  # делаем неблокирующий в виде read_exact
        self.sock = s
        self._read_banner()

    def close(self):
        try:
            if self.sock:
                self.sock.close()
        finally:
            self.sock = None

    def _read_exact(self, n: int) -> bytes:
        """Прочитать ровно n байт из сокета."""
        data = bytearray()
        while len(data) < n:
            chunk = self.sock.recv(n - len(data))
            if not chunk:
                raise ConnectionError("minicap: соединение закрыто")
            data.extend(chunk)
        return bytes(data)

    def _read_banner(self):
        """Прочитать баннер minicap (первая структура заголовка)."""
        # Первая пара байт: version (1), banner length (1)
        header = self._read_exact(2)
        version, banner_len = header[0], header[1]

        # Остальные байты баннера
        rest = self._read_exact(banner_len - 2)

        # Разбор по известному формату:
        # version (1), length (1),
        # pid (4), realWidth (4), realHeight (4),
        # virtualWidth (4), virtualHeight (4),
        # orientation (1), quirks (1)
        try:
            # Собираем все байты
            full = header + rest
            # Пропустим первые 2 байта (version,length), затем читаем поля
            # Для простоты используем int.from_bytes в нужных местах:
            pid = int.from_bytes(full[2:6], "little", signed=False)
            real_w = int.from_bytes(full[6:10], "little", signed=False)
            real_h = int.from_bytes(full[10:14], "little", signed=False)
            virt_w = int.from_bytes(full[14:18], "little", signed=False)
            virt_h = int.from_bytes(full[18:22], "little", signed=False)
            orientation = full[22]
            quirks = full[23]
        except Exception:
            # Если что-то пошло не так, не падаем
            pid = real_w = real_h = virt_w = virt_h = orientation = quirks = 0

        self.banner = {
            "version": version,
            "length": banner_len,
            "pid": pid,
            "real_w": real_w,
            "real_h": real_h,
            "virt_w": virt_w,
            "virt_h": virt_h,
            "orientation_quarters": orientation,  # 0..3
            "quirks": quirks,
        }
        print("[minicap] banner:", self.banner)

    def read_frame(self) -> Optional[bytes]:
        """Прочитать один JPEG-фрейм (как bytes)."""
        # Длина фрейма — 4 байта little-endian
        try:
            size_buf = self._read_exact(4)
        except Exception as e:
            return None
        frame_size = struct.unpack("<I", size_buf)[0]
        if frame_size <= 0 or frame_size > 50_000_000:
            # Защита от мусора
            return None
        try:
            jpeg = self._read_exact(frame_size)
            return jpeg
        except Exception:
            return None


if __name__ == "__main__":
    import cv2
    import numpy as np
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

    def minicap_loop(host="127.0.0.1", port=1313, show=True, max_fps: float = 0.0):
        client = MinicapClient(host=host, port=port)
        try:
            client.connect()
        except Exception as e:
            print(f"[minicap] Не удалось подключиться к {host}:{port}: {e}")
            return

        last = 0.0
        try:
            print("[minicap] Старт цикла... Нажмите 'q' в окне, чтобы выйти.")
            while True:
                last = limit_fps(last, max_fps)
                jpeg = client.read_frame()
                if jpeg is None:
                    print("[minicap] Конец потока или ошибка чтения.")
                    break
                arr = np.frombuffer(jpeg, dtype=np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if img is None:
                    continue

                if show:
                    cv2.imshow("WSA minicap", img)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break
        finally:
            client.close()
            cv2.destroyAllWindows()

    # ----------------------------- MAIN ------------------------------------

    # adb disconnect adb-1bc7f1e9-kkc2yd._adb-tls-connect._tcp
    # adb shell wm size 690x1280
    # adb forward tcp:1313 localabstract:minicap
    # adb shell "LD_LIBRARY_PATH=/data/local/tmp /data/local/tmp/minicap -P 690x1280@690x1280/90 -S -Q 90"

    minicap_loop(show=True, max_fps=30)
