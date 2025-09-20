from typing import Optional
import os
import logging
import subprocess

from adb_shell.adb_device import AdbDeviceTcp
from adb_shell.auth.sign_pythonrsa import PythonRSASigner

try:
    from devices.wincap import (
        click_in_window,
        find_window_by_title,
        screenshot_window_np,
    )
except ImportError:
    from wincap import click_in_window, find_window_by_title, screenshot_window_np


logger = logging.getLogger(__name__)


class Device:
    """Wrapper around AdbDeviceTcp that manages RSA keys and connection.

    Keeps the defaults from the previous implementation:
    host=127.0.0.1, port=58526, adbkey at user's ~/.android/adbkey,
    and auth_timeout_s=0.1.

    Example:
        with Device() as d:
            adb = d.device
        # device.device.shell("pm list packages | grep -i rogue")
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 58526,
        adbkey: Optional[str] = None,
        auth_timeout_s: float = 0.1,
    ):
        if adbkey is None:
            adbkey = os.path.expanduser(r"~\.android\adbkey")
        self.host = host
        self.port = port
        self.adbkey = adbkey
        self.auth_timeout_s = auth_timeout_s
        self._signer: Optional[PythonRSASigner] = None
        self.device: Optional[AdbDeviceTcp] = None
        self._hwnd = find_window_by_title("Rogue Hearts")

    def click(self, xy: tuple[int, int]):
        click_in_window(self._hwnd, xy[0], xy[1], button="left", double=False)

    def get_frame(self):
        """screenshoot from Android trough ADB"""
        return self.device.shell("screencap -p", decode=False)

    def get_frame2(self):
        frame_bgr = screenshot_window_np(self._hwnd, client_only=True)
        return frame_bgr  # np.ndarray (H,W,3) BGR

    def _load_keys(self) -> None:
        if not os.path.exists(self.adbkey):
            raise FileNotFoundError(f"adbkey not found: {self.adbkey}")
        with open(self.adbkey, "r") as f:
            priv = f.read()
        with open(self.adbkey + ".pub", "r") as f:
            pub = f.read()
        self._signer = PythonRSASigner(pub, priv)

    def connect(self) -> "Device":
        """Connect to the device and return the underlying Device.

        Raises ConnectionError on failure.
        """
        if self.device is not None:
            try:
                if self.device.is_connected():
                    return self
            except Exception:
                # fall through and reconnect
                pass

        self._load_keys()
        device = AdbDeviceTcp(self.host, self.port)
        if not device.connect(
            rsa_keys=[self._signer], auth_timeout_s=self.auth_timeout_s
        ):
            raise ConnectionError(
                f"Failed to connect to device at {self.host}:{self.port}"
            )

        self.device = device
        logger.debug("Connected to device at %s:%s", self.host, self.port)
        self._hwnd = find_window_by_title("Rogue Hearts")
        return self

    def close(self) -> None:
        """Close the connection if open."""
        if self.device is not None:
            try:
                # AdbDeviceTcp has a close() method
                self.device.close()
            except Exception as e:
                logger.debug("Error while closing device: %s", e)
        self.device = None

    def __enter__(self) -> "Device":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.close()
        # don't suppress exceptions
        return False

    def force_stop_app(self, package_name: str) -> str:
        """Force stop an application by package name."""
        if self.device is None:
            raise ConnectionError("Device not connected")
        return self.device.shell(f"am force-stop {package_name}")

    def force_stop_rogue_hearts(self) -> str:
        """Force stop Rogue Hearts game."""
        package_name = "com.ninetailgames.roguehearts.paid"
        return self.force_stop_app(package_name)

    def start_app(self, package_name: str) -> str:
        """Start an application by package name."""
        if self.device is None:
            raise ConnectionError("Device not connected")
        return self.device.shell(
            f"monkey -p {package_name} -c android.intent.category.LAUNCHER 1"
        )

    def start_rogue_hearts(self) -> str:
        """Start Rogue Hearts game."""
        package_name = "com.ninetailgames.roguehearts.paid"
        return self.start_app(package_name)

    @staticmethod
    def start_rogue_hearts_wsa() -> str:
        """Start Rogue Hearts game using Windows Subsystem for Android."""
        wsa_client_path = os.path.expanduser(
            r"~\AppData\Local\Microsoft\WindowsApps\MicrosoftCorporationII.WindowsSubsystemForAndroid_8wekyb3d8bbwe\WsaClient.exe"
        )
        package_name = "com.ninetailgames.roguehearts.paid"

        try:
            result = subprocess.run(
                [wsa_client_path, "/launch", f"wsa://{package_name}"],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to start Rogue Hearts via WSA: {e.stderr}")
        except FileNotFoundError:
            raise FileNotFoundError(f"WSA Client not found at: {wsa_client_path}")


if __name__ == "__main__":
    device = Device("127.0.0.1", 58526)
    device.start_rogue_hearts_wsa()
