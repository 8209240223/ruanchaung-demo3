# 苹果检测模型说明

## 框选优先模式（video_processor.py 中 APPLE_ACCURACY_FIRST=True）

- 优先保证**苹果框选准确**：YOLOv8m + 多尺度 1280/640，每 2 帧检测
- 成熟度/病害识别精度次要
- 若需更快速度，将 `APPLE_ACCURACY_FIRST = False`，则用 YOLOv8n + 单尺度 640

## 当前检测优先级

1. **自定义模型**（最精准）：将 `.pt` 文件放到 `web_app/models/apple_detection.pt`
2. **框选优先**：YOLOv8m > s > n + 多尺度；**速度优先**：YOLOv8n > s > m + 单尺度

## 如何获取更精准的苹果检测模型

### 方式一：Roboflow Universe（推荐）

1. 打开 [Roboflow Universe - apples](https://universe.roboflow.com/roboflow-100/apples-fvpl5)
2. 或 [Apple detection yolo](https://universe.roboflow.com/the-pennsylvania-state-university/apple-detection-yolo)
3. 选择 **YOLOv8** 格式导出，下载 `.pt` 权重
4. 重命名为 `apple_detection.pt`，放入 `web_app/models/` 目录

### 方式二：MinneApple 数据集训练

- 数据集：https://github.com/nicolaihaeni/MinneApple
- 参考：https://github.com/joy0010/Apple-Detection-in-MinneApple-Dataset-with-YOLOv8
- 训练后导出 `best.pt`，重命名为 `apple_detection.pt` 放入本目录

### 方式三：自训练

使用自己的果园苹果标注数据，用 YOLOv8 训练后导出权重，放入本目录即可。

## 类别说明

- **COCO 通用模型**：仅检测 apple（类别 47）
- **自定义模型**：支持 apple(0)、damaged_apple(1) 等多类别，系统会自动识别
