# 智能农业果园平台（demo3）

一个基于 Flask 的智能农业全栈演示项目，聚焦果园场景，提供识别诊断、任务规划、视频分析、无人机调度、气象预警和后台管理等能力。  
项目后端与前端页面统一在 `web_app` 目录中，适合课程展示、功能联调和本地演示。

## 功能概览

- 用户登录/注册与基础权限控制
- 首页大屏与管理后台数据看板
- 果园地图展示与作业区域配置
- 作业任务规划与无人机资源分配
- 图片识别（成熟度、病虫害）与诊断建议
- 视频分析任务提交、状态查询、结果回放
- 风险预警、灌溉建议、历史记录查询
- 农业助手接口（对话式辅助）

## 技术栈

- 后端：Flask、Flask-SocketIO、Werkzeug
- 视觉与推理：PyTorch、TorchVision、OpenCV、Ultralytics
- 数据存储：SQLite（默认本地文件）
- 前端：HTML + CSS + JavaScript（模板在 `web_app/templates`）

## 目录结构

```text
demo3/
├─ web_app/
│  ├─ app.py                    # Flask 统一入口
│  ├─ requirements.txt          # Python 依赖
│  ├─ unified_model_loader.py   # 模型加载与配置
│  ├─ unified_predict.py        # 统一推理逻辑
│  ├─ video_processor.py        # 视频分析逻辑
│  ├─ templates/                # 页面模板
│  ├─ static/                   # 前端静态资源
│  ├─ data/                     # 果园地块数据（geojson）
│  └─ models/                   # 模型说明与权重放置位置
├─ docs/                        # 架构说明等文档
└─ README.md
```

## 快速开始（Windows）

### 1. 创建并激活虚拟环境

```powershell
cd web_app
py -m venv .venv
.\.venv\Scripts\activate
```

### 2. 安装依赖

```powershell
pip install -r requirements.txt
```

### 3. 启动服务

```powershell
py app.py
```

默认访问地址：

- 本机：`http://127.0.0.1:5000`
- 局域网：`http://<你的IP>:5000`

也可以使用脚本启动：

- `web_app/run_orchard.bat`
- `web_app/run_orchard.ps1`

## 关键环境变量（可选）

- `APP_HOST`：监听地址（默认 `0.0.0.0`）
- `APP_PORT`：端口（默认 `5000`）
- `APP_AUTO_OPEN_BROWSER`：是否自动打开浏览器（`1/0`）
- `AMAP_JS_KEY`：高德地图 JS Key（地图功能建议配置自己的 Key）

## 默认数据与账号说明

- 首次运行会自动初始化 SQLite 数据库与基础表
- 演示环境会初始化默认管理员账号（见 `web_app/app.py`）
- 生产环境请务必自行修改默认账号和密钥配置

## 常见问题

- 端口被占用：先关闭占用 `5000` 端口的进程再启动
- 模型加载失败：确认模型文件路径与依赖版本匹配
- 页面中文乱码：终端使用 UTF-8（项目已在 Windows 做兼容处理）

## 免责声明

本项目主要用于课程实验与演示，不直接面向生产环境。  
如需上线，请补充鉴权安全、日志审计、异常恢复、部署编排和监控告警等能力。
