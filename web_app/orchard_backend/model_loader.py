# -*- coding: utf-8 -*-
"""
统一模型加载模块
功能：加载demo1和demo2的训练好的模型
"""

import sys
import io
import os

# 设置控制台编码为UTF-8
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import torch
import torch.nn as nn
from torchvision import models

# ==================== 模型路径配置 =====================
_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_APP_DIR = os.path.dirname(_PKG_DIR)
ROOT_DIR = os.path.dirname(WEB_APP_DIR)
DEMO1_MODEL_PATH = os.path.join(ROOT_DIR, '..', 'demo1', 'processed_dataset', 'best_model.pth')
DEMO2_MODEL_PATH = os.path.join(ROOT_DIR, '..', 'demo2', 'processed_dataset', 'best_model.pth')
APPLE_DISEASE_MODEL_PATH = os.path.join(WEB_APP_DIR, 'training', 'processed_dataset', 'best_model.pth')
APPLE_FRUIT_DISEASE_MODEL_PATH = os.path.join(WEB_APP_DIR, 'training', 'fruit_processed_dataset', 'best_model.pth')

# ==================== Demo1模型结构（苹果成熟度检测）====================
class ChannelAttention_Demo1(nn.Module):
    """通道注意力模块（Demo1）"""
    def __init__(self, in_planes, ratio=16):
        super(ChannelAttention_Demo1, self).__init__()
        self.avg_pool = nn.AdaptiveAvgPool2d(1)
        self.max_pool = nn.AdaptiveMaxPool2d(1)
        self.fc1 = nn.Conv2d(in_planes, in_planes // ratio, 1, bias=False)
        self.relu1 = nn.ReLU()
        self.fc2 = nn.Conv2d(in_planes // ratio, in_planes, 1, bias=False)
        self.sigmoid = nn.Sigmoid()
    
    def forward(self, x):
        avg_out = self.fc2(self.relu1(self.fc1(self.avg_pool(x))))
        max_out = self.fc2(self.relu1(self.fc1(self.max_pool(x))))
        out = avg_out + max_out
        return self.sigmoid(out)

class SpatialAttention_Demo1(nn.Module):
    """空间注意力模块（Demo1）"""
    def __init__(self, kernel_size=7):
        super(SpatialAttention_Demo1, self).__init__()
        assert kernel_size in (3, 7), 'kernel size must be 3 or 7'
        padding = 3 if kernel_size == 7 else 1
        self.conv1 = nn.Conv2d(2, 1, kernel_size, padding=padding, bias=False)
        self.sigmoid = nn.Sigmoid()
    
    def forward(self, x):
        avg_out = torch.mean(x, dim=1, keepdim=True)
        max_out, _ = torch.max(x, dim=1, keepdim=True)
        x = torch.cat([avg_out, max_out], dim=1)
        x = self.conv1(x)
        return self.sigmoid(x)

class CBAM_Demo1(nn.Module):
    """CBAM注意力模块（Demo1）"""
    def __init__(self, in_planes, ratio=16, kernel_size=7):
        super(CBAM_Demo1, self).__init__()
        self.ca = ChannelAttention_Demo1(in_planes, ratio)
        self.sa = SpatialAttention_Demo1(kernel_size)
    
    def forward(self, x):
        out = x * self.ca(x)
        out = out * self.sa(out)
        return out

class ResNet50WithAttention_Demo1(nn.Module):
    """带CBAM注意力的ResNet50模型（Demo1）"""
    def __init__(self, num_classes=3):
        super(ResNet50WithAttention_Demo1, self).__init__()
        resnet = models.resnet50(weights=models.ResNet50_Weights.IMAGENET1K_V1)
        self.conv1 = resnet.conv1
        self.bn1 = resnet.bn1
        self.relu = resnet.relu
        self.maxpool = resnet.maxpool
        self.layer1 = resnet.layer1
        self.layer2 = resnet.layer2
        self.layer3 = resnet.layer3
        self.layer4 = resnet.layer4
        self.attention2 = CBAM_Demo1(512, ratio=16)
        self.attention3 = CBAM_Demo1(1024, ratio=16)
        self.attention4 = CBAM_Demo1(2048, ratio=16)
        self.avgpool = resnet.avgpool
        num_features = resnet.fc.in_features
        self.fc = nn.Sequential(
            nn.Dropout(0.5),
            nn.Linear(num_features, 512),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(512, num_classes)
        )
    
    def forward(self, x):
        x = self.conv1(x)
        x = self.bn1(x)
        x = self.relu(x)
        x = self.maxpool(x)
        x = self.layer1(x)
        x = self.layer2(x)
        x = self.attention2(x)
        x = self.layer3(x)
        x = self.attention3(x)
        x = self.layer4(x)
        x = self.attention4(x)
        x = self.avgpool(x)
        x = torch.flatten(x, 1)
        x = self.fc(x)
        return x

# ==================== 苹果病害模型（MobileNetV3-Small，与 train_apple_disease.py 一致）====================
class AppleDiseaseNet(nn.Module):
    """苹果叶片病害 4 类分类，MobileNetV3-Small + 自定义分类头"""
    def __init__(self, num_classes=4):
        super(AppleDiseaseNet, self).__init__()
        backbone = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.IMAGENET1K_V1)
        self.features = backbone.features
        self.avgpool = backbone.avgpool
        self.classifier = backbone.classifier
        in_features = self.classifier[-1].in_features
        self.classifier[-1] = nn.Linear(in_features, num_classes)

    def forward(self, x):
        x = self.features(x)
        x = self.avgpool(x)
        x = torch.flatten(x, 1)
        x = self.classifier(x)
        return x


# ==================== 苹果果实病害模型（与 train_apple_fruit_disease.py 一致）====================
class AppleFruitDiseaseNet(nn.Module):
    """苹果果实病害 4 类：Blotch_Apple, Normal_Apple, Rot_Apple, Scab_Apple"""
    def __init__(self, num_classes=4):
        super(AppleFruitDiseaseNet, self).__init__()
        backbone = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.IMAGENET1K_V1)
        self.features = backbone.features
        self.avgpool = backbone.avgpool
        self.classifier = backbone.classifier
        in_features = self.classifier[-1].in_features
        self.classifier[-1] = nn.Sequential(
            nn.Dropout(0.3),
            nn.Linear(in_features, num_classes),
        )

    def forward(self, x):
        x = self.features(x)
        x = self.avgpool(x)
        x = torch.flatten(x, 1)
        x = self.classifier(x)
        return x


# ==================== Demo2模型结构（多类别水果分类）====================
class ChannelAttention_Demo2(nn.Module):
    """增强的通道注意力模块（Demo2）"""
    def __init__(self, in_planes, ratio=8):
        super(ChannelAttention_Demo2, self).__init__()
        self.avg_pool = nn.AdaptiveAvgPool2d(1)
        self.max_pool = nn.AdaptiveMaxPool2d(1)
        self.fc1 = nn.Conv2d(in_planes, in_planes // ratio, 1, bias=False)
        self.bn1 = nn.BatchNorm2d(in_planes // ratio)
        self.relu1 = nn.ReLU()
        self.fc2 = nn.Conv2d(in_planes // ratio, in_planes, 1, bias=False)
        self.bn2 = nn.BatchNorm2d(in_planes)
        self.sigmoid = nn.Sigmoid()
    
    def forward(self, x):
        avg_out = self.bn2(self.fc2(self.relu1(self.bn1(self.fc1(self.avg_pool(x))))))
        max_out = self.bn2(self.fc2(self.relu1(self.bn1(self.fc1(self.max_pool(x))))))
        out = avg_out + max_out
        return self.sigmoid(out)

class SpatialAttention_Demo2(nn.Module):
    """增强的空间注意力模块（Demo2）"""
    def __init__(self, kernel_size=7):
        super(SpatialAttention_Demo2, self).__init__()
        assert kernel_size in (3, 7), 'kernel size must be 3 or 7'
        padding = 3 if kernel_size == 7 else 1
        self.conv1 = nn.Conv2d(2, 1, kernel_size, padding=padding, bias=False)
        self.bn = nn.BatchNorm2d(1)
        self.sigmoid = nn.Sigmoid()
    
    def forward(self, x):
        avg_out = torch.mean(x, dim=1, keepdim=True)
        max_out, _ = torch.max(x, dim=1, keepdim=True)
        x = torch.cat([avg_out, max_out], dim=1)
        x = self.bn(self.conv1(x))
        return self.sigmoid(x)

class SEAttention_Demo2(nn.Module):
    """SE注意力模块（Demo2）"""
    def __init__(self, in_planes, ratio=8):
        super(SEAttention_Demo2, self).__init__()
        self.avg_pool = nn.AdaptiveAvgPool2d(1)
        self.fc = nn.Sequential(
            nn.Linear(in_planes, in_planes // ratio, bias=False),
            nn.ReLU(inplace=True),
            nn.Linear(in_planes // ratio, in_planes, bias=False),
            nn.Sigmoid()
        )
    
    def forward(self, x):
        b, c, _, _ = x.size()
        y = self.avg_pool(x).view(b, c)
        y = self.fc(y).view(b, c, 1, 1)
        return x * y.expand_as(x)

class CBAM_Demo2(nn.Module):
    """增强的CBAM注意力模块（Demo2）"""
    def __init__(self, in_planes, ratio=8, kernel_size=7, use_se=True):
        super(CBAM_Demo2, self).__init__()
        self.ca = ChannelAttention_Demo2(in_planes, ratio)
        self.sa = SpatialAttention_Demo2(kernel_size)
        self.use_se = use_se
        if use_se:
            self.se = SEAttention_Demo2(in_planes, ratio)
    
    def forward(self, x):
        out = x * self.ca(x)
        out = out * self.sa(out)
        if self.use_se:
            out = self.se(out)
        return out

class ResNet50WithAttention_Demo2(nn.Module):
    """带增强CBAM+SE注意力的ResNet50模型（Demo2）"""
    def __init__(self, num_classes=5):
        super(ResNet50WithAttention_Demo2, self).__init__()
        resnet = models.resnet50(weights=models.ResNet50_Weights.IMAGENET1K_V1)
        self.conv1 = resnet.conv1
        self.bn1 = resnet.bn1
        self.relu = resnet.relu
        self.maxpool = resnet.maxpool
        self.layer1 = resnet.layer1
        self.layer2 = resnet.layer2
        self.layer3 = resnet.layer3
        self.layer4 = resnet.layer4
        self.attention1 = CBAM_Demo2(256, ratio=8, use_se=True)
        self.attention2 = CBAM_Demo2(512, ratio=8, use_se=True)
        self.attention3 = CBAM_Demo2(1024, ratio=8, use_se=True)
        self.attention4 = CBAM_Demo2(2048, ratio=8, use_se=True)
        self.final_attention = CBAM_Demo2(2048, ratio=8, use_se=True)
        self.avgpool = resnet.avgpool
        num_features = resnet.fc.in_features
        self.fc = nn.Sequential(
            nn.Dropout(0.5),
            nn.Linear(num_features, 1024),
            nn.BatchNorm1d(1024),
            nn.ReLU(),
            nn.Dropout(0.4),
            nn.Linear(1024, 512),
            nn.BatchNorm1d(512),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(512, num_classes)
        )
    
    def forward(self, x):
        x = self.conv1(x)
        x = self.bn1(x)
        x = self.relu(x)
        x = self.maxpool(x)
        x = self.layer1(x)
        x = self.attention1(x)
        x = self.layer2(x)
        x = self.attention2(x)
        x = self.layer3(x)
        x = self.attention3(x)
        x = self.layer4(x)
        x = self.attention4(x)
        x = self.final_attention(x)
        x = self.avgpool(x)
        x = torch.flatten(x, 1)
        x = self.fc(x)
        return x

# ==================== 模型配置信息 =====================
MODEL_CONFIGS = {
    'demo1': {
        'name': '苹果成熟度检测',
        'description': '检测苹果的成熟度：未成熟、成熟、过成熟',
        'model_class': ResNet50WithAttention_Demo1,
        'num_classes': 3,
        'classes': ['成熟', '未成熟', '过成熟'],
        'color_map': {
            '未成熟': (0, 255, 0),      # 绿色
            '成熟': (0, 0, 255),        # 红色
            '过成熟': (0, 0, 139)       # 深红色
        },
        'description_map': {
            '未成熟': '未成熟的苹果，呈绿色',
            '成熟': '成熟的苹果，呈红色（包括半成熟和完全成熟）',
            '过成熟': '过成熟的苹果，可能已腐烂'
        },
        'model_path': DEMO1_MODEL_PATH
    },
    'demo2': {
        'name': '多类别水果分类',
        'description': '识别5种水果：苹果、杨桃、梨、李子、番茄',
        'model_class': ResNet50WithAttention_Demo2,
        'num_classes': 5,
        'classes': ['Apple', 'Carambola', 'Pear', 'Plum', 'Tomatoes'],
        'color_map': {
            'Apple': (0, 0, 255),        # 红色
            'Carambola': (0, 255, 255),  # 黄色
            'Pear': (0, 255, 0),         # 绿色
            'Plum': (128, 0, 128),       # 紫色
            'Tomatoes': (0, 0, 255)      # 红色
        },
        'description_map': {
            'Apple': '苹果 - 圆形或椭圆形，通常为红色、绿色或黄色',
            'Carambola': '杨桃 - 星形横截面，黄色或绿色，有5个棱角',
            'Pear': '梨 - 上窄下宽的形状，通常为黄色或绿色',
            'Plum': '李子 - 圆形或椭圆形，通常为紫色、红色或黄色',
            'Tomatoes': '番茄 - 圆形或椭圆形，通常为红色'
        },
        'model_path': DEMO2_MODEL_PATH
    },
    'apple_disease': {
        'name': '苹果叶片病害识别',
        'description': '识别苹果叶片 4 类：黑星病、黑腐病、锈病、健康（轻量快速版）',
        'model_class': AppleDiseaseNet,
        'num_classes': 4,
        'classes': ['Apple___Apple_scab', 'Apple___Black_rot', 'Apple___Cedar_apple_rust', 'Apple___healthy'],
        'color_map': {
            'Apple___Apple_scab': (220, 80, 60),
            'Apple___Black_rot': (180, 60, 80),
            'Apple___Cedar_apple_rust': (200, 140, 60),
            'Apple___healthy': (80, 200, 120),
        },
        'description_map': {
            'Apple___Apple_scab': '苹果黑星病（Venturia inaequalis）',
            'Apple___Black_rot': '苹果黑腐病（Botryosphaeria obtusa）',
            'Apple___Cedar_apple_rust': '苹果锈病（雪松-苹果锈病）',
            'Apple___healthy': '健康叶片',
        },
        'model_path': APPLE_DISEASE_MODEL_PATH
    },
    'apple_fruit_disease': {
        'name': '苹果果实病害识别',
        'description': '识别苹果果实 4 类：褐斑、正常、腐烂、黑星',
        'model_class': AppleFruitDiseaseNet,
        'num_classes': 4,
        'classes': ['Blotch_Apple', 'Normal_Apple', 'Rot_Apple', 'Scab_Apple'],
        'color_map': {
            'Blotch_Apple': (200, 120, 80),
            'Normal_Apple': (80, 200, 120),
            'Rot_Apple': (120, 60, 80),
            'Scab_Apple': (180, 100, 60),
        },
        'description_map': {
            'Blotch_Apple': '苹果褐斑病',
            'Normal_Apple': '正常果实',
            'Rot_Apple': '腐烂',
            'Scab_Apple': '黑星病',
        },
        'model_path': APPLE_FRUIT_DISEASE_MODEL_PATH
    }
}

# ==================== 全局模型缓存 =====================
_models = {}
_device = None

def load_model(model_type='demo1', device='cpu', force_reload=False):
    """
    加载指定类型的模型
    
    参数:
        model_type: 模型类型 ('demo1' 或 'demo2')
        device: 设备 ('cpu' 或 'cuda')
        force_reload: 是否强制重新加载
    
    返回:
        model: 加载好的模型
        config: 模型配置信息
    """
    global _models, _device
    
    if model_type not in MODEL_CONFIGS:
        raise ValueError(f"未知的模型类型: {model_type}")
    
    config = MODEL_CONFIGS[model_type]
    
    # 检查是否已加载且不需要重新加载
    if model_type in _models and not force_reload:
        return _models[model_type], config
    
    # 检查模型文件是否存在
    model_path = config['model_path']
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"模型文件不存在: {model_path}")
    
    # 创建模型结构
    model = config['model_class'](num_classes=config['num_classes'])
    
    # 加载模型权重
    checkpoint = torch.load(model_path, map_location=device)
    
    # 检查checkpoint格式
    saved_classes = None
    if isinstance(checkpoint, dict):
        if 'model_state_dict' in checkpoint:
            model.load_state_dict(checkpoint['model_state_dict'])
            saved_classes = checkpoint.get('classes', None)
        else:
            model.load_state_dict(checkpoint)
    else:
        model.load_state_dict(checkpoint)
    
    # 对于demo1，优先使用保存的类别顺序，但需要验证是否正确
    # ImageFolder按文件夹名称字母顺序排序，实际顺序是：成熟、未成熟、过成熟
    if model_type == 'demo1':
        if saved_classes:
            # 验证保存的类别顺序是否正确（应该是：成熟、未成熟、过成熟）
            correct_order = ['成熟', '未成熟', '过成熟']
            if saved_classes == correct_order:
                config['classes'] = saved_classes
                print(f"  使用模型文件中保存的类别顺序: {saved_classes}")
            else:
                print(f"  警告：模型文件中保存的类别顺序 {saved_classes} 不正确")
                print(f"  使用正确的类别顺序: {correct_order}")
                config['classes'] = correct_order
        else:
            # 如果没有保存类别信息，使用正确的顺序
            config['classes'] = ['成熟', '未成熟', '过成熟']
            print(f"  模型文件中未保存类别信息，使用正确的顺序: {config['classes']}")
    elif saved_classes:
        # 对于demo2，直接使用保存的类别顺序
        config['classes'] = saved_classes
    
    # 设置为评估模式
    model.eval()
    model = model.to(device)
    
    _device = device
    _models[model_type] = model
    
    print(f"✓ {config['name']}模型加载成功: {model_path}")
    print(f"  类别: {config['classes']}")
    
    return model, config

def get_model(model_type='demo1', device='cpu'):
    """
    获取模型（如果已加载则直接返回）
    """
    return load_model(model_type, device, force_reload=False)

def reload_model(model_type='demo1', device='cpu'):
    """
    强制重新加载模型
    """
    return load_model(model_type, device, force_reload=True)

def get_device():
    """获取当前设备"""
    return _device if _device else torch.device('cuda' if torch.cuda.is_available() else 'cpu')

