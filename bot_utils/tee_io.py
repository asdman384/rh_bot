import io
from collections import deque


class _TeeIO(io.TextIOBase):
    """A simple tee stream that writes to the real stream and stores lines in a deque.

    Notes:
    - Designed to be used with contextlib.redirect_stdout / redirect_stderr.
    - Captures full lines; partial fragments are buffered until a newline arrives.
    - Thread-safe minimal locking; captures approximate sequence under concurrency.
    """

    def __init__(self, line_buffer: deque[str], real_stream, label: str | None = None):
        from threading import Lock

        self._lines = line_buffer
        self._real = real_stream
        self._label = label or ""
        self._partial = ""
        self._lock = Lock()

    def writable(self):
        return True

    def write(self, s: str):
        if not isinstance(s, str):
            s = str(s)
        with self._lock:
            # Always forward to real stream
            try:
                self._real.write(s)
            except Exception:
                pass

            self._partial += s
            while "\n" in self._partial:
                line, self._partial = self._partial.split("\n", 1)
                # Store captured line (with optional label)
                if self._label:
                    self._lines.append(f"{self._label}{line}")
                else:
                    self._lines.append(line)
        return len(s)

    def flush(self):
        with self._lock:
            try:
                self._real.flush()
            except Exception:
                pass
            # If there is a partial line pending, keep it until newline arrives.
