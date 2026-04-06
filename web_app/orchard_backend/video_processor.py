# -*- coding: utf-8 -*-
"""
果园视频智能分析：YOLOv8 苹果检测 + 成熟度/病害识别
"""

import os
import sys
import cv2
import base64
import threading
import queue
import time
from PIL import Image, ImageDraw, ImageFont
import numpy as np

# 病害英文 -> 中文（用于视频标注，避免问号乱码）
DISEASE_CN = {
    'Blotch_Apple': '褐斑病', 'Normal_Apple': '正常', 'Rot_Apple': '腐烂', 'Scab_Apple': '黑星病',
    'Scratch_Apple': '刮伤', 'Branch_Apple': '枝干',  # 兼容其他模型输出
}

# COCO 类别中 apple 的索引（YOLOv8 使用 COCO 80 类）
COCO_APPLE_ID = 47

# 自定义苹果检测模型路径（若存在则优先使用，比 COCO 更精准）
# 可放置：MinneApple/Roboflow 等果园苹果专用模型
# 下载示例：Roboflow Universe "apples" 或 "apple-detection-yolo"
_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_APP_DIR = os.path.dirname(_PKG_DIR)
MODELS_DIR = os.path.join(WEB_APP_DIR, 'models')
APPLE_DETECTION_CUSTOM = os.path.join(MODELS_DIR, 'apple_detection.pt')

# 苹果框选优先准确：True=多尺度+大模型保证框选准，成熟度/病害精度次要
APPLE_ACCURACY_FIRST = True

# 成熟度 -> 框颜色 BGR
MATURITY_COLORS = {
    '成熟': (0, 255, 0),      # 绿
    '未成熟': (0, 255, 255),  # 黄
    '过成熟': (0, 165, 255),  # 橙
}


def get_device():
    try:
        import torch
        return 'cuda' if torch.cuda.is_available() else 'cpu'
    except Exception:
        return 'cpu'


def load_orchard_detector(device=None):
    """
    加载苹果检测模型。APPLE_ACCURACY_FIRST 时优先用准模型保证框选准确。
    1. 自定义模型 web_app/models/apple_detection.pt（果园专用）
    2. 框选优先：m > s > n；否则 n > s > m
    """
    if device is None:
        device = get_device()
    try:
        from ultralytics import YOLO
        if os.path.isfile(APPLE_DETECTION_CUSTOM):
            model = YOLO(APPLE_DETECTION_CUSTOM)
            return model, device, [0, 1]
        order = ('yolov8m.pt', 'yolov8s.pt', 'yolov8n.pt') if APPLE_ACCURACY_FIRST else ('yolov8n.pt', 'yolov8s.pt', 'yolov8m.pt')
        for name in order:
            try:
                weight_path = os.path.join(MODELS_DIR, name) if os.path.isfile(os.path.join(MODELS_DIR, name)) else name
                model = YOLO(weight_path)
                return model, device, [COCO_APPLE_ID]
            except Exception:
                continue
        fallback = os.path.join(MODELS_DIR, 'yolov8n.pt')
        model = YOLO(fallback if os.path.isfile(fallback) else 'yolov8n.pt')
        return model, device, [COCO_APPLE_ID]
    except Exception as e:
        raise RuntimeError(f"YOLO 加载失败: {e}")


def _nms_boxes(boxes, iou_thresh=0.5):
    """对重叠框做 NMS，保留高置信度"""
    if len(boxes) <= 1:
        return boxes
    boxes = sorted(boxes, key=lambda b: b[4], reverse=True)
    keep = []
    for b in boxes:
        x1, y1, x2, y2, conf = b
        area = (x2 - x1) * (y2 - y1)
        overlap = False
        for k in keep:
            kx1, ky1, kx2, ky2, _ = k
            ix1 = max(x1, kx1)
            iy1 = max(y1, ky1)
            ix2 = min(x2, kx2)
            iy2 = min(y2, ky2)
            if ix2 > ix1 and iy2 > iy1:
                inter = (ix2 - ix1) * (iy2 - iy1)
                iou = inter / (area + 1e-6)
                if iou > iou_thresh:
                    overlap = True
                    break
        if not overlap:
            keep.append(b)
    return keep


def detect_apples_in_frame(frame, model, apple_class_ids=None, imgsz=640, conf_thresh=0.25, max_boxes=20):
    """
    检测帧中的苹果
    APPLE_ACCURACY_FIRST 时用 1280+640 多尺度保证框选准，否则单尺度 640
    返回: [(x1,y1,x2,y2,conf), ...]
    """
    if apple_class_ids is None:
        apple_class_ids = [COCO_APPLE_ID]
    scales = (1280, 640) if APPLE_ACCURACY_FIRST else (640,)
    try:
        all_boxes = []
        for sz in scales:
            results = model(frame, imgsz=sz, verbose=False)[0]
            if results.boxes is None:
                continue
            for i, box in enumerate(results.boxes):
                cls_id = int(box.cls[0])
                if cls_id not in apple_class_ids:
                    continue
                conf = float(box.conf[0])
                if conf < conf_thresh:
                    continue
                xyxy = box.xyxy[0].cpu().numpy()
                x1, y1, x2, y2 = int(xyxy[0]), int(xyxy[1]), int(xyxy[2]), int(xyxy[3])
                all_boxes.append((x1, y1, x2, y2, conf))
        all_boxes = _nms_boxes(all_boxes, iou_thresh=0.45)
        all_boxes.sort(key=lambda b: b[4], reverse=True)
        return all_boxes[:max_boxes]
    except Exception as e:
        print(f"[YOLO] 检测失败: {e}", flush=True)
        return []


def crop_bbox_to_pil(frame, bbox):
    """从帧中裁剪 bbox 区域为 PIL Image"""
    x1, y1, x2, y2 = bbox[:4]
    h, w = frame.shape[:2]
    x1 = max(0, min(x1, w - 1))
    x2 = max(0, min(x2, w))
    y1 = max(0, min(y1, h - 1))
    y2 = max(0, min(y2, h))
    if x2 <= x1 or y2 <= y1:
        return None
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return None
    rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


def _get_chinese_font(size=22):
    """获取支持中文的字体，用于 PIL 绘制（避免问号乱码）"""
    windir = os.environ.get('SystemRoot', 'C:\\Windows')
    fonts_dir = os.path.join(windir, 'Fonts')
    candidates = [
        os.path.join(fonts_dir, 'msyh.ttc'),   # 微软雅黑
        os.path.join(fonts_dir, 'msyhbd.ttc'),
        os.path.join(fonts_dir, 'simhei.ttf'), # 黑体
        os.path.join(fonts_dir, 'simsun.ttc'), # 宋体
        os.path.join(fonts_dir, 'simsunb.ttf'),
        'C:/Windows/Fonts/msyh.ttc',
        'C:/Windows/Fonts/simhei.ttf',
        '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
        '/System/Library/Fonts/PingFang.ttc',
    ]
    if os.path.isdir(fonts_dir):
        for f in os.listdir(fonts_dir):
            if f.lower().endswith(('.ttc', '.ttf')) and any(x in f.lower() for x in ('msyh', 'simhei', 'simsun', 'yahei')):
                p = os.path.join(fonts_dir, f)
                if p not in candidates:
                    candidates.append(p)
    for path in candidates:
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def draw_annotations(frame, bboxes, maturity_results, disease_results):
    """
    在帧上绘制彩色框和中文标签（PIL 支持中文，与实时预览一致）
    """
    annotated = frame.copy()
    rgb = cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb)
    draw = ImageDraw.Draw(pil_img)
    font = _get_chinese_font(24)  # 加大字号，避免看不清
    for i, bbox in enumerate(bboxes):
        x1, y1, x2, y2 = bbox[:4]
        mat_class, mat_conf = maturity_results[i] if i < len(maturity_results) else ('未知', 0)
        dis_class, _ = disease_results[i] if i < len(disease_results) else ('未知', 0)
        dis_key = str(dis_class).replace(' ', '_') if dis_class else '未知'
        dis_cn = DISEASE_CN.get(dis_key, DISEASE_CN.get(dis_class, str(dis_class)))
        color_bgr = MATURITY_COLORS.get(mat_class, (0, 0, 255))
        color_rgb = (color_bgr[2], color_bgr[1], color_bgr[0])
        thickness = 2
        draw.rectangle([x1, y1, x2, y2], outline=color_rgb, width=thickness)
        label = f"{mat_class} {mat_conf*100:.0f}% | {dis_cn}"
        try:
            bbox_text = draw.textbbox((0, 0), label, font=font)
            tw, th = bbox_text[2] - bbox_text[0], bbox_text[3] - bbox_text[1]
        except AttributeError:
            tw, th = draw.textsize(label, font=font)
        ty = y1 - th - 6
        if ty < 0:
            ty = y2 + 6
        pad_x, pad_y = 10, 6
        draw.rectangle([x1, ty, x1 + tw + pad_x * 2, ty + th + pad_y], fill=(0, 0, 0))
        draw.text((x1 + pad_x, ty + pad_y // 2), label, font=font, fill=color_rgb)
    annotated = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    return annotated


def process_orchard_video(
    input_path,
    output_path,
    fps_sample=3,
    progress_callback=None,
    device=None,
    skip_annotate=False,
):
    """
    处理果园视频：YOLO 检测 + 成熟度/病害识别
    progress_callback: (frame_idx, total, fps, w, h, annotations) -> 每帧推送标注供前端实时叠加
    skip_annotate: True 时直接复制原视频，不检测不标注（用于已标注视频）
    """
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise ValueError(f"无法打开视频: {input_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (w, h))

    if skip_annotate:
        # 已标注视频：直接复制，不检测不绘制
        frame_idx = 0
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                break
            out.write(frame)
            if progress_callback:
                try:
                    progress_callback(frame_idx, total_frames, fps, w, h, {'bboxes': [], 'maturity': [], 'disease': []})
                except Exception:
                    pass
            frame_idx += 1
        cap.release()
        out.release()
        if progress_callback:
            progress_callback(frame_idx, total_frames, fps, w, h, {'bboxes': [], 'maturity': [], 'disease': []})
        return output_path

    if device is None:
        device = get_device()
    if APPLE_ACCURACY_FIRST:
        fps_sample = min(fps_sample, 2)  # 每 2 帧检测一次，保证框选更密

    from orchard_backend.predict import predict_batch

    yolo_model, _, apple_cls_ids = load_orchard_detector(device)
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # 回到开头（cap 已在函数开头打开）

    frame_idx = 0
    last_bboxes = []
    last_maturity = []
    last_disease = []

    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            break

        is_key_frame = (frame_idx % fps_sample == 0)

        if is_key_frame and frame is not None:
            bboxes = detect_apples_in_frame(frame, yolo_model, apple_class_ids=apple_cls_ids)
            if bboxes:
                valid = []
                for b in bboxes:
                    c = crop_bbox_to_pil(frame, b)
                    if c is not None and c.width >= 16 and c.height >= 16:
                        valid.append((b, c))
                if valid:
                    bboxes_ok = [v[0] for v in valid]
                    crops = [v[1] for v in valid]
                    maturity_results = predict_batch(crops, 'demo1', device)
                    disease_results = predict_batch(crops, 'apple_fruit_disease', device)
                    last_bboxes = bboxes_ok
                    last_maturity = maturity_results
                    last_disease = disease_results
                else:
                    last_bboxes = []
                    last_maturity = []
                    last_disease = []
            else:
                last_bboxes = []
                last_maturity = []
                last_disease = []

        if last_bboxes:
            annotated = draw_annotations(frame, last_bboxes, last_maturity, last_disease)
        else:
            annotated = frame

        out.write(annotated)

        # 每帧推送标注数据，供前端实时叠加显示（模拟无人机飞行时实时分析）
        if progress_callback:
            try:
                ann = {
                    'bboxes': [[int(x) for x in b[:5]] for b in last_bboxes],
                    'maturity': [[str(m[0]), float(m[1])] for m in last_maturity],
                    'disease': [[str(d[0]), float(d[1])] for d in last_disease],
                }
                progress_callback(frame_idx, total_frames, fps, w, h, ann)
            except Exception:
                pass

        frame_idx += 1

    cap.release()
    out.release()
    if progress_callback:
        progress_callback(frame_idx, total_frames, fps, w, h, {'bboxes': [], 'maturity': [], 'disease': []})
    return output_path
