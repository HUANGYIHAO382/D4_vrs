# D4 自动善变识别

从暗黑4 善变界面截图中，自动识别背包里**需要善变**的物品，排除**已善变**和**空格**，并在待善变格子上生成半透明遮罩与编号。

当前阶段只做**识别 + 可视化标记**（截图测试），不含自动点击循环。

## 功能说明

1. **裁剪背包区域**：按 `config.yaml` 中的 `inventory_monitor` 从整屏截图裁出右下戒指栏。
2. **自动对齐网格**：`InventoryGridDetector` 用亮度投影 comb 拟合 11×3 格子坐标，避免固定间距带来的逐格漂移。
3. **逐格分类**：
   - `empty`：空格（近黑）
   - `done`：已善变（格子底部中央有骰子/猫头鹰小图标）
   - `pending`：待善变（有物品且无完成标志）
4. **输出遮罩图**：仅对 `pending` 叠加绿色半透明遮罩、绿框、序号。

## 环境

- Python 3.9+
- Windows（路径含中文截图时需本项目自带的 `image_io` 读写）
- 参考分辨率：**3840×2160** 善变界面（其它分辨率需重标 `config.yaml`）

```bash
cd E:\D4_OCR_PR
pip install -r requirements.txt
```

依赖：`opencv-python`、`numpy`、`pyyaml`（`mss` 预留给后续实时截屏，当前截图测试可不装）。

## 快速开始

将测试截图放到 `samples/`（例如 `samples/善变截图.png`），然后：

```bash
python main.py
```

或指定图片：

```bash
python main.py samples/你的截图.png
```

终端会打印：网格拟合结果、待善变数量、每个物品的行列与屏幕坐标。

输出目录 `samples/output/`：

| 文件 | 说明 |
|------|------|
| `*_overlay.png` | 待善变物品绿色遮罩 + 编号（主结果） |
| `*_grid.png` | 网格对齐与逐格分类（绿=P 待善变，红=D 已善变，灰=E 空格） |
| `*_mask.png` | 二值遮罩 |
| `*_full.png` | 全屏标注（背包 ROI 黄框 + overlay） |

## 配置说明（`config.yaml`）

| 段 | 关键字段 | 说明 |
|----|----------|------|
| `inventory_monitor` | left/top/width/height | 背包裁剪区（全屏坐标） |
| `inventory_grid` | cols/rows, x0/y0, pitch_x/pitch_y | 网格锚点；`auto_detect: true` 时自动拟合精确坐标 |
| `occupied` | value_mean, bright_ratio | 判断格子是否有物品 |
| `done_marker` | region, x_center, lower/upper_hsv, pixel_ratio | 已善变标志（底部中央小图标）检测 |
| `clicks` / `delays_ms` | — | 预留给后续自动点击，当前未使用 |

换分辨率或界面布局时，把 `inventory_grid` 的 `x0/y0/pitch` 大致改对即可，`auto_detect` 会在锚点附近自动对齐。

## 目录结构

```
D4_OCR_PR/
  config.yaml                 # 善变识别配置
  main.py                     # 入口（默认跑 samples/善变截图.png）
  requirements.txt
  scripts/
    test_transmute_image.py   # 截图测试脚本
  src/
    config.py                 # 配置读写
    image_io.py               # 中文路径图像读写
    inventory_grid.py         # 背包网格识别（通用，可复用）
    detector.py               # 善变逐格分类 + 遮罩
    coords.py                 # ROI → 屏幕坐标
  samples/                    # 测试截图（*.png 默认不上传 Git）
  docs/                       # 本地设计文档（默认不上传 Git）
```

## 模块分层

- **通用层** `inventory_grid.py`：只负责把背包解析成精确格子坐标，与业务无关。
- **业务层** `detector.py`：在格子上做占用 / 已善变 / 待善变判断，并生成遮罩。

其它功能（如识别太古词缀）可复用 `InventoryGridDetector`，单独新增判定模块即可。

## 验收参考（样张 `善变截图.png`）

- 网格 11×3 与装备栏对齐，右侧无累积漂移
- 待善变格有绿色遮罩与连续编号
- 底部带完成图标的格子不被标记
- 空格不标记

## 后续计划（未实现）

- 实时截屏 + 自动点击善变循环（放入 → 善变 → 清除 → 重扫）
- 太古词缀（武器小太阳）识别

## 常见问题

- **网格整体偏移**：调整 `inventory_grid` 的 `x0/y0`，保持 `auto_detect: true`。
- **已善变误判/漏判**：调 `done_marker.pixel_ratio` 或 `region` / `x_center` 取样条带。
- **空格被判成有物品**：提高 `occupied.value_mean` 或 `bright_ratio`。
- **中文路径读图失败**：确认使用本项目 `image_io.imread_unicode`，不要直接用 `cv2.imread`。
