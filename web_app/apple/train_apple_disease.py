# -*- coding: utf-8 -*-
"""
苹果叶片病害分类模型训练脚本
数据集：Apple_Disease_Dataset（PlantVillage 风格，4 类：Apple_scab, Black_rot, Cedar_apple_rust, healthy）
默认采用 MobileNetV3-Small，并启用速度优先策略，尽量将训练控制在 1 小时内
"""

import argparse
import os
import sys

# 将 web_app 加入路径以便可单独运行
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_APP_DIR = os.path.dirname(SCRIPT_DIR)
if WEB_APP_DIR not in sys.path:
    sys.path.insert(0, WEB_APP_DIR)

import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from torchvision import transforms, models, datasets
from tqdm import tqdm

# 默认路径
DEFAULT_DATA_DIR = os.path.join(SCRIPT_DIR, "Apple_Disease_Dataset")
DEFAULT_OUTPUT_DIR = os.path.join(SCRIPT_DIR, "processed_dataset")
IMAGE_SIZE = 224
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]
DEFAULT_WORKERS = max(0, min(4, (os.cpu_count() or 1) - 1))


def get_train_transform():
    return transforms.Compose([
        transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)),
        transforms.RandomHorizontalFlip(),
        transforms.ToTensor(),
        transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
    ])


def get_val_transform():
    return transforms.Compose([
        transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
    ])


def prepare_data(data_dir, val_ratio=0.2):
    """
    若存在 train/ 则用 train 训练、test/ 验证；若只有 test/ 则从 test 按比例划分 train/val。
    返回 (train_dataset, val_dataset, class_names)。
    """
    train_dir = os.path.join(data_dir, "train")
    test_dir = os.path.join(data_dir, "test")

    if os.path.isdir(train_dir):
        full_train = datasets.ImageFolder(train_dir, transform=get_train_transform())
        classes = full_train.classes
        if os.path.isdir(test_dir):
            train_ds = full_train
            val_ds = datasets.ImageFolder(test_dir, transform=get_val_transform())
        else:
            n = len(full_train)
            n_val = max(1, int(n * val_ratio))
            n_train = n - n_val
            train_idx, val_idx = torch.utils.data.random_split(
                range(n), [n_train, n_val], generator=torch.Generator().manual_seed(42)
            )
            train_ds = torch.utils.data.Subset(
                datasets.ImageFolder(train_dir, transform=get_train_transform()),
                train_idx.indices,
            )
            val_ds = torch.utils.data.Subset(
                datasets.ImageFolder(train_dir, transform=get_val_transform()),
                val_idx.indices,
            )
    elif os.path.isdir(test_dir):
        full_ds = datasets.ImageFolder(test_dir, transform=get_train_transform())
        classes = full_ds.classes
        n = len(full_ds)
        n_val = max(1, int(n * val_ratio))
        n_train = n - n_val
        train_idx, val_idx = torch.utils.data.random_split(
            range(n), [n_train, n_val], generator=torch.Generator().manual_seed(42)
        )
        train_ds = torch.utils.data.Subset(
            datasets.ImageFolder(test_dir, transform=get_train_transform()),
            train_idx.indices,
        )
        val_ds = torch.utils.data.Subset(
            datasets.ImageFolder(test_dir, transform=get_val_transform()),
            val_idx.indices,
        )
    else:
        raise FileNotFoundError(
            f"未找到 train 或 test 目录，请确认数据路径: {data_dir}\n"
            "期望结构: Apple_Disease_Dataset/train/Apple___Apple_scab/... 或 .../test/..."
        )

    classes = list(classes)
    return train_ds, val_ds, classes


def build_model(num_classes, device, freeze_backbone=True):
    """MobileNetV3-Small + 自定义分类头，兼顾训练速度与推理速度"""
    model = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.IMAGENET1K_V1)
    in_features = model.classifier[-1].in_features
    model.classifier[-1] = nn.Linear(in_features, num_classes)

    if freeze_backbone:
        for param in model.features.parameters():
            param.requires_grad = False

    return model.to(device)


def train_one_epoch(model, loader, criterion, optimizer, device, epoch, total_epochs):
    model.train()
    total_loss, correct, total = 0.0, 0, 0
    pbar = tqdm(
        loader,
        desc=f"第 {epoch}/{total_epochs} 轮",
        unit="batch",
        ncols=100,
        leave=True,
    )
    for images, labels in pbar:
        images, labels = images.to(device), labels.to(device)
        optimizer.zero_grad()
        out = model(images)
        loss = criterion(out, labels)
        loss.backward()
        optimizer.step()
        total_loss += loss.item()
        _, pred = out.max(1)
        correct += pred.eq(labels).sum().item()
        total += labels.size(0)
        pbar.set_postfix({"loss": f"{loss.item():.4f}", "acc": f"{correct/total:.2%}"})
    return total_loss / len(loader), correct / total


@torch.no_grad()
def evaluate(model, loader, device):
    model.eval()
    correct, total = 0, 0
    for images, labels in loader:
        images, labels = images.to(device), labels.to(device)
        out = model(images)
        _, pred = out.max(1)
        correct += pred.eq(labels).sum().item()
        total += labels.size(0)
    return correct / total if total else 0.0


def unfreeze_backbone(model):
    """解冻主干网络，用于后期微调。"""
    if hasattr(model, "features"):
        for param in model.features.parameters():
            param.requires_grad = True


def main():
    parser = argparse.ArgumentParser(description="苹果病害分类模型训练（默认：MobileNetV3-Small 快速模式）")
    parser.add_argument("--data_dir", type=str, default=DEFAULT_DATA_DIR, help="数据集根目录（含 train 或 test）")
    parser.add_argument("--output_dir", type=str, default=DEFAULT_OUTPUT_DIR, help="保存 best_model.pth 的目录")
    parser.add_argument("--epochs", type=int, default=8, help="训练轮数（默认 8，速度优先）")
    parser.add_argument("--batch_size", type=int, default=64, help="批大小（默认 64）")
    parser.add_argument("--lr", type=float, default=1e-3, help="学习率")
    parser.add_argument("--val_ratio", type=float, default=0.2, help="仅当无 train 时从 test 划分验证集比例")
    parser.add_argument("--device", type=str, default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--num_workers", type=int, default=DEFAULT_WORKERS, help="DataLoader 进程数")
    parser.add_argument("--patience", type=int, default=2, help="验证集无提升时的早停轮数")
    parser.add_argument("--unfreeze_epoch", type=int, default=999, help="从第几轮开始解冻主干微调，默认不解冻以优先保证速度")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    device = torch.device(args.device)
    print(f"使用设备: {device}")

    print("准备数据...")
    train_ds, val_ds, classes = prepare_data(args.data_dir, val_ratio=args.val_ratio)
    num_classes = len(classes)
    print(f"类别（按顺序）: {classes}")
    print(f"训练集样本数: {len(train_ds)}")
    print(f"验证集样本数: {len(val_ds)}")

    train_loader = DataLoader(
        train_ds,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.num_workers,
        pin_memory=(device.type == "cuda"),
    )
    val_loader = DataLoader(
        val_ds,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.num_workers,
        pin_memory=(device.type == "cuda"),
    )

    print("正在构建模型（加载预训练权重）...")
    model = build_model(num_classes, device, freeze_backbone=True)
    total_epochs = args.epochs
    print(
        f"\n共 {total_epochs} 轮训练，每轮结束后会显示验证集准确率。"
        f"\n当前模式：MobileNetV3-Small + 默认仅训练分类头 + 早停"
        f"\nnum_workers={args.num_workers}，batch_size={args.batch_size}，device={device}\n"
    )
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad],
        lr=args.lr
    )
    scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=4, gamma=0.5)

    best_acc = 0.0
    stale_epochs = 0
    for epoch in range(1, total_epochs + 1):
        if epoch == args.unfreeze_epoch:
            unfreeze_backbone(model)
            optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr * 0.2)
            scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=4, gamma=0.5)
            print(f"  -> 第 {epoch} 轮开始解冻主干，进入微调阶段")

        train_loss, train_acc = train_one_epoch(
            model, train_loader, criterion, optimizer, device, epoch, total_epochs
        )
        val_acc = evaluate(model, val_loader, device)
        scheduler.step()
        val_pct = val_acc * 100
        print(
            f"  本轮结果：训练损失={train_loss:.4f}  训练准确率={train_acc:.2%}  "
            f"当前验证集准确率={val_pct:.2f}%"
        )

        if val_acc > best_acc:
            best_acc = val_acc
            stale_epochs = 0
            checkpoint = {
                "model_state_dict": model.state_dict(),
                "classes": classes,
                "epoch": epoch,
            }
            path = os.path.join(args.output_dir, "best_model.pth")
            torch.save(checkpoint, path)
            print(f"  -> 已保存最佳模型到 {path}（验证集准确率 {val_pct:.2f}%）")
        else:
            stale_epochs += 1
            print(f"  -> 连续 {stale_epochs} 轮验证集未提升")

        if stale_epochs >= args.patience:
            print(f"\n触发早停：验证集连续 {args.patience} 轮未提升，提前结束训练。")
            break

    print(f"\n训练结束。共 {total_epochs} 轮，最佳验证集准确率: {best_acc:.2%} ({best_acc*100:.2f}%)")


if __name__ == "__main__":
    main()
