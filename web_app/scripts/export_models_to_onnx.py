# -*- coding: utf-8 -*-
"""
将 web_app 已训练的 PyTorch 模型导出为 ONNX，供鸿蒙端 MindSpore Lite 等工具继续转换为 .ms 端侧推理。

用法（在 web_app 目录下）:
  python scripts/export_models_to_onnx.py

输出目录: web_app/exported_onnx/
  - demo1.onnx / demo2.onnx / apple_disease.onnx / apple_fruit_disease.onnx（存在权重才导出）
  - labels_*.json  类别名列表，可与鸿蒙 rawfile 一并打包
"""
from __future__ import annotations

import json
import os
import sys

import torch

# 保证可从 web_app 根导入
WEB_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WEB_APP_DIR not in sys.path:
    sys.path.insert(0, WEB_APP_DIR)

from unified_model_loader import MODEL_CONFIGS, load_model  # noqa: E402


OUT_DIR = os.path.join(WEB_APP_DIR, "exported_onnx")


def export_one(model_type: str, opset: int = 14) -> bool:
    cfg = MODEL_CONFIGS[model_type]
    path = cfg["model_path"]
    if not os.path.isfile(path):
        print(f"[跳过] {model_type}: 无权重文件 {path}")
        return False
    device = "cpu"
    model, config = load_model(model_type, device=device, force_reload=True)
    model.eval()
    dummy = torch.randn(1, 3, 224, 224, device=device)
    onnx_name = f"{model_type}.onnx"
    out_path = os.path.join(OUT_DIR, onnx_name)
    os.makedirs(OUT_DIR, exist_ok=True)
    torch.onnx.export(
        model,
        dummy,
        out_path,
        input_names=["input"],
        output_names=["logits"],
        dynamic_axes={"input": {0: "batch"}, "logits": {0: "batch"}},
        opset_version=opset,
        do_constant_folding=True,
    )
    labels_path = os.path.join(OUT_DIR, f"labels_{model_type}.json")
    with open(labels_path, "w", encoding="utf-8") as f:
        json.dump(config["classes"], f, ensure_ascii=False, indent=2)
    print(f"[OK] {model_type} -> {out_path}")
    print(f"     labels -> {labels_path}")
    return True


def main() -> None:
    print("导出 ONNX（输入固定 1x3x224x224，与 unified_predict 验证预处理一致）\n")
    types = list(MODEL_CONFIGS.keys())
    ok = 0
    for mt in types:
        try:
            if export_one(mt):
                ok += 1
        except Exception as e:
            print(f"[失败] {mt}: {e}")
    print(f"\n完成：成功 {ok}/{len(types)}。下一步见 scripts/HARMONY_ONDEVICE.md")


if __name__ == "__main__":
    main()
