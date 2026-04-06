# 把 Web 训练的 PyTorch 模型接到鸿蒙端（说明）

## 为什么不能「直接跑 .pth」

- 鸿蒙 **ArkTS 里不能执行 Python，也不能加载 PyTorch**。
- `.pth` 必须在 **别的运行时**里跑，常见两条路：
  1. **端侧**：把模型转成 **MindSpore Lite 的 `.ms`**（或 ONNX→再转 `.ms`），用 **MindSpore Lite**（ArkTS Kit 或 C++）推理。
  2. **服务端**：继续用 Flask（你现在的 `app.py`），手机只发图——这是「联网推理」，不是「模型进手机」。

本仓库已按 **端侧移植** 准备 **ONNX 导出**，方便你再走华为转换工具。

## 第一步：在电脑上导出 ONNX

```bash
cd web_app
python scripts/export_models_to_onnx.py
```

生成目录：`web_app/exported_onnx/`（含 `*.onnx` 与 `labels_*.json`）。

## 第二步：转成鸿蒙可用的 `.ms`

在 **安装 MindSpore Lite 模型转换工具** 的电脑上（版本需与目标设备/文档一致）：

- 将对应 `*.onnx` 转为 **MindSpore Lite `.ms`**（具体命令以华为当前文档为准，关键词：ONNX 转 MindSpore Lite）。
- 将生成的 `.ms` 拷贝到鸿蒙工程：`entry/src/main/resources/rawfile/`（例如 `demo1.ms`）。

## 第三步：在 App 里推理

- **HarmonyOS NEXT / 较高 API**：若工程已支持 **`@kit.MindSporeLiteKit`**，可在 ArkTS 中 `loadModelFromFile` + `predict`（以你当前 SDK 文档为准）。
- **API 9 / 老工程**：往往 **没有** 上述 ArkTS Kit，需要：
  - **升级工程与 SDK** 到文档支持 MindSpore Lite Kit 的版本，或  
  - 使用 **Native C++** 集成 MindSpore Lite C++ API，再通过 **NAPI** 暴露给 ArkTS。

本鸿蒙工程中的 **`OnDeviceModelRunner.ets`** 为接入点占位；**`ImageNet224Preprocessor.ets`** 提供与训练侧一致的 **224 + ImageNet 归一化** 预处理（与 `Resize(256)+CenterCrop(224)` 略有差异时，可再改预处理对齐）。

## 与页面 scene 的对应关系

| 页面 scene | 建议 rawfile 模型名 | 对应导出 key |
|------------|---------------------|--------------|
| maturity   | demo1.ms            | demo1        |
| crop       | demo2.ms            | demo2        |
| disease    | apple_disease.ms    | apple_disease |

在 `FarmConfig` 中打开 `useOnDeviceInference` 后，需在 `OnDeviceModelRunner` 内按你 SDK 实际 API 补全加载与推理（当前 API 9 默认仍会提示未完成 Native/Kit 集成）。
