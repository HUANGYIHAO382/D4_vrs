"""
对善变截图跑识别并输出遮罩/网格图。

用法:
    python scripts/test_transmute_image.py
    python scripts/test_transmute_image.py samples/善变截图.png
"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import load_config
from src.detector import TransmuteDetector
from src.image_io import imread_unicode, imwrite_unicode

DEFAULT_SAMPLE = ROOT / "samples" / "善变截图.png"


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SAMPLE
    out_dir = ROOT / "samples" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    frame = imread_unicode(path)
    if frame is None:
        raise FileNotFoundError(f"无法读取: {path}")

    h, w = frame.shape[:2]
    print(f"图像: {path.name}  {w}x{h}")

    cfg = load_config()
    inv_mon = cfg["inventory_monitor"]
    print(f"背包 ROI: {inv_mon}")

    det = TransmuteDetector(cfg)
    result = det.scan(frame)

    lay = result.layout
    mode = "自动拟合" if lay.auto else "固定几何(回退)"
    print(f"网格: {lay.cols}x{lay.rows}  {mode}  覆盖率={lay.score:.3f}")
    print(f"  列起点 x_starts={lay.x_starts}  单格宽={lay.cell_w}")
    print(f"  行起点 y_starts={lay.y_starts}  单格高={lay.cell_h}")
    print(f"待善变: {len(result.pending)} 件 | 已善变跳过: {result.done_count} | 空格: {result.empty_count}")
    for it in result.pending:
        sx, sy = it.screen_center(inv_mon["left"], inv_mon["top"])
        print(f"  #{it.index} 行列=({it.row},{it.col}) ROI=({it.cx},{it.cy}) 屏幕=({sx},{sy})")

    stem = path.stem
    imwrite_unicode(out_dir / f"{stem}_overlay.png", result.overlay_bgr)
    imwrite_unicode(out_dir / f"{stem}_mask.png", cv2.cvtColor(result.pending_mask, cv2.COLOR_GRAY2BGR))
    imwrite_unicode(out_dir / f"{stem}_grid.png", det.draw_grid(result.inventory_bgr, result.cells))

    full = frame.copy()
    x, y = inv_mon["left"], inv_mon["top"]
    iw, ih = inv_mon["width"], inv_mon["height"]
    cv2.rectangle(full, (x, y), (x + iw, y + ih), (255, 200, 0), 2)
    ov = result.overlay_bgr
    full[y : y + ov.shape[0], x : x + ov.shape[1]] = ov
    imwrite_unicode(out_dir / f"{stem}_full.png", full)
    print(f"输出目录: {out_dir}")


if __name__ == "__main__":
    main()
