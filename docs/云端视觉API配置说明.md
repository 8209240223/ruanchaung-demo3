# 云端 AI 病虫害识别配置指南

## 功能说明

病虫害诊断页面可集成**云端大模型**，上传图片后调用视觉 API 进行智能分析。

## 配置步骤（环境变量，推荐）

1. **获取 API 密钥**  
   火山引擎：<https://www.volcengine.com/> — 控制台创建密钥。

2. **设置环境变量**

   ```powershell
   # Windows PowerShell（当前会话）
   $env:DOUBAO_API_KEY="你的API密钥"
   ```

   ```bash
   # Linux / macOS
   export DOUBAO_API_KEY="你的API密钥"
   ```

   可选：`DOUBAO_API_ENDPOINT`、`DOUBAO_MODEL`（默认值见 `web_app/orchard_backend/doubao_config.py`）。

3. **启动服务**（在 `web_app` 目录）

   ```powershell
   py app.py
   ```

**请勿将真实密钥写入仓库代码。** 公开仓库中只能使用环境变量或本机私密配置。

## 使用方法

1. 打开：`http://127.0.0.1:5000/病虫害`
2. 上传图片并开始 AI 诊断
3. 等待云端返回（通常数秒到十余秒）

## 注意事项

- API 配额与网络需可用
- 图片建议 JPG/PNG，大小参考接口限制

## 故障排查

- 提示密钥未配置：检查是否已设置 `DOUBAO_API_KEY`
- 调用失败：核对密钥、网络、配额

## 相关代码

- `web_app/orchard_backend/doubao_config.py`：读取环境变量与默认端点
- `web_app/app.py`：`call_doubao_api` / `call_doubao_api_with_prompt`
- 官方文档：<https://www.volcengine.com/docs/82379>
