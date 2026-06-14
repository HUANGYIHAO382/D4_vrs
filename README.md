# D4 视觉中枢（HSV 掩膜）

游戏内染色掉落物 + HSV 纯色掩膜，将屏幕 ROI 内的目标识别为屏幕坐标 `(screen_x, screen_y)`。本阶段只做「眼」，不含点击、寻路、打怪。

## 环境

- Python 3.10+
- Windows，游戏在前台；默认 **1920×1080**，ROI 为屏幕中央 800×800

```bash
cd e:\D4_OCR_PR
pip install -r requirements.txt
```

## 前置条件

1. 在游戏设置里把目标掉落物（如源生粉尘）改成单一高对比色（荧光洋红、青色等）。
2. 窗口模式或无边框全屏，避免 ROI 裁到黑边。
3. 游戏在主显示器时，`config.yaml` 中 `monitor.left/top` 一般无需改；副屏需加上显示器偏移。

## 使用流程

### 1. HSV 标定（必须先做）

```bash
python tools/hsv_picker.py
```

- 把游戏画面放在 ROI 内，地上要有染色掉落物。
- 拖动 **H_min / S_min / V_min / H_max / S_max / V_max**，直到 **Mask** 窗口里目标为连贯白块、背景几乎全黑。
- 按 **s** 保存到 `config.yaml`；**p** 在终端打印数组；**q** 退出。

**色相环绕**：目标接近红色时，H 可能在 0 与 170 两端；本工具仅支持单段 `inRange`，可放宽 H 范围或换一种染色。

### 2. 运行视觉管线

```bash
python main.py
```

- 绿框 + 红点标出当前**面积最大**的目标。
- 终端输出 ROI 局部坐标与屏幕绝对坐标。
- **q** 退出。

`config.yaml` 中 `debug: false` 可关闭 `imshow` 以提升 FPS（仍打印日志）。

## 配置说明

| 字段 | 说明 |
|------|------|
| `monitor` | mss ROI：`top`, `left`, `width`, `height` |
| `lower_hsv` / `upper_hsv` | OpenCV HSV 阈值（H:0–179, S/V:0–255） |
| `min_area` | 轮廓最小面积（像素²），过滤噪点 |
| `kernel_size` / `dilate_iterations` | 掩膜膨胀，粘连物品名字底板 |
| `debug` | 是否显示调试窗口 |
| `log_interval_frames` | 每隔多少帧打印一次坐标与耗时 |

## 验收清单（游戏内实机）

| 项 | 标准 |
|----|------|
| 掩膜干净度 | Mask 中目标为整块白，UI/地面无大块误检 |
| 红点稳定性 | 同一件掉落物 3–5 秒内中心抖动约 &lt; 5px |
| 坐标正确性 | 红点落在名称/光柱视觉中心；屏幕坐标抽查合理 |
| 性能 | ROI 800×800 单循环宜 &lt; 30ms |
| 配置复用 | 只改 yaml 即可调 `min_area`、形态学、HSV |

## 常见问题

- **误检多**：收紧 `S_min`/`V_min`，或增大 `min_area`。
- **目标断裂**：略增 `dilate_iterations` 或 `kernel_size`。
- **漏检**：放宽 H/S/V 范围，或确认游戏内染色已生效。
- **ROI 不对**：按分辨率重算中央区域，修改 `monitor`。

## 目录结构

```
D4_OCR_PR/
  config.yaml
  requirements.txt
  main.py
  src/
    capture.py      # mss 截屏
    vision.py       # HSV 掩膜与轮廓
    coords.py       # 坐标换算
    config_utils.py # 配置读写
  tools/
    hsv_picker.py   # HSV 标定
```

## 后续扩展（未实现）

1. 屏幕坐标 → 外设/Win32 点击  
2. 多目标优先级与拾取重试  
3. 寻路/站位（与视觉解耦）
