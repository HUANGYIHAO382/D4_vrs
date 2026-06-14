"""
D4 自动善变 — 入口。

当前阶段用于对截图测试识别与遮罩生成：
    python main.py                      # 跑默认样张 samples/善变截图.png
    python main.py samples/xxx.png      # 指定截图
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.test_transmute_image import main

if __name__ == "__main__":
    main()
