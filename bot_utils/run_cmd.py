import subprocess
from typing import Optional


def run_cmd(cmd, timeout: Optional[float] = 5.0) -> str:
    """Запустить команду и вернуть stdout как строку (без исключений)."""
    try:
        out = subprocess.check_output(cmd, shell=True, timeout=timeout)
        return out.decode("utf-8", errors="ignore").strip()
    except Exception as e:
        return f""