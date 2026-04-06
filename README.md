# 智能农业果园平台（demo3）

基于 Flask 的果园场景演示项目：识别诊断、任务规划、视频分析、无人机调度、气象预警与后台管理等。业务入口在 `web_app`，核心 Python 逻辑集中在包 `orchard_backend`。

## 功能概览

- 用户登录/注册与基础权限
- 大屏与管理后台
- 果园地图与作业配置
- 任务规划与无人机分配
- 图像识别（成熟度、病虫害）与用药/气象等页面
- 视频分析任务与 WebSocket
- 云端视觉 API（需配置环境变量）

## 技术栈

- Flask、Flask-SocketIO、SQLite
- PyTorch、TorchVision、OpenCV、Ultralytics（YOLO）

## 目录结构

```text
demo3/
├─ web_app/
│  ├─ app.py                 # Flask 入口
│  ├─ orchard_backend/       # 后端核心包
│  │  ├─ model_loader.py     # 模型结构与路径、加载
│  │  ├─ predict.py          # 统一图像推理
│  │  ├─ video_processor.py  # 视频 / YOLO 检测与批推理
│  │  └─ doubao_config.py    # 云端 API（读环境变量）
│  ├─ training/              # 训练脚本与叶片数据集、导出的 .pth
│  ├─ scripts/               # ONNX 导出等工具脚本
│  ├─ templates/  static/
│  ├─ data/                  # 如 orchard.geojson；运行时 captures 等
│  └─ models/                  # YOLO 权重、可选 apple_detection.pt 等
├─ docs/                     # 架构图、API 说明、技术文档
└─ README.md
```

## 快速开始（Windows）

```powershell
cd web_app
py -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
py app.py
```

- 本机：<http://127.0.0.1:5000>  
- 亦可使用 `run_orchard.bat` / `run_orchard.ps1`

## 环境变量（节选）

| 变量 | 说明 |
|------|------|
| `APP_HOST` / `APP_PORT` | 监听地址与端口 |
| `APP_AUTO_OPEN_BROWSER` | `1`/`0` 是否自动打开浏览器 |
| `AMAP_JS_KEY` | 高德地图 JS Key |
| `DOUBAO_API_KEY` | 火山方舟等云端视觉 API（病虫害云端诊断） |

云端配置详见 `docs/云端视觉API配置说明.md`。

## 模型与权重

- 成熟度 / 多水果分类：可来自上级目录的 `demo1`、`demo2` 工程（路径在 `model_loader.py` 中配置）
- 苹果叶片 / 果实病害：`training/processed_dataset/best_model.pth`、`training/fruit_processed_dataset/best_model.pth`
- 视频框苹果：优先 `models/apple_detection.pt`，否则使用 `models/yolov8n.pt` / `yolov8m.pt`（可放入 `models/`）

## 说明

- 首次运行会初始化本地 SQLite 与演示账号（见 `app.py`）；正式环境请修改默认账号并妥善保管密钥。
- 课程/演示用途为主；上线需补强安全、审计与运维。
