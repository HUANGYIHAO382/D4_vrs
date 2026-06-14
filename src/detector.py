"""
善变物品检测（基于解耦的网格识别）。

分工：
- 几何（每个格子的精确坐标）来自 `src.inventory_grid.InventoryGridDetector`；
- 本模块只负责"逐格分类"这一善变业务逻辑，把每个格子判为：
    empty   空格（近黑、没有物品）
    done    已善变（格子底部中央存在骰子/猫头鹰小图标）
    pending 待善变（占用且没有完成标志）
最终只对 pending 生成半透明遮罩与编号，方便人工核对与后续自动点击。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from src.config import load_config
from src.coords import roi_to_screen
from src.inventory_grid import GridLayout, InventoryGridDetector, Slot


@dataclass
class Cell:
    """一个格子 + 它的分类结果（在 Slot 之上加了业务状态）。"""

    slot: Slot
    state: str = "empty"  # empty | done | pending
    index: int = 0        # 待善变物品的序号（从 1 开始；非 pending 为 0）

    @property
    def row(self) -> int:
        return self.slot.row

    @property
    def col(self) -> int:
        return self.slot.col

    @property
    def cx(self) -> int:
        return self.slot.cx

    @property
    def cy(self) -> int:
        return self.slot.cy

    def screen_center(self, monitor_left: int, monitor_top: int) -> tuple[int, int]:
        """格子中心换算成全屏坐标（供后续鼠标点击使用）。"""
        pt = roi_to_screen(self.cx, self.cy, monitor_left, monitor_top)
        return pt.x, pt.y


@dataclass
class ScanResult:
    """一次扫描的全部产物。"""

    pending: list[Cell]            # 待善变格（已排序、已编号）
    done_count: int                # 已善变格数量
    empty_count: int               # 空格数量
    inventory_bgr: np.ndarray      # 裁剪出的背包图
    pending_mask: np.ndarray       # 待善变格的二值遮罩
    overlay_bgr: np.ndarray        # 叠加了半透明遮罩+编号的可视化图
    layout: GridLayout             # 本次使用的网格布局
    cells: list[Cell] = field(default_factory=list)  # 全部格子（含分类）


class TransmuteDetector:
    def __init__(self, cfg: dict[str, Any] | None = None):
        self._cfg = cfg or load_config()
        self._mon = self._cfg["inventory_monitor"]
        # 网格几何全部交给解耦模块
        self._grid = InventoryGridDetector(self._cfg)
        self._pad = self._grid.cell_pad
        # 占用判定阈值
        self._occ = self._cfg["occupied"]
        # 已善变标志检测参数
        self._done = self._cfg["done_marker"]
        self._done_lo = np.array(self._done["lower_hsv"], dtype=np.uint8)
        self._done_hi = np.array(self._done["upper_hsv"], dtype=np.uint8)

    def crop_inventory(self, frame_bgr: np.ndarray) -> np.ndarray:
        """裁出背包区域（直接复用网格模块的实现）。"""
        return self._grid.crop_inventory(frame_bgr)

    # ---------- 取样辅助 ----------

    def _inner_patch(self, inv: np.ndarray, slot: Slot) -> np.ndarray:
        """取格子内缩 pad 后的图块（避开亮边框）。"""
        x0, y0, x1, y1 = slot.inner(self._pad)
        y0 = max(0, y0)
        y1 = min(inv.shape[0], y1)
        x0 = max(0, x0)
        x1 = min(inv.shape[1], x1)
        return inv[y0:y1, x0:x1]

    def _is_occupied(self, inv: np.ndarray, slot: Slot) -> bool:
        """判断格子是否有物品：平均亮度足够 且 亮像素比例足够（空格近黑）。"""
        patch = self._inner_patch(inv, slot)
        if patch.size == 0:
            return False
        v = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)[:, :, 2]
        value_mean = float(v.mean())
        bright_ratio = float(np.count_nonzero(v > 80) / v.size)
        return (
            value_mean >= float(self._occ["value_mean"])
            and bright_ratio >= float(self._occ["bright_ratio"])
        )

    def _done_strip_coords(self, slot: Slot) -> tuple[int, int, int, int]:
        """计算"已善变标志"取样条带坐标：格子底部一条、且只取水平中央。

        之所以只取底部中央：标志固定出现在卡片底部正中，而金属戒指主体在
        卡片中上部——把取样限制到底部中央可避免被亮戒指误判。
        """
        region = float(self._done.get("region", 0.18))     # 取底部高度的比例
        xc = self._done.get("x_center", [0.28, 0.72])       # 水平中央区段比例
        strip_h = max(1, int(slot.h * region))
        y1 = slot.y + slot.h - self._pad
        y0 = y1 - strip_h
        x0 = slot.x + int(slot.w * float(xc[0]))
        x1 = slot.x + int(slot.w * float(xc[1]))
        return x0, y0, x1, y1

    def _has_done_marker(self, inv: np.ndarray, slot: Slot) -> bool:
        """底部中央条带内，符合标志颜色（亮、低饱和）的像素比超过阈值则判已善变。"""
        x0, y0, x1, y1 = self._done_strip_coords(slot)
        y0 = max(0, y0)
        y1 = min(inv.shape[0], y1)
        x0 = max(0, x0)
        x1 = min(inv.shape[1], x1)
        strip = inv[y0:y1, x0:x1]
        if strip.size == 0:
            return False
        hsv = cv2.cvtColor(strip, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, self._done_lo, self._done_hi)
        ratio = np.count_nonzero(mask) / mask.size
        return ratio >= float(self._done["pixel_ratio"])

    # ---------- 主流程 ----------

    def scan(self, frame_bgr: np.ndarray) -> ScanResult:
        """扫描一帧：裁剪 → 识别网格 → 逐格分类 → 生成遮罩/可视化。"""
        inv = self.crop_inventory(frame_bgr)
        layout = self._grid.detect(inv)
        cells = [Cell(slot=s) for s in layout.slots()]

        pending: list[Cell] = []
        done = 0
        empty = 0
        for cell in cells:
            # 先判空格，再判是否已善变，剩下的就是待善变
            if not self._is_occupied(inv, cell.slot):
                cell.state = "empty"
                empty += 1
            elif self._has_done_marker(inv, cell.slot):
                cell.state = "done"
                done += 1
            else:
                cell.state = "pending"
                pending.append(cell)

        # 按 行优先 排序并编号，作为后续"挨个善变"的顺序
        pending.sort(key=lambda c: (c.row, c.col))
        for i, c in enumerate(pending):
            c.index = i + 1

        mask = self._pending_mask(inv, pending)
        overlay = self._build_overlay(inv, cells)
        return ScanResult(pending, done, empty, inv, mask, overlay, layout, cells)

    # ---------- 可视化 ----------

    def _pending_mask(self, inv: np.ndarray, pending: list[Cell]) -> np.ndarray:
        """把所有待善变格填成白色，得到二值遮罩。"""
        mask = np.zeros(inv.shape[:2], dtype=np.uint8)
        for c in pending:
            x0, y0, x1, y1 = c.slot.inner(self._pad)
            cv2.rectangle(mask, (x0, y0), (x1, y1), 255, -1)
        return mask

    def _build_overlay(self, inv: np.ndarray, cells: list[Cell]) -> np.ndarray:
        """生成可视化：待善变格盖半透明绿色 + 绿框 + 序号；已善变格淡红标注。"""
        overlay = inv.copy()
        tint = np.zeros_like(inv)
        tint[:] = (0, 200, 0)  # 绿色底
        pending_mask = self._pending_mask(inv, [c for c in cells if c.state == "pending"])
        m3 = cv2.cvtColor(pending_mask, cv2.COLOR_GRAY2BGR)
        # 在遮罩区域用 55%原图 + 45%绿色 混合，形成半透明效果
        blended = cv2.addWeighted(overlay, 0.55, tint, 0.45, 0)
        overlay = np.where(m3 > 0, blended, overlay)

        for c in cells:
            x0, y0, x1, y1 = c.slot.inner(self._pad)
            if c.state == "pending":
                cv2.rectangle(overlay, (x0, y0), (x1, y1), (0, 255, 0), 2)
                cv2.circle(overlay, (c.cx, c.cy), 4, (0, 0, 255), -1)
                cv2.putText(
                    overlay, str(c.index), (x0, max(y0 + 18, 16)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2, cv2.LINE_AA,
                )
            elif c.state == "done":
                cv2.rectangle(overlay, (x0, y0), (x1, y1), (60, 60, 180), 1)
                cv2.line(overlay, (x0, y0), (x1, y1), (40, 40, 160), 1)
        return overlay

    def draw_grid(self, inv: np.ndarray, cells: list[Cell]) -> np.ndarray:
        """调试图：画出每个格子框、逐格分类字母(E/D/P)、底部标志取样条带(品红)。"""
        out = inv.copy()
        color_map = {
            "empty": (120, 120, 120),
            "done": (0, 0, 255),
            "pending": (0, 255, 0),
        }
        for c in cells:
            color = color_map.get(c.state, (200, 200, 200))
            s = c.slot
            cv2.rectangle(out, (s.x, s.y), (s.x + s.w, s.y + s.h), color, 2)
            sx0, sy0, sx1, sy1 = self._done_strip_coords(s)
            cv2.rectangle(out, (sx0, sy0), (sx1, sy1), (255, 0, 255), 1)
            cv2.putText(
                out, c.state[0].upper(), (s.x + 4, s.y + 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA,
            )
        return out

    @property
    def inventory_monitor(self) -> dict[str, int]:
        """背包裁剪区（全屏坐标），供坐标换算/点击使用。"""
        m = self._mon
        return {k: int(m[k]) for k in ("top", "left", "width", "height")}
