"""
支持 Unicode 路径的图像读写。

为什么需要：Windows 上 OpenCV 的 `cv2.imread` / `cv2.imwrite` 在路径里含有
中文（如 "善变截图.png"）时会失败（底层用的是 ANSI 路径）。这里用
`numpy.fromfile` 先把文件读成字节流，再交给 `cv2.imdecode` 解码，从而绕开
路径编码问题。写出同理（`imencode` + `tofile`）。
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def imread_unicode(path: Path | str) -> np.ndarray | None:
    """读取图像为 BGR ndarray；路径不存在或解码失败返回 None。"""
    p = Path(path)
    if not p.is_file():
        return None
    # 以字节流方式读盘，避免 cv2 直接吃中文路径报错
    data = np.fromfile(str(p), dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def imwrite_unicode(path: Path | str, bgr: np.ndarray) -> bool:
    """写出 BGR 图像到（可能含中文的）路径；成功返回 True。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    ext = p.suffix or ".png"
    # 先编码到内存缓冲，再用 tofile 落盘，绕开中文路径
    ok, buf = cv2.imencode(ext, bgr)
    if not ok:
        return False
    buf.tofile(str(p))
    return True
