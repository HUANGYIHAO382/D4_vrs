"""
背包格网格识别（解耦、与具体业务无关）。

职责：把一张"已裁剪好的背包区域图像"解析成规整的格子网格（行 x 列），
输出每个格子的精确像素坐标。任何上层功能（自动善变、批量出售、词缀识别等）
都可以复用本模块拿到格子坐标，再各自实现"逐格判断"。

核心思路（为什么不直接 x0 + 列号*pitch 外推）：
    固定外推一旦 pitch 有零点几像素误差，就会逐格累积，越往后偏得越多。
    本模块改用 comb（梳状模板）在"卡片亮度投影"上做全局拟合：
    在锚点附近搜索一组 (起点 start, 间距 pitch, 单格尺寸 size)，使得 N 个等距
    梳齿覆盖到的平均亮度最大。它拟合的是整排的周期结构，对单卡反光裂开、
    面板边框等局部噪声不敏感，且 pitch 是全局最优 → 没有累积漂移。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np


@dataclass
class Slot:
    """单个背包格（坐标均为裁剪区局部坐标）。"""

    row: int
    col: int
    x: int
    y: int
    w: int
    h: int

    @property
    def cx(self) -> int:
        """格子中心 x。"""
        return self.x + self.w // 2

    @property
    def cy(self) -> int:
        """格子中心 y。"""
        return self.y + self.h // 2

    def inner(self, pad: int) -> tuple[int, int, int, int]:
        """向内收缩 pad 像素后的 (x0, y0, x1, y1)，用于避开亮边框取样。"""
        return (self.x + pad, self.y + pad, self.x + self.w - pad, self.y + self.h - pad)


@dataclass
class GridLayout:
    """一次识别得到的整张网格布局。"""

    cols: int
    rows: int
    x_starts: list[int]  # 每一列的左边缘 x（长度 = cols）
    y_starts: list[int]  # 每一行的上边缘 y（长度 = rows）
    cell_w: int
    cell_h: int
    auto: bool = False    # True=自动拟合得到；False=固定几何回退
    score: float = 0.0    # 自动拟合的覆盖率得分（越高越可信）

    def slots(self) -> list[Slot]:
        """把行列起点展开成全部 Slot（按 行优先 顺序）。"""
        out: list[Slot] = []
        for r in range(self.rows):
            for c in range(self.cols):
                out.append(
                    Slot(row=r, col=c, x=self.x_starts[c], y=self.y_starts[r], w=self.cell_w, h=self.cell_h)
                )
        return out


@dataclass
class _AxisFit:
    """单个轴（横/纵）的拟合结果。"""

    start: int
    pitch: int
    size: int
    score: float


def _comb_fit(profile: np.ndarray, n: int, start_rng: range, pitch_rng: range, size_rng: range) -> _AxisFit | None:
    """用 n 个等距矩形（梳）在一维覆盖率投影上做全局最优拟合。

    参数:
        profile:   一维"卡片像素占比"投影（值域约 0~1）。
        n:         期望的格子数（该轴上的列数或行数）。
        *_rng:     start/pitch/size 的搜索范围（在配置锚点附近展开）。
    返回:
        最优 (start, pitch, size, score)；profile 为空或 n<=0 时返回 None。

    实现用前缀和把"任意区间求和"降到 O(1)，整体复杂度 = 搜索网格大小 * n。
    """
    if n <= 0 or profile.size == 0:
        return None
    # 前缀和：prefix[i] = profile[0..i-1] 之和，便于 O(1) 求区间和
    prefix = np.concatenate([[0.0], np.cumsum(profile.astype(np.float64))])
    length = profile.size

    def seg_sum(a: int, b: int) -> float:
        a = max(0, min(length, a))
        b = max(0, min(length, b))
        return float(prefix[b] - prefix[a])

    best: _AxisFit | None = None
    for size in size_rng:
        if size <= 0:
            continue
        for pitch in pitch_rng:
            if pitch < size:  # 间距必须不小于单格宽，否则梳齿重叠没意义
                continue
            for start in start_rng:
                end = start + (n - 1) * pitch + size
                if start < 0 or end > length:  # 整把梳必须落在 profile 内
                    continue
                # 累加 n 个梳齿覆盖到的亮度总量
                total = 0.0
                for i in range(n):
                    a = start + i * pitch
                    total += seg_sum(a, a + size)
                score = total / (n * size)  # 归一化为"平均覆盖率"
                if best is None or score > best.score:
                    best = _AxisFit(start=start, pitch=pitch, size=size, score=score)
    return best


def _around(center: int, span: int, step: int = 1) -> range:
    """生成 [center-span, center+span] 的搜索范围。"""
    return range(int(center - span), int(center + span + 1), step)


class InventoryGridDetector:
    """从背包裁剪图识别格子网格；可独立于任何业务功能复用。"""

    def __init__(self, cfg: dict[str, Any]):
        # 裁剪区（全屏坐标）
        self._mon = cfg["inventory_monitor"]
        # 网格几何 + 自动对齐参数
        g = cfg["inventory_grid"]
        self._cols = int(g["cols"])
        self._rows = int(g["rows"])
        self._x0 = int(g["x0"])
        self._y0 = int(g["y0"])
        self._pitch_x = int(g["pitch_x"])
        self._pitch_y = int(g["pitch_y"])
        self._cell_w = int(g["cell_w"])
        self._cell_h = int(g["cell_h"])
        self._pad = int(g.get("cell_pad", 0))
        self._auto = bool(g.get("auto_detect", True))
        self._value_thresh = int(g.get("value_thresh", 52))
        self._min_score = float(g.get("auto_min_score", 0.40))

    @property
    def cell_pad(self) -> int:
        """取样内缩像素（供上层逐格分析时复用）。"""
        return self._pad

    def crop_inventory(self, frame_bgr: np.ndarray) -> np.ndarray:
        """从整帧里裁出背包区域。

        若传入图像本身尺寸≈裁剪区尺寸（说明已是裁好的图），则直接返回拷贝；
        否则按 inventory_monitor 的 top/left/width/height 裁剪。
        """
        eh, ew = int(self._mon["height"]), int(self._mon["width"])
        fh, fw = frame_bgr.shape[:2]
        if abs(fh - eh) <= 2 and abs(fw - ew) <= 2:
            return frame_bgr.copy()
        t, l = int(self._mon["top"]), int(self._mon["left"])
        return frame_bgr[t : t + eh, l : l + ew].copy()

    def _fixed_layout(self) -> GridLayout:
        """固定几何：直接用配置的 x0/pitch 外推（自动拟合失败时的回退）。"""
        x_starts = [self._x0 + c * self._pitch_x for c in range(self._cols)]
        y_starts = [self._y0 + r * self._pitch_y for r in range(self._rows)]
        return GridLayout(
            cols=self._cols, rows=self._rows, x_starts=x_starts, y_starts=y_starts,
            cell_w=self._cell_w, cell_h=self._cell_h, auto=False, score=0.0,
        )

    def detect(self, inventory_bgr: np.ndarray) -> GridLayout:
        """识别网格：开启 auto_detect 则 comb 拟合，否则用固定几何。"""
        if not self._auto:
            return self._fixed_layout()

        ih, iw = inventory_bgr.shape[:2]
        # 卡片掩膜：亮度 V 大于阈值视为"卡片像素"（空隙/背景近黑）
        v = cv2.cvtColor(inventory_bgr, cv2.COLOR_BGR2HSV)[:, :, 2]
        card = (v > self._value_thresh).astype(np.float32)

        # 列拟合：只在卡片所在的"纵向带"内投影，避开顶部标题/快捷栏
        y_lo = max(0, self._y0)
        y_hi = min(ih, self._y0 + self._rows * self._pitch_y)
        col_profile = card[y_lo:y_hi, :].mean(axis=0)  # 每个 x 的卡片占比
        col_fit = _comb_fit(
            col_profile, self._cols,
            start_rng=_around(self._x0, 15),
            pitch_rng=_around(self._pitch_x, 6),
            size_rng=_around(self._cell_w, 10, 2),
        )

        # 行拟合：只在卡片所在的"横向带"内投影
        x_lo = max(0, self._x0)
        x_hi = min(iw, self._x0 + self._cols * self._pitch_x)
        row_profile = card[:, x_lo:x_hi].mean(axis=1)  # 每个 y 的卡片占比
        row_fit = _comb_fit(
            row_profile, self._rows,
            start_rng=_around(self._y0, 18),
            pitch_rng=_around(self._pitch_y, 8),
            size_rng=_around(self._cell_h, 12, 2),
        )

        # 拟合失败或覆盖率过低 → 回退固定几何，保证不会"全乱"
        if (
            col_fit is None or row_fit is None
            or col_fit.score < self._min_score or row_fit.score < self._min_score
        ):
            return self._fixed_layout()

        # 用拟合出的（全局最优、无漂移）起点+间距生成每列/每行坐标
        x_starts = [col_fit.start + c * col_fit.pitch for c in range(self._cols)]
        y_starts = [row_fit.start + r * row_fit.pitch for r in range(self._rows)]
        return GridLayout(
            cols=self._cols, rows=self._rows, x_starts=x_starts, y_starts=y_starts,
            cell_w=col_fit.size, cell_h=row_fit.size, auto=True,
            score=min(col_fit.score, row_fit.score),
        )

    def slots(self, inventory_bgr: np.ndarray) -> list[Slot]:
        """便捷接口：直接拿到全部格子。"""
        return self.detect(inventory_bgr).slots()

    def draw(self, inventory_bgr: np.ndarray, layout: GridLayout | None = None) -> np.ndarray:
        """调试：在图上画出网格框。"""
        layout = layout or self.detect(inventory_bgr)
        out = inventory_bgr.copy()
        for s in layout.slots():
            cv2.rectangle(out, (s.x, s.y), (s.x + s.w, s.y + s.h), (0, 255, 0), 2)
        return out
