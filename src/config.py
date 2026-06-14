"""
善变项目配置读写（config.yaml）。

设计要点：
- `default_config()` 给出全部默认值，是配置的"单一事实来源"。
- `load_config()` 读 YAML 后与默认值做"深合并"：缺失的键自动用默认值补齐，
  因此即使 config.yaml 只写了一部分字段也能正常工作。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import yaml

# 配置文件默认位置：项目根目录下的 config.yaml
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


def default_config() -> dict[str, Any]:
    """返回一份完整的默认配置（实机请用 config.yaml 覆盖）。"""
    return {
        # 背包裁剪区（全屏坐标系）
        "inventory_monitor": {
            "left": 2362,
            "top": 1283,
            "width": 1402,
            "height": 766,
        },
        # 网格几何 + 自动对齐参数（裁剪区局部坐标）
        "inventory_grid": {
            "cols": 11,
            "rows": 3,
            "x0": 177,
            "y0": 166,
            "pitch_x": 110,
            "pitch_y": 162,
            "cell_w": 100,
            "cell_h": 153,
            "cell_pad": 8,
            "auto_detect": True,
            "value_thresh": 52,
            "auto_min_score": 0.40,
        },
        # 占用判定阈值（区分空格 / 有物品）
        "occupied": {
            "value_mean": 45,
            "bright_ratio": 0.12,
        },
        # 已善变标志（格子底部中央小图标）检测参数
        "done_marker": {
            "region": 0.18,
            "x_center": [0.28, 0.72],
            "lower_hsv": [0, 0, 120],
            "upper_hsv": [179, 110, 255],
            "pixel_ratio": 0.06,
        },
        # 旧颜色管线参数（保留兼容，当前网格方案不使用）
        "min_area": 800,
        "max_area": 12000,
        "kernel_size": 3,
        "dilate_iterations": 0,
        # 自动点击坐标（后续自动循环用）
        "clicks": {
            "transmute": [1200, 700],
            "clear": [1300, 700],
        },
        # 各步骤间延时（毫秒）
        "delays_ms": {
            "after_pick": 250,
            "after_transmute": 700,
            "after_clear": 450,
            "between_items": 350,
            "countdown_sec": 3,
        },
    }


def load_config(path: Path | str | None = None) -> dict[str, Any]:
    """加载配置：文件不存在直接返回默认值；存在则与默认值深合并。"""
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not config_path.is_file():
        return default_config()
    with config_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    base = default_config()
    # 这些键是嵌套字典，做 update（只覆盖用户写了的子键，其余保留默认）
    merge_keys = {"clicks", "delays_ms", "inventory_grid", "occupied", "done_marker"}
    for k, v in data.items():
        if k in merge_keys and isinstance(v, dict) and isinstance(base.get(k), dict):
            base[k].update(v)
        elif k == "inventory_monitor" and isinstance(v, dict):
            base["inventory_monitor"] = dict(v)
        else:
            base[k] = v
    return base


def save_config(data: dict[str, Any], path: Path | str | None = None) -> None:
    """把配置写回 YAML（保留中文、块状格式）。"""
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    with config_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, default_flow_style=False)


def hsv_pair(cfg: dict[str, Any], prefix: str) -> tuple[np.ndarray, np.ndarray]:
    """把 `{prefix}_lower_hsv` / `{prefix}_upper_hsv` 取出为两个 uint8 数组。"""
    return (
        np.array(cfg[f"{prefix}_lower_hsv"], dtype=np.uint8),
        np.array(cfg[f"{prefix}_upper_hsv"], dtype=np.uint8),
    )
