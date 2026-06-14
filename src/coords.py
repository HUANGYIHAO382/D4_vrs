"""ROI 局部坐标 → 屏幕绝对坐标。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ScreenPoint:
    x: int
    y: int


def roi_to_screen(cx: int, cy: int, monitor_left: int, monitor_top: int) -> ScreenPoint:
    """把裁剪区内的局部坐标 (cx, cy) 加上裁剪区左上角偏移，换算成全屏坐标。"""
    return ScreenPoint(x=monitor_left + cx, y=monitor_top + cy)
