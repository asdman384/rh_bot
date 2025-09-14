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
