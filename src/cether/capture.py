"""Real screen capture and foreground app lookup for Windows.

The screenshot is converted to an 8x8 grayscale thumbnail in memory and the
full image is dropped. Nothing is written to disk.
"""

from __future__ import annotations

import ctypes
import io
import os
from ctypes import wintypes

from PIL import Image

from .perception import Thumbnail

HASH_SIZE = 8


def to_thumbnail(image: Image.Image) -> Thumbnail:
    small = image.convert("L").resize((HASH_SIZE, HASH_SIZE), Image.Resampling.BILINEAR)
    return list(small.getdata())


def grab_primary_monitor() -> tuple[Thumbnail, bytes]:
    """Return the thumbnail and a PNG of the primary monitor. Both stay in memory."""
    import mss

    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[1])
        image = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    try:
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return to_thumbnail(image), buf.getvalue()
    finally:
        image.close()


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def foreground_app() -> str:
    """Return the executable base name of the foreground window, or '' if none."""
    hwnd = _user32.GetForegroundWindow()
    if not hwnd:
        return ""
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if not _kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return ""
        return os.path.splitext(os.path.basename(buf.value))[0].lower()
    finally:
        _kernel32.CloseHandle(handle)
