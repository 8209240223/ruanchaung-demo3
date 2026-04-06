# -*- coding: utf-8 -*-
"""
统一预测模块
功能：根据选择的模型进行图片预测
"""

import torch
import torch.nn.functional as F
from torchvision import transforms
from PIL import Image
import cv2
import numpy as np
import os

from unified_model_loader import get_model, get_device

def preprocess_image(image_path, image_size=224):
    """
    预处理图片
    
    参数:
        image_path: 图片路径
        image_size: 图片尺寸（默认224x224）
    
    返回:
        tensor: 预处理后的图片tensor
        original_image: 原始PIL图片（用于标注）
    """
    try:
        img = Image.open(image_path).convert('RGB')
        original_img = img.copy()
    except Exception as e:
        raise ValueError(f"无法加载图片: {e}")
    
    # 预处理变换（与训练时的验证集变换一致）
    transform = transforms.Compose([
        transforms.Resize(256),
        transforms.CenterCrop(image_size),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    ])
    
    img_tensor = transform(img).unsqueeze(0)  # 添加batch维度
    
    return img_tensor, original_img

def predict_image(image_path, model_type='demo1', device='cpu'):
    """
    预测单张图片
    
    参数:
        image_path: 图片路径
        model_type: 模型类型 ('demo1' 或 'demo2')
        device: 设备 ('cpu' 或 'cuda')
    
    返回:
        class_name: 预测的类别名称
        confidence: 置信度（0-1）
        probabilities: 所有类别的概率
        original_img: 原始图片
        config: 模型配置信息
    """
    # 获取模型和配置
    model, config = get_model(model_type, device)
    model_device = get_device()
    
    # 预处理图片
    img_tensor, original_img = preprocess_image(image_path, image_size=224)
    img_tensor = img_tensor.to(model_device)
    
    # 预测
    with torch.no_grad():
        outputs = model(img_tensor)
        probabilities = F.softmax(outputs, dim=1)
        confidence, predicted = torch.max(probabilities, 1)
    
    # 获取类别名称和置信度
    class_idx = predicted.item()
    classes = config['classes']
    class_name = classes[class_idx]
    confidence_score = confidence.item()
    
    # 获取所有类别的概率
    prob_dict = {classes[i]: probabilities[0][i].item() for i in range(len(classes))}
    
    return class_name, confidence_score, prob_dict, original_img, config

def draw_box_on_image(image, class_name, confidence, config, box_type='full'):
    """
    在图片上画框和标注
    
    参数:
        image: PIL图片对象
        class_name: 类别名称
        confidence: 置信度
        config: 模型配置信息
        box_type: 框的类型 ('full' 或 'center')
    
    返回:
        annotated_image: 标注后的PIL图片
    """
    # 转换为numpy数组（用于OpenCV）
    img_array = np.array(image)
    img_cv = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
    
    # 获取颜色
    color_map = config['color_map']
    color = color_map.get(class_name, (255, 255, 255))  # 默认白色
    
    height, width = img_cv.shape[:2]
    
    if box_type == 'full':
        # 整张图片画框（留一些边距）
        margin = 10
        pt1 = (margin, margin)
        pt2 = (width - margin, height - margin)
        thickness = 5
    else:
        # 在中心画一个小框
        box_size = min(width, height) // 2
        center_x, center_y = width // 2, height // 2
        pt1 = (center_x - box_size // 2, center_y - box_size // 2)
        pt2 = (center_x + box_size // 2, center_y + box_size // 2)
        thickness = 3
    
    # 画矩形框
    cv2.rectangle(img_cv, pt1, pt2, color, thickness)
    
    # 添加文字标签
    label = f"{class_name} ({confidence*100:.1f}%)"
    
    # 计算文字位置（在框的上方）
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.8
    font_thickness = 2
    
    # 获取文字大小
    (text_width, text_height), baseline = cv2.getTextSize(label, font, font_scale, font_thickness)
    
    # 文字背景位置
    text_x = pt1[0]
    text_y = pt1[1] - text_height - 10
    
    # 如果文字会超出图片上边界，放在框下方
    if text_y < 0:
        text_y = pt2[1] + text_height + 10
    
    # 画文字背景（半透明）
    overlay = img_cv.copy()
    cv2.rectangle(overlay, 
                  (text_x - 5, text_y - text_height - 5),
                  (text_x + text_width + 5, text_y + baseline + 5),
                  (0, 0, 0), -1)  # 黑色背景
    cv2.addWeighted(overlay, 0.6, img_cv, 0.4, 0, img_cv)
    
    # 画文字
    cv2.putText(img_cv, label, (text_x, text_y), 
                font, font_scale, color, font_thickness, cv2.LINE_AA)
    
    # 转换回PIL格式
    img_rgb = cv2.cvtColor(img_cv, cv2.COLOR_BGR2RGB)
    annotated_image = Image.fromarray(img_rgb)
    
    return annotated_image

def preprocess_pil(pil_image, image_size=224):
    """从 PIL 图像预处理为 tensor，用于 predict_from_pil / predict_batch"""
    transform = transforms.Compose([
        transforms.Resize(256),
        transforms.CenterCrop(image_size),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    ])
    return transform(pil_image.convert('RGB'))


def predict_from_pil(pil_image, model_type='demo1', device=None):
    """
    从 PIL 图像预测（支持内存图像，无需写盘）
    返回: (class_name, confidence, prob_dict)
    """
    if device is None:
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
    model, config = get_model(model_type, device)
    img_tensor = preprocess_pil(pil_image).unsqueeze(0).to(device)
    with torch.no_grad():
        outputs = model(img_tensor)
        probabilities = F.softmax(outputs, dim=1)
        confidence, predicted = torch.max(probabilities, 1)
    classes = config['classes']
    class_idx = predicted.item()
    class_name = classes[class_idx]
    confidence_score = confidence.item()
    prob_dict = {classes[i]: probabilities[0][i].item() for i in range(len(classes))}
    return class_name, confidence_score, prob_dict


def predict_batch(pil_images, model_type='demo1', device=None):
    """
    批量预测多张 PIL 图像，一次 forward
    返回: [(class_name, confidence), ...]
    """
    if not pil_images:
        return []
    if device is None:
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
    model, config = get_model(model_type, device)
    tensors = [preprocess_pil(img) for img in pil_images]
    batch = torch.stack(tensors).to(device)
    with torch.no_grad():
        outputs = model(batch)
        probabilities = F.softmax(outputs, dim=1)
        confidence, predicted = torch.max(probabilities, 1)
    classes = config['classes']
    results = []
    for i in range(len(pil_images)):
        cn = classes[predicted[i].item()]
        cf = confidence[i].item()
        results.append((cn, cf))
    return results


def predict_and_annotate(image_path, model_type='demo1', device='cpu', box_type='full'):
    """
    预测图片并在图片上画框标注
    
    参数:
        image_path: 图片路径
        model_type: 模型类型
        device: 设备
        box_type: 框的类型
    
    返回:
        class_name: 预测类别
        confidence: 置信度
        prob_dict: 所有类别概率
        annotated_image: 标注后的图片
        config: 模型配置信息
    """
    # 预测
    class_name, confidence, prob_dict, original_img, config = predict_image(
        image_path, model_type, device
    )
    
    # 画框标注
    annotated_image = draw_box_on_image(
        original_img, class_name, confidence, config, box_type
    )
    
    return class_name, confidence, prob_dict, annotated_image, config



