# -*- coding: utf-8 -*-
"""
苹果果实病害分类模型训练脚本
数据集：fruit_disease_dataset（Train/Test，4 类：Blotch_Apple, Normal_Apple, Rot_Apple, Scab_Apple）
采用与叶片相同的 MobileNetV3-Small + 速度优先策略，尽量 1 小时内完成
"""

import argparse
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_APP_DIR = os.path.dirname(SCRIPT_DIR)
if WEB_APP_DIR not in sys.path:
    sys.path.insert(0, WEB_APP_DIR)

import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from torchvision import transforms, models, datasets
from tqdm import tqdm

# 果实数据集路径：fruit 与 app.py 同级时为 WEB_APP_DIR/fruit/...；在 apple 下则为 SCRIPT_DIR/fruit/...
_dataset_candidates = [
    os.path.join(WEB_APP_DIR, "fruit", "fruit_disease_dataset", "dataset"),
    os.path.join(SCRIPT_DIR, "fruit", "fruit_disease_dataset", "dataset"),
]
DEFAULT_DATA_DIR = next((p for p in _dataset_candidates if os.path.isdir(p)), _dataset_candidates[0])
DEFAULT_OUTPUT_DIR = os.path.join(WEB_APP_DIR, "apple", "fruit_processed_dataset")
IMAGE_SIZE = 224
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]
DEFAULT_WORKERS = max(0, min(4, (os.cpu_count() or 1) - 1))


def get_train_transform():
    """增强数据增强，减轻过拟合、提升泛化"""
    return transforms.Compose([
        transforms.Resize((256, 256)),
        transforms.RandomResizedCrop(IMAGE_SIZE, scale=(0.7, 1.0), ratio=(0.9, 1.1)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(15),
        transforms.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.2),
        transforms.ToTensor(),
        transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
    ])


def get_val_transform():
    return transforms.Compose([
        transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
    ])


def _resolve_split_dirs(data_dir):
    """支持 Train/Test 或 train/test"""
    for train_name, test_name in [("Train", "Test"), ("train", "test")]:
        train_dir = os.path.join(data_dir, train_name)
        test_dir = os.path.join(data_dir, test_name)
        if os.path.isdir(train_dir):
            return train_dir, test_dir
    return None, None


def _find_dataset_root():
    """
    在 web_app 下自动递归查找包含 Train/Test（或 train/test）的数据根目录。
    返回找到的 dataset 根目录；找不到返回 None。
    """
    # 优先在 fruit 子树里找，再兜底全量 web_app
    search_roots = [
        os.path.join(WEB_APP_DIR, "fruit"),
        WEB_APP_DIR,
    ]
    checked = set()

    for root in search_roots:
        if not os.path.isdir(root):
            continue
        for current_root, dirs, _ in os.walk(root):
            # 排除一些明显无关目录，加快扫描
            lower_root = current_root.lower()
            if any(skip in lower_root for skip in [".venv", "node_modules", "__pycache__", ".git"]):
                continue

            key = os.path.normpath(current_root)
            if key in checked:
                continue
            checked.add(key)

            has_upper = ("Train" in dirs and "Test" in dirs)
            has_lower = ("train" in dirs and "test" in dirs)
            if has_upper or has_lower:
                return current_root
    return None


def prepare_data(data_dir, val_ratio=0.2):
    """使用 Train/Test（或 train/test），返回 (train_ds, val_ds, classes)。"""
    train_dir, test_dir = _resolve_split_dirs(data_dir)
    if train_dir is None:
        raise FileNotFoundError(
            f"未找到 Train 或 train 目录，请确认数据路径: {data_dir}\n"
            "期望结构: .../dataset/Train/Blotch_Apple/... 与 .../dataset/Test/..."
        )

    full_train = datasets.ImageFolder(train_dir, transform=get_train_transform())
    classes = list(full_train.classes)

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

    return train_ds, val_ds, classes


def build_model(num_classes, device, freeze_backbone=True):
    """MobileNetV3-Small + 分类头，分类头加 Dropout 减轻过拟合"""
    model = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.IMAGENET1K_V1)
    in_features = model.classifier[-1].in_features
    model.classifier[-1] = nn.Sequential(
        nn.Dropout(0.3),
        nn.Linear(in_features, num_classes),
    )
    if freeze_backbone:
        for param in model.features.parameters():
            param.requires_grad = False
    return model.to(device)


def train_one_epoch(model, loader, criterion, optimizer, device, epoch, total_epochs):
    model.train()
    total_loss, correct, total = 0.0, 0, 0
    pbar = tqdm(loader, desc=f"第 {epoch}/{total_epochs} 轮", unit="batch", ncols=100, leave=True)
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
    if hasattr(model, "features"):
        for param in model.features.parameters():
            param.requires_grad = True


def main():
    parser = argparse.ArgumentParser(description="苹果果实病害分类（MobileNetV3-Small 快速模式）")
    parser.add_argument("--data_dir", type=str, default=DEFAULT_DATA_DIR)
    parser.add_argument("--output_dir", type=str, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--epochs", type=int, default=15)
    parser.add_argument("--batch_size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--val_ratio", type=float, default=0.2)
    parser.add_argument("--device", type=str, default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--num_workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--patience", type=int, default=5)
    parser.add_argument("--unfreeze_epoch", type=int, default=4, help="第几轮解冻主干微调，提升泛化")
    args = parser.parse_args()

    # 如果默认 data_dir 不可用，自动递归查找包含 Train/Test 的目录
    train_dir, _ = _resolve_split_dirs(args.data_dir)
    if train_dir is None:
        auto_dir = _find_dataset_root()
        if auto_dir:
            print(f"自动发现数据目录: {os.path.abspath(auto_dir)}")
            args.data_dir = auto_dir

    os.makedirs(args.output_dir, exist_ok=True)
    device = torch.device(args.device)
    print(f"使用设备: {device}")
    print(f"数据目录: {os.path.abspath(args.data_dir)}")

    print("准备数据...")
    train_ds, val_ds, classes = prepare_data(args.data_dir, val_ratio=args.val_ratio)
    num_classes = len(classes)
    print(f"类别（按顺序）: {classes}")
    print(f"训练集样本数: {len(train_ds)}")
    print(f"验证集样本数: {len(val_ds)}")

    train_loader = DataLoader(
        train_ds, batch_size=args.batch_size, shuffle=True,
        num_workers=args.num_workers, pin_memory=(device.type == "cuda"),
    )
    val_loader = DataLoader(
        val_ds, batch_size=args.batch_size, shuffle=False,
        num_workers=args.num_workers, pin_memory=(device.type == "cuda"),
    )

    print("正在构建模型（加载预训练权重）...")
    model = build_model(num_classes, device, freeze_backbone=True)
    total_epochs = args.epochs
    print(
        f"\n共 {total_epochs} 轮训练，当前模式：MobileNetV3-Small + 仅训练分类头 + 早停\n"
        f"num_workers={args.num_workers}，batch_size={args.batch_size}，device={device}\n"
    )
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad],
        lr=args.lr,
        weight_decay=1e-2,
    )
    scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=5, gamma=0.5)

    best_acc = 0.0
    stale_epochs = 0
    for epoch in range(1, total_epochs + 1):
        if epoch == args.unfreeze_epoch:
            unfreeze_backbone(model)
            optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr * 0.1, weight_decay=1e-2)
            scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=5, gamma=0.5)
            print(f"  -> 第 {epoch} 轮解冻主干，进入微调（低学习率）")

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
            path = os.path.join(args.output_dir, "best_model.pth")
            torch.save({
                "model_state_dict": model.state_dict(),
                "classes": classes,
                "epoch": epoch,
            }, path)
            print(f"  -> 已保存最佳模型到 {path}（验证集准确率 {val_pct:.2f}%）")
        else:
            stale_epochs += 1
            print(f"  -> 连续 {stale_epochs} 轮验证集未提升")

        if stale_epochs >= args.patience:
            print(f"\n触发早停：验证集连续 {args.patience} 轮未提升。")
            break

    print(f"\n训练结束。最佳验证集准确率: {best_acc:.2%} ({best_acc*100:.2f}%)")


if __name__ == "__main__":
    main()
