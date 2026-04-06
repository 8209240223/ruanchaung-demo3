# -*- coding: utf-8 -*-
"""
Flask统一后端主文件
功能：统一控制demo1和demo2的模型，提供统一的前端界面
"""

import sys
import io
import os
import webbrowser
import sqlite3
import random
import heapq
import math
import copy
from datetime import datetime, timedelta
from functools import wraps
import re
import shutil
import subprocess
import uuid

# 设置控制台编码为UTF-8
if sys.platform == 'win32':
    import codecs
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    os.system('chcp 65001 >nul')

try:
    from flask import Flask, render_template, request, jsonify, send_from_directory, session, redirect, url_for, flash
    from flask_socketio import SocketIO, emit
    from werkzeug.utils import secure_filename
    from werkzeug.security import generate_password_hash, check_password_hash
    import torch
    import base64
    import requests
    import json
    import time
    import socket
    import cv2
    import numpy as np
    import threading
except ImportError as e:
    print(f"导入错误: {e}")
    print("请确保已安装所有依赖: py -m pip install Flask werkzeug torch torchvision requests flask-socketio")
    raise

from unified_predict import predict_and_annotate, predict_image
from unified_model_loader import MODEL_CONFIGS, reload_model, get_model, get_device, APPLE_DISEASE_MODEL_PATH, APPLE_FRUIT_DISEASE_MODEL_PATH
try:
    from video_processor import process_orchard_video
except ImportError:
    process_orchard_video = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, 'templates')
STATIC_DIR = os.path.join(BASE_DIR, 'static')
DATA_DIR = os.path.join(BASE_DIR, 'data')
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')
VIDEO_UPLOAD_DIR = os.path.join(BASE_DIR, 'static', 'uploads', 'video')
DEFAULT_HOST = os.getenv('APP_HOST', '0.0.0.0')
DEFAULT_PORT = int(os.getenv('APP_PORT', '5000'))
AUTO_OPEN_BROWSER = os.getenv('APP_AUTO_OPEN_BROWSER', '1') != '0'
AMAP_JS_KEY = os.getenv('AMAP_JS_KEY', '1d374242eb401cffe6f743aa981c577a')
ORCHARD_GEOJSON_PATH = os.path.join(DATA_DIR, 'orchard.geojson')
DB_PATH = os.path.join(BASE_DIR, 'agri_data.db')
ROLE_LEVELS = {
    'viewer': 1,
    'operator': 2,
    'agronomist': 3,
    'admin': 4
}

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    return conn

def init_database():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.executescript(
        """
        CREATE TABLE IF NOT EXISTS risk_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plot_name TEXT NOT NULL,
            risk_type TEXT NOT NULL,
            risk_level TEXT NOT NULL,
            probability REAL NOT NULL,
            operation_window TEXT NOT NULL,
            recommendation TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS irrigation_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plot_name TEXT NOT NULL,
            crop_type TEXT NOT NULL,
            growth_stage TEXT NOT NULL,
            soil_moisture REAL NOT NULL,
            weather_temp REAL NOT NULL,
            weather_rainfall REAL NOT NULL,
            suggested_water_lpm REAL NOT NULL,
            suggested_duration_min INTEGER NOT NULL,
            priority TEXT NOT NULL,
            recommendation TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            task_type TEXT NOT NULL,
            plot_name TEXT NOT NULL,
            priority TEXT NOT NULL,
            status TEXT NOT NULL,
            assignee TEXT,
            detail TEXT,
            planned_start TEXT,
            planned_end TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS operation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            log_type TEXT NOT NULL,
            source TEXT NOT NULL,
            related_task_id INTEGER,
            model_name TEXT,
            class_name TEXT,
            confidence REAL,
            action_summary TEXT NOT NULL,
            payload_json TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS orchard_missions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mission_name TEXT NOT NULL,
            strategy_json TEXT NOT NULL,
            status TEXT NOT NULL,
            score_total REAL,
            score_efficiency REAL,
            score_energy REAL,
            score_balance REAL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS orchard_telemetry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mission_id INTEGER,
            drone_id TEXT NOT NULL,
            zone_id TEXT,
            pos_x REAL NOT NULL,
            pos_y REAL NOT NULL,
            battery REAL,
            speed REAL,
            drone_status TEXT,
            event_type TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            action TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            method TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS drone_fleet (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            drone_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'idle',
            current_task_id INTEGER,
            charging_until TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL COLLATE NOCASE,
            email TEXT,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    conn.commit()
    # 初始化 50 架无人机（若表为空）
    rows = conn.execute("SELECT COUNT(*) AS c FROM drone_fleet").fetchone()
    if rows['c'] == 0:
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for i in range(1, 51):
            did = f'UAV-{i:02d}'
            conn.execute(
                "INSERT INTO drone_fleet (drone_id, name, status, current_task_id, charging_until, updated_at) VALUES (?, ?, 'idle', NULL, NULL, ?)",
                (did, f'无人机{i}号', now)
            )
        conn.commit()
    # 本地演示用固定管理员：登录后历史记录仍为数据库/JSON 全量，不按账号隔离
    row_wyj = conn.execute(
        "SELECT id FROM users WHERE username = ? COLLATE NOCASE LIMIT 1",
        ('wyj',),
    ).fetchone()
    now_admin = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ph_wyj = generate_password_hash('730423')
    if not row_wyj:
        conn.execute(
            "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
            ('wyj', None, ph_wyj, now_admin),
        )
    else:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE username = ? COLLATE NOCASE",
            (ph_wyj, 'wyj'),
        )
    conn.commit()
    conn.close()

def get_request_role():
    role = request.headers.get('X-User-Role') or request.args.get('role') or 'admin'
    role = role.lower()
    return role if role in ROLE_LEVELS else 'viewer'

def require_role(min_role):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            current_role = get_request_role()
            if ROLE_LEVELS.get(current_role, 0) < ROLE_LEVELS.get(min_role, 0):
                return jsonify({
                    'success': False,
                    'error': f'权限不足，需要 {min_role} 及以上角色',
                    'current_role': current_role
                }), 403
            return func(*args, **kwargs)
        return wrapper
    return decorator

def write_audit_log(action):
    try:
        conn = get_db_connection()
        conn.execute(
            """
            INSERT INTO audit_logs (role, action, endpoint, method, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                get_request_role(),
                action,
                request.path,
                request.method,
                datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[审计] 写入失败: {e}", flush=True)

def build_action_plan(class_name, confidence):
    confidence_val = float(confidence)
    confidence_band = '高' if confidence_val >= 85 else '中' if confidence_val >= 65 else '低'
    action = {
        'urgency': '中',
        'expected_benefit': '减少人工复检成本约 10%-15%',
        'next_steps': [
            '24小时内完成同地块复拍复核',
            '结合近三天气象数据调整灌溉与施药节奏',
            '若连续两次识别异常，自动创建巡检任务'
        ],
        'notes': '建议由农技员复核后再执行大规模农事操作'
    }
    if class_name in ('过成熟', 'Tomatoes') and confidence_val >= 80:
        action['urgency'] = '高'
        action['expected_benefit'] = '减少采后损耗约 8%-12%'
        action['next_steps'][0] = '12小时内完成重点区域采收或分拣'
    if confidence_band == '低':
        action['urgency'] = '复核'
        action['notes'] = '置信度偏低，需人工复核确认结果'
    return action

def build_risk_alerts(plot_name, weather_temp, humidity, rainfall):
    level = '低'
    probability = 0.2
    risk_type = '病害风险'
    recommendation = '保持例行巡检，暂不需要额外处理。'
    window = '未来72小时内每天下午巡检一次'

    if humidity >= 80 and rainfall >= 8:
        level = '高'
        probability = 0.82
        recommendation = '高湿叠加降雨，建议立即预防性喷施并增加排水巡检。'
        window = '未来24小时内完成处理'
    elif humidity >= 70 or rainfall >= 4:
        level = '中'
        probability = 0.58
        recommendation = '存在病害扩散条件，建议48小时内复查并局部处理。'
        window = '未来48小时内完成处理'
    elif weather_temp >= 33:
        risk_type = '虫害风险'
        level = '中'
        probability = 0.55
        recommendation = '高温可能提升虫害活跃度，建议增设诱捕监测点。'
        window = '未来48小时内完成诱捕布点'

    return {
        'plot_name': plot_name,
        'risk_type': risk_type,
        'risk_level': level,
        'probability': probability,
        'operation_window': window,
        'recommendation': recommendation
    }

def build_irrigation_plan(plot_name, crop_type, growth_stage, soil_moisture, weather_temp, rainfall):
    base_water_lpm = 18.0
    if growth_stage == '结果期':
        base_water_lpm = 22.0
    elif growth_stage == '苗期':
        base_water_lpm = 14.0

    moisture_gap = max(0.0, 65.0 - soil_moisture)
    temp_factor = 1.0 + max(0.0, weather_temp - 26.0) * 0.02
    rain_discount = max(0.5, 1.0 - rainfall * 0.03)

    suggested_water_lpm = round(base_water_lpm * (1.0 + moisture_gap / 100.0) * temp_factor * rain_discount, 2)
    suggested_duration_min = int(max(12, min(45, 18 + moisture_gap * 0.35)))

    priority = '高' if soil_moisture < 45 else '中' if soil_moisture < 60 else '低'
    recommendation = (
        f"{plot_name} 建议在清晨或傍晚灌溉，单次约 {suggested_duration_min} 分钟，"
        f"流量 {suggested_water_lpm} L/min，并在次日复测土壤湿度。"
    )

    return {
        'plot_name': plot_name,
        'crop_type': crop_type,
        'growth_stage': growth_stage,
        'soil_moisture': soil_moisture,
        'weather_temp': weather_temp,
        'weather_rainfall': rainfall,
        'suggested_water_lpm': suggested_water_lpm,
        'suggested_duration_min': suggested_duration_min,
        'priority': priority,
        'recommendation': recommendation
    }


def build_default_orchard_config():
    grid = {'width': 80, 'height': 60, 'cell_size': 14}
    geo_ref = {
        'origin_lng': 116.3975,  # 左上角参考点（GCJ-02）
        'origin_lat': 39.9098,
        'cell_meter': 3.0
    }
    zones = [
        {'id': 'Z1', 'name': '北一区', 'rect': [2, 2, 24, 20], 'risk_weight': 1.0},
        {'id': 'Z2', 'name': '北二区', 'rect': [26, 2, 50, 20], 'risk_weight': 1.3},
        {'id': 'Z3', 'name': '南一区', 'rect': [2, 22, 24, 52], 'risk_weight': 1.1},
        {'id': 'Z4', 'name': '南二区', 'rect': [26, 22, 50, 52], 'risk_weight': 1.4},
        {'id': 'Z5', 'name': '东区', 'rect': [52, 8, 76, 52], 'risk_weight': 1.2}
    ]
    obstacles = [
        {'id': 'O1', 'name': '机库', 'rect': [30, 25, 36, 32]},
        {'id': 'O2', 'name': '灌溉泵站', 'rect': [12, 28, 16, 34]},
        {'id': 'O3', 'name': '仓储区', 'rect': [60, 18, 68, 26]},
        {'id': 'O4', 'name': '高压线缓冲区', 'rect': [44, 40, 48, 52]}
    ]
    drones = [
        {'id': 'UAV-01', 'name': '无人机1号', 'start': [4, 56], 'speed': 4.6, 'battery': 100.0},
        {'id': 'UAV-02', 'name': '无人机2号', 'start': [10, 56], 'speed': 4.2, 'battery': 100.0},
        {'id': 'UAV-03', 'name': '无人机3号', 'start': [16, 56], 'speed': 4.0, 'battery': 100.0},
        {'id': 'UAV-04', 'name': '无人机4号', 'start': [22, 56], 'speed': 3.8, 'battery': 100.0}
    ]
    return {'grid': grid, 'geo_ref': geo_ref, 'zones': zones, 'obstacles': obstacles, 'drones': drones}


def grid_to_lnglat(x, y, geo_ref):
    origin_lng = float(geo_ref.get('origin_lng', 116.3975))
    origin_lat = float(geo_ref.get('origin_lat', 39.9098))
    cell_meter = float(geo_ref.get('cell_meter', 3.0))
    ref_lat = float(geo_ref.get('ref_lat', origin_lat))
    meters_x = x * cell_meter
    meters_y = y * cell_meter
    d_lat = meters_y / 111320.0
    d_lng = meters_x / (111320.0 * max(0.2, math.cos(ref_lat * math.pi / 180.0)))
    return [origin_lng + d_lng, origin_lat - d_lat]


def lnglat_to_grid(lng, lat, geo_ref):
    origin_lng = float(geo_ref.get('origin_lng', 116.3975))
    origin_lat = float(geo_ref.get('origin_lat', 39.9098))
    cell_meter = float(geo_ref.get('cell_meter', 3.0))
    ref_lat = float(geo_ref.get('ref_lat', origin_lat))
    meters_x = (float(lng) - origin_lng) * 111320.0 * max(0.2, math.cos(ref_lat * math.pi / 180.0))
    meters_y = (origin_lat - float(lat)) * 111320.0
    return [meters_x / cell_meter, meters_y / cell_meter]


def point_in_polygon(px, py, polygon):
    inside = False
    n = len(polygon)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        intersects = ((yi > py) != (yj > py)) and (
            px < (xj - xi) * (py - yi) / ((yj - yi) if (yj - yi) != 0 else 1e-9) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def polygon_to_rect(poly):
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return [int(math.floor(min(xs))), int(math.floor(min(ys))), int(math.ceil(max(xs))), int(math.ceil(max(ys)))]


def load_orchard_geojson(path):
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        geo = json.load(f)
    features = geo.get('features', [])
    if not features:
        return None

    boundary_lnglat = None
    hangar_lnglat = None
    zones_geo = []
    obstacles_geo = []
    launch_points_geo = []

    for ft in features:
        props = ft.get('properties', {}) or {}
        ftype = props.get('feature_type', '')
        geom = ft.get('geometry', {}) or {}
        gtype = geom.get('type')
        coords = geom.get('coordinates', [])
        if gtype == 'Polygon' and coords and coords[0]:
            ring = [[float(p[0]), float(p[1])] for p in coords[0]]
            if ftype == 'boundary':
                boundary_lnglat = ring
            elif ftype == 'hangar':
                hangar_lnglat = ring
            elif ftype == 'zone':
                zones_geo.append((props, ring))
            elif ftype in ('obstacle', 'no_fly'):
                obstacles_geo.append((props, ring))
        elif gtype == 'Point' and len(coords) >= 2 and ftype == 'launch_point':
            launch_points_geo.append((props, [float(coords[0]), float(coords[1])]))

    if not boundary_lnglat:
        return None

    lons = [p[0] for p in boundary_lnglat]
    lats = [p[1] for p in boundary_lnglat]
    min_lng, max_lng = min(lons), max(lons)
    min_lat, max_lat = min(lats), max(lats)
    center_lat = (min_lat + max_lat) / 2.0

    cell_meter = 3.0
    geo_ref = {
        'origin_lng': min_lng,
        'origin_lat': max_lat,
        'cell_meter': cell_meter,
        'ref_lat': center_lat
    }
    width_m = (max_lng - min_lng) * 111320.0 * max(0.2, math.cos(center_lat * math.pi / 180.0))
    height_m = (max_lat - min_lat) * 111320.0
    grid = {
        'width': max(20, int(math.ceil(width_m / cell_meter)) + 4),
        'height': max(20, int(math.ceil(height_m / cell_meter)) + 4),
        'cell_size': 12
    }

    boundary_grid = [lnglat_to_grid(p[0], p[1], geo_ref) for p in boundary_lnglat]

    hangar_grid = None
    hangar_center = None
    hangar_polygon_lnglat = None
    if hangar_lnglat:
        hangar_grid = [lnglat_to_grid(p[0], p[1], geo_ref) for p in hangar_lnglat]
        hangar_rect = polygon_to_rect(hangar_grid)
        x1, y1, x2, y2 = hangar_rect
        hangar_center = ((x1 + x2) // 2, (y1 + y2) // 2)
        hangar_polygon_lnglat = hangar_lnglat

    zones = []
    for idx, (props, ring) in enumerate(zones_geo):
        poly_grid = [lnglat_to_grid(p[0], p[1], geo_ref) for p in ring]
        rect = polygon_to_rect(poly_grid)
        zones.append({
            'id': str(props.get('id') or props.get('zone_id') or f'Z{idx + 1}'),
            'name': str(props.get('name') or f'分区{idx + 1}'),
            'risk_weight': float(props.get('risk_weight', 1.0)),
            'polygon_lnglat': ring,
            'polygon': poly_grid,
            'rect': rect
        })

    # 如果分区数量不足，按边界矩形自动细分为10块（满足“10架无人机分区域巡查”）
    desired_drone_count = 10
    if boundary_grid and len(zones) < desired_drone_count:
        bx1, by1, bx2, by2 = polygon_to_rect(boundary_grid)
        cols, rows = 5, 2
        cell_w = max(1, (bx2 - bx1 + 1) // cols)
        cell_h = max(1, (by2 - by1 + 1) // rows)
        gen = []
        idx = 1
        for ry in range(rows):
            for cx in range(cols):
                zx1 = bx1 + cx * cell_w
                zy1 = by1 + ry * cell_h
                zx2 = (bx1 + (cx + 1) * cell_w - 1) if cx < cols - 1 else bx2
                zy2 = (by1 + (ry + 1) * cell_h - 1) if ry < rows - 1 else by2
                gen.append({
                    'id': f'P{idx:02d}',
                    'name': f'巡查区{idx:02d}',
                    'risk_weight': 1.0,
                    'rect': [zx1, zy1, zx2, zy2]
                })
                idx += 1
        zones = gen[:desired_drone_count]

    obstacles = []
    for idx, (props, ring) in enumerate(obstacles_geo):
        poly_grid = [lnglat_to_grid(p[0], p[1], geo_ref) for p in ring]
        rect = polygon_to_rect(poly_grid)
        obstacles.append({
            'id': str(props.get('id') or f'O{idx + 1}'),
            'name': str(props.get('name') or f'障碍{idx + 1}'),
            'polygon_lnglat': ring,
            'polygon': poly_grid,
            'rect': rect
        })

    # 强制使用10架无人机，并全部从机库内起飞（避免GeoJSON里点位数量不一致导致“不是10架”）
    drones = []
    count = desired_drone_count
    if hangar_center is not None:
        offsets = []
        # 简单螺旋/网格偏移，保证初始点尽量分散且落在机库内
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                offsets.append((dx * 2, dy * 2))
        for i in range(count):
            dx, dy = offsets[i % len(offsets)]
            start_grid = (hangar_center[0] + dx, hangar_center[1] + dy)
            if hangar_grid and not point_in_polygon(start_grid[0] + 0.5, start_grid[1] + 0.5, hangar_grid):
                start_grid = hangar_center
            start = [int(round(start_grid[0])), int(round(start_grid[1]))]
            drones.append({
                'id': f'UAV-{i + 1:02d}',
                'name': f'无人机{i + 1}号',
                'start': start,
                'start_lnglat': grid_to_lnglat(start[0] + 0.5, start[1] + 0.5, geo_ref),
                'speed': 12.0,  # 提升展示速度（执行速度由tick控制）
                'battery': 100.0
            })
    else:
        for i in range(count):
            start = [3 + (i % 5) * 3, grid['height'] - 4 - (i // 5) * 3]
            drones.append({
                'id': f'UAV-{i + 1:02d}',
                'name': f'无人机{i + 1}号',
                'start': start,
                'start_lnglat': grid_to_lnglat(start[0], start[1], geo_ref),
                'speed': 12.0,
                'battery': 100.0
            })

    if not zones:
        zones = [
            {'id': 'Z1', 'name': '果园主区', 'rect': [3, 3, grid['width'] - 4, grid['height'] - 4], 'risk_weight': 1.0}
        ]

    result = {
        'grid': grid,
        'geo_ref': geo_ref,
        'boundary_polygon_lnglat': boundary_lnglat,
        'boundary_polygon': boundary_grid,
        'zones': zones,
        'obstacles': obstacles,
        'drones': drones,
        'desired_drone_count': desired_drone_count,
        'source': 'geojson'
    }
    if hangar_polygon_lnglat is not None and hangar_center is not None:
        result['hangar_polygon_lnglat'] = hangar_polygon_lnglat
        result['hangar_center'] = hangar_center
    return result


def build_orchard_config():
    loaded = load_orchard_geojson(ORCHARD_GEOJSON_PATH)
    if loaded:
        return loaded
    return build_default_orchard_config()


def rect_contains(rect, x, y):
    x1, y1, x2, y2 = rect
    return x1 <= x <= x2 and y1 <= y <= y2


def zone_center(zone):
    x1, y1, x2, y2 = zone['rect']
    return ((x1 + x2) // 2, (y1 + y2) // 2)


def is_cell_blocked(x, y, obstacles, boundary_polygon=None):
    if boundary_polygon and not point_in_polygon(x + 0.5, y + 0.5, boundary_polygon):
        return True
    cx, cy = x + 0.5, y + 0.5
    for obs in obstacles:
        rect = obs.get('rect')
        # 快速包围盒预筛选，排除大多数不相关障碍物，避免 point_in_polygon 的高代价调用
        if rect and not rect_contains(rect, x, y):
            continue
        poly = obs.get('polygon')
        if poly:
            if point_in_polygon(cx, cy, poly):
                return True
        elif rect and rect_contains(rect, x, y):
            return True
    return False


def build_blocked_set(grid, obstacles, boundary_polygon=None):
    """预计算整个网格中所有阻塞格子，返回 frozenset，供 A* 等函数 O(1) 查询。"""
    w = grid['width']
    h = grid['height']
    blocked = set()
    for y in range(h):
        for x in range(w):
            if is_cell_blocked(x, y, obstacles, boundary_polygon):
                blocked.add((x, y))
    return frozenset(blocked)


def neighbors_4(x, y, grid):
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nx, ny = x + dx, y + dy
        if 0 <= nx < grid['width'] and 0 <= ny < grid['height']:
            yield nx, ny


def astar_path(start, goal, grid, obstacles, boundary_polygon=None, blocked_set=None):
    """A* 寻路。blocked_set 不为 None 时用预计算集合做 O(1) 障碍查询（大图必须用）。"""
    def cell_blocked(x, y):
        if blocked_set is not None:
            return (x, y) in blocked_set
        return is_cell_blocked(x, y, obstacles, boundary_polygon)

    if start == goal:
        return [start]
    if cell_blocked(goal[0], goal[1]):
        return [start]

    def heuristic(a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    open_heap = []
    heapq.heappush(open_heap, (0, start))
    came_from = {}
    g_score = {start: 0}
    f_score = {start: heuristic(start, goal)}
    visited = set()

    while open_heap:
        _, current = heapq.heappop(open_heap)
        if current in visited:
            continue
        visited.add(current)
        if current == goal:
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            return list(reversed(path))

        for nxt in neighbors_4(current[0], current[1], grid):
            if cell_blocked(nxt[0], nxt[1]):
                continue
            tentative = g_score[current] + 1
            if tentative < g_score.get(nxt, 10**9):
                came_from[nxt] = current
                g_score[nxt] = tentative
                f_score[nxt] = tentative + heuristic(nxt, goal)
                heapq.heappush(open_heap, (f_score[nxt], nxt))
    return [start]


def build_zone_coverage_points(zone, obstacles, boundary_polygon=None, row_step=2):
    """row_step=2 提高覆盖密度，快速扫过果园"""
    x1, y1, x2, y2 = zone['rect']
    zone_poly = zone.get('polygon')
    points = []
    forward = True
    for y in range(y1, y2 + 1, row_step):
        row = []
        x_iter = range(x1, x2 + 1, 2) if forward else range(x2, x1 - 1, -2)
        for x in x_iter:
            if zone_poly and not point_in_polygon(x + 0.5, y + 0.5, zone_poly):
                continue
            if not is_cell_blocked(x, y, obstacles, boundary_polygon):
                row.append((x, y))
        if row:
            points.extend(row)
            forward = not forward
    return points


def build_zone_lawnmower_path(zone, grid, obstacles, boundary_polygon=None, x_step=1, row_step=2, blocked_set=None):
    """生成连续扫掠路径。blocked_set 不为 None 时用预计算集合做 O(1) 障碍查询。"""
    def cell_blocked(x, y):
        if blocked_set is not None:
            return (x, y) in blocked_set
        return is_cell_blocked(x, y, obstacles, boundary_polygon)

    x1, y1, x2, y2 = zone['rect']
    zone_poly = zone.get('polygon')
    path = []
    forward = True
    last = None
    for y in range(y1, y2 + 1, row_step):
        x_iter = range(x1, x2 + 1, x_step) if forward else range(x2, x1 - 1, -x_step)
        for x in x_iter:
            if zone_poly and not point_in_polygon(x + 0.5, y + 0.5, zone_poly):
                continue
            if cell_blocked(x, y):
                continue
            cur = (x, y)
            if last is None:
                path.append(cur)
                last = cur
                continue
            if abs(cur[0] - last[0]) + abs(cur[1] - last[1]) <= 1:
                path.append(cur)
                last = cur
                continue
            seg = astar_path(last, cur, grid, obstacles, boundary_polygon, blocked_set=blocked_set)
            if len(seg) > 1:
                path.extend(seg[1:])
                last = cur
            else:
                continue
        forward = not forward
    return path


def build_zone_sample_points(zone, obstacles, boundary_polygon=None, step=8, max_points=36, blocked_set=None):
    """在分区内按网格抽样少量点，用于快速规划（避免海量航点导致卡顿）。"""
    def cell_blocked(x, y):
        if blocked_set is not None:
            return (x, y) in blocked_set
        return is_cell_blocked(x, y, obstacles, boundary_polygon)

    x1, y1, x2, y2 = zone['rect']
    zone_poly = zone.get('polygon')
    pts = []
    for y in range(y1, y2 + 1, step):
        for x in range(x1, x2 + 1, step):
            if zone_poly and not point_in_polygon(x + 0.5, y + 0.5, zone_poly):
                continue
            if cell_blocked(x, y):
                continue
            pts.append((x, y))
            if len(pts) >= max_points:
                return pts
    if not pts:
        cx, cy = zone_center(zone)
        if (not zone_poly) or point_in_polygon(cx + 0.5, cy + 0.5, zone_poly):
            if not cell_blocked(cx, cy):
                pts.append((cx, cy))
    return pts


def nearest_neighbor_order(start, waypoints):
    """贪心最近邻排序，缩短总路径以快速覆盖"""
    if not waypoints:
        return []
    remaining = list(waypoints)
    ordered = []
    current = start
    while remaining:
        nearest = min(remaining, key=lambda p: abs(p[0] - current[0]) + abs(p[1] - current[1]))
        ordered.append(nearest)
        remaining.remove(nearest)
        current = nearest
    return ordered


def assign_zones_to_drones(zones, drones, obstacles=None, boundary_polygon=None):
    """按航点数量分配分区，使各无人机工作量接近"""
    drone_load = {d['id']: 0.0 for d in drones}
    assignments = {d['id']: [] for d in drones}
    zone_scored = []
    for z in zones:
        if obstacles is not None and boundary_polygon is not None:
            wp_count = len(build_zone_coverage_points(z, obstacles, boundary_polygon))
            score = wp_count * float(z.get('risk_weight', 1.0))
        else:
            x1, y1, x2, y2 = z['rect']
            score = max(1, (x2 - x1 + 1) * (y2 - y1 + 1)) * float(z.get('risk_weight', 1.0))
        zone_scored.append((score, z))
    zone_scored.sort(key=lambda x: x[0], reverse=True)

    for score, zone in zone_scored:
        drone_id = min(drone_load, key=lambda k: drone_load[k])
        assignments[drone_id].append(zone)
        drone_load[drone_id] += score
    return assignments


def rebalance_assignments(assignments, drones, zones, grid, obstacles, boundary_polygon, max_iters=8):
    """迭代调整分区分配，使各无人机路径长度更均衡"""
    def _build_paths(assigns):
        raw = {}
        for drone in drones:
            drone_id = drone['id']
            start = tuple(drone['start'])
            zs = assigns.get(drone_id, [])
            waypoints = []
            for z in zs:
                waypoints.extend(build_zone_coverage_points(z, obstacles, boundary_polygon))
            if waypoints:
                waypoints = nearest_neighbor_order(start, waypoints)
                path = merge_paths_by_waypoints(start, waypoints, grid, obstacles, boundary_polygon)
                if path:
                    last_cell = path[-1]
                    return_seg = astar_path(last_cell, start, grid, obstacles, boundary_polygon)
                    if len(return_seg) > 1:
                        path = path + return_seg[1:]
            else:
                path = []
            raw[drone_id] = path
        timed = apply_time_window_conflicts(raw)
        return {k: len(v) for k, v in timed.items() if v}

    lengths = _build_paths(assignments)
    if not lengths or len(lengths) < 2:
        return assignments
    for _ in range(max_iters):
        max_drone = max(lengths, key=lambda k: lengths[k])
        min_drone = min(lengths, key=lambda k: lengths[k])
        if lengths[max_drone] - lengths[min_drone] < max(5, lengths[max_drone] * 0.15):
            break
        max_zones = list(assignments.get(max_drone, []))
        if not max_zones:
            break
        best_zone, best_delta = None, float('inf')
        for z in max_zones:
            new_assign = copy.deepcopy(assignments)
            new_assign[max_drone] = [x for x in max_zones if x != z]
            new_assign[min_drone] = list(assignments.get(min_drone, [])) + [z]
            new_lens = _build_paths(new_assign)
            if not new_lens:
                continue
            new_max = max(new_lens.values())
            new_min = min(new_lens.values())
            delta = new_max - new_min
            if delta < best_delta:
                best_delta = delta
                best_zone = z
        if best_zone is None:
            break
        assignments[max_drone] = [x for x in max_zones if x != best_zone]
        assignments[min_drone] = list(assignments.get(min_drone, [])) + [best_zone]
        lengths = _build_paths(assignments)
    return assignments


def merge_paths_by_waypoints(start, waypoints, grid, obstacles, boundary_polygon=None, blocked_set=None):
    path = [start]
    current = start
    for wp in waypoints:
        segment = astar_path(current, wp, grid, obstacles, boundary_polygon, blocked_set=blocked_set)
        if len(segment) > 1:
            path.extend(segment[1:])
            current = wp
    return path


def apply_time_window_conflicts(paths_by_drone):
    """路径长的无人机优先预留，减少等待，使完成时间更均衡"""
    reserved = {}
    timed_paths = {}
    items = sorted(paths_by_drone.items(), key=lambda x: -len(x[1]) if x[1] else 0)
    for drone_id, raw_path in items:
        if not raw_path:
            timed_paths[drone_id] = []
            continue
        timed = []
        t = 0
        for cell in raw_path:
            while (cell[0], cell[1], t) in reserved:
                wait_cell = timed[-1] if timed else cell
                timed.append(wait_cell)
                reserved[(wait_cell[0], wait_cell[1], t)] = drone_id
                t += 1
            timed.append(cell)
            reserved[(cell[0], cell[1], t)] = drone_id
            t += 1
        timed_paths[drone_id] = timed
    return timed_paths


def score_plan(timed_paths):
    lengths = [len(p) for p in timed_paths.values() if p]
    if not lengths:
        return {'total': 0.0, 'efficiency': 0.0, 'energy': 0.0, 'balance': 0.0}
    makespan = max(lengths)
    total_distance = sum(lengths)
    avg = sum(lengths) / len(lengths)
    variance = sum((l - avg) ** 2 for l in lengths) / max(1, len(lengths))
    std = math.sqrt(variance)

    efficiency = max(0.0, 100.0 - makespan * 0.45)
    energy = max(0.0, 100.0 - total_distance * 0.18)
    balance = max(0.0, 100.0 - std * 6.5)
    total = round(efficiency * 0.45 + energy * 0.25 + balance * 0.30, 2)
    return {
        'total': total,
        'efficiency': round(efficiency, 2),
        'energy': round(energy, 2),
        'balance': round(balance, 2)
    }


def path_to_lnglat(path, geo_ref):
    return [grid_to_lnglat(x + 0.5, y + 0.5, geo_ref) for x, y in path]


def build_orchard_plan(config):
    zones = config['zones']
    drones = config['drones']
    obstacles = config['obstacles']
    grid = config['grid']
    boundary_polygon = config.get('boundary_polygon')
    geo_ref = config.get('geo_ref', {})
    hangar_center = config.get('hangar_center')
    return_dest = hangar_center if hangar_center is not None else None
    blocked_set = build_blocked_set(grid, obstacles, boundary_polygon)

    # 目标：最快完成。优先用“规则扫掠路径”避免规划卡顿；分区不足时按无人机数量自动细分。
    desired = int(config.get('desired_drone_count', 10) or 10)
    drones_sorted = list(drones)[:desired]
    zones_sorted = list(zones)
    if len(zones_sorted) < len(drones_sorted) and boundary_polygon:
        bx1, by1, bx2, by2 = polygon_to_rect(boundary_polygon)
        cols, rows = 5, 2
        cell_w = max(1, (bx2 - bx1 + 1) // cols)
        cell_h = max(1, (by2 - by1 + 1) // rows)
        gen = []
        idx = 1
        for ry in range(rows):
            for cx in range(cols):
                zx1 = bx1 + cx * cell_w
                zy1 = by1 + ry * cell_h
                zx2 = (bx1 + (cx + 1) * cell_w - 1) if cx < cols - 1 else bx2
                zy2 = (by1 + (ry + 1) * cell_h - 1) if ry < rows - 1 else by2
                gen.append({
                    'id': f'P{idx:02d}',
                    'name': f'巡查区{idx:02d}',
                    'risk_weight': 1.0,
                    'rect': [zx1, zy1, zx2, zy2]
                })
                idx += 1
        zones_sorted = gen[:len(drones_sorted)]

    # 一机一区：按顺序绑定（避免rebalance多轮A*导致“点按钮无反应”）
    assignments = {d['id']: [] for d in drones_sorted}
    for i, z in enumerate(zones_sorted):
        if not drones_sorted:
            break
        d = drones_sorted[i % len(drones_sorted)]
        assignments[d['id']].append(z)
    raw_paths = {}
    zone_assignment_view = {}

    for drone in drones_sorted:
        drone_id = drone['id']
        start = tuple(drone['start'])
        assigned_zones = assignments.get(drone_id, [])
        zone_assignment_view[drone_id] = [z['id'] for z in assigned_zones]
        waypoints = []
        for z in assigned_zones:
            pts = build_zone_sample_points(z, obstacles, boundary_polygon=boundary_polygon, step=8, max_points=36, blocked_set=blocked_set)
            waypoints.extend(pts)
        if not waypoints and assigned_zones:
            cx, cy = zone_center(assigned_zones[0])
            if (cx, cy) not in blocked_set:
                waypoints = [(cx, cy)]
        waypoints = nearest_neighbor_order(start, waypoints)
        path = merge_paths_by_waypoints(start, waypoints, grid, obstacles, boundary_polygon=boundary_polygon, blocked_set=blocked_set) if waypoints else [start]
        if path and return_dest is not None:
            last_cell = path[-1]
            dest_tuple = tuple(return_dest)
            return_seg = astar_path(last_cell, dest_tuple, grid, obstacles, boundary_polygon, blocked_set=blocked_set)
            if len(return_seg) > 1:
                path.extend(return_seg[1:])
        raw_paths[drone_id] = path

    # 最快完成：不做时间窗冲突等待（否则路径会被插入大量“等待格子”，规划和执行都变慢）
    timed_paths = raw_paths
    scores = score_plan(timed_paths)
    timed_paths_lnglat = {k: path_to_lnglat(v, geo_ref) for k, v in timed_paths.items()}
    return {
        'assignments': zone_assignment_view,
        'raw_paths': raw_paths,
        'timed_paths': timed_paths,
        'timed_paths_lnglat': timed_paths_lnglat,
        'scores': scores
    }

def normalize_risk_level(value):
    if not value:
        return '中'
    value = str(value).strip().lower()
    mapping = {
        'high': '高',
        'medium': '中',
        'low': '低',
        '严重': '高',
        '重度': '高',
        '中度': '中',
        '轻度': '低',
        '高': '高',
        '中': '中',
        '低': '低'
    }
    for k, v in mapping.items():
        if k in value:
            return v
    return '中'

def extract_json_like_text(content):
    if not content:
        return ""
    text = content.strip()
    fenced = re.findall(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE)
    if fenced:
        for block in fenced:
            block = block.strip()
            if block.startswith('{') and block.endswith('}'):
                return block
    first = text.find('{')
    last = text.rfind('}')
    if first != -1 and last != -1 and first < last:
        return text[first:last + 1]
    return ""

def ensure_structured_diagnosis(result):
    template = {
        'disease_name': '未知病虫害',
        'risk_level': '中',
        'confidence': 0.5,
        'action_window': '未来48小时内复查',
        'treatment_plan': ['先隔离疑似病株', '补拍叶片和果实近景', '由农技员复核后再执行处置'],
        'raw_text': ''
    }

    if isinstance(result, dict):
        data = result
    else:
        data = {}
        raw = str(result or '').strip()
        data['raw_text'] = raw
        json_text = extract_json_like_text(raw)
        if json_text:
            try:
                parsed = json.loads(json_text)
                if isinstance(parsed, dict):
                    data.update(parsed)
            except Exception:
                pass

        if 'disease_name' not in data:
            m = re.search(r"(病虫害类型|疾病名称|病害名称)[:：]\s*([^\n]+)", raw)
            if m:
                data['disease_name'] = m.group(2).strip()
        if 'risk_level' not in data:
            m = re.search(r"(风险等级|严重程度)[:：]\s*([^\n]+)", raw)
            if m:
                data['risk_level'] = m.group(2).strip()
        if 'action_window' not in data:
            m = re.search(r"(处理时窗|建议处理时窗|防治时机)[:：]\s*([^\n]+)", raw)
            if m:
                data['action_window'] = m.group(2).strip()
        if 'treatment_plan' not in data:
            plans = re.findall(r"(?:^|\n)\s*(?:[-*•]|\d+[\.、])\s*(.+)", raw)
            if plans:
                data['treatment_plan'] = [p.strip() for p in plans[:3] if p.strip()]

    diagnosis = dict(template)
    diagnosis['disease_name'] = str(data.get('disease_name') or template['disease_name']).strip()
    diagnosis['risk_level'] = normalize_risk_level(data.get('risk_level'))
    try:
        confidence = float(data.get('confidence', template['confidence']))
    except Exception:
        confidence = template['confidence']
    diagnosis['confidence'] = max(0.0, min(1.0, confidence))
    diagnosis['action_window'] = str(data.get('action_window') or template['action_window']).strip()

    treatment_plan = data.get('treatment_plan', template['treatment_plan'])
    if isinstance(treatment_plan, str):
        treatment_plan = [x.strip() for x in re.split(r"[;\n]+", treatment_plan) if x.strip()]
    if not isinstance(treatment_plan, list):
        treatment_plan = list(template['treatment_plan'])
    treatment_plan = [str(x).strip() for x in treatment_plan if str(x).strip()]
    if not treatment_plan:
        treatment_plan = list(template['treatment_plan'])
    diagnosis['treatment_plan'] = treatment_plan[:3]
    diagnosis['raw_text'] = str(data.get('raw_text') or '').strip()
    return diagnosis

# 获取本机局域网IP地址
def get_local_ip():
    """获取本机局域网IP地址"""
    try:
        # 连接到一个远程地址来获取本机IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception as e:
        print(f"获取IP地址失败: {e}")
        return "127.0.0.1"


def _patch_werkzeug_cookie_partitioned():
    """Flask 3.1+ 保存 session 时会传 partitioned=；Werkzeug<3.1 不支持该参数导致登录 500。"""
    try:
        import inspect
        from werkzeug.wrappers.response import Response

        if 'partitioned' in inspect.signature(Response.set_cookie).parameters:
            return
    except (TypeError, ValueError, ImportError):
        return

    _orig_set = Response.set_cookie

    def set_cookie(
        self,
        key,
        value='',
        max_age=None,
        expires=None,
        path='/',
        domain=None,
        secure=False,
        httponly=False,
        samesite=None,
        partitioned=False,
        **kwargs,
    ):
        kwargs.pop('partitioned', None)
        return _orig_set(
            self,
            key,
            value,
            max_age=max_age,
            expires=expires,
            path=path,
            domain=domain,
            secure=secure,
            httponly=httponly,
            samesite=samesite,
            **kwargs,
        )

    Response.set_cookie = set_cookie  # type: ignore[method-assign]

    _orig_del = Response.delete_cookie

    def delete_cookie(
        self,
        key,
        path='/',
        domain=None,
        secure=False,
        httponly=False,
        samesite=None,
        partitioned=False,
        **kwargs,
    ):
        kwargs.pop('partitioned', None)
        return _orig_del(
            self,
            key,
            path=path,
            domain=domain,
            secure=secure,
            httponly=httponly,
            samesite=samesite,
            **kwargs,
        )

    Response.delete_cookie = delete_cookie  # type: ignore[method-assign]


_patch_werkzeug_cookie_partitioned()

# 创建Flask应用
app = Flask(__name__, template_folder=TEMPLATES_DIR, static_folder=STATIC_DIR)
app.config['UPLOAD_FOLDER'] = UPLOAD_DIR
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 200MB（支持视频上传）
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'your-secret-key-change-in-production')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

# 初始化SocketIO
# 使用threading模式，禁用websocket升级避免兼容性问题
socketio = SocketIO(
    app, 
    cors_allowed_origins="*", 
    async_mode='threading',
    logger=False,
    engineio_logger=False,
    ping_timeout=60,
    ping_interval=25,
    allow_upgrades=False,  # 禁用websocket升级，只使用polling
    transports=['polling']  # 只使用polling传输
)

# 存储视频流数据
video_stream_data = {
    'frame': None,
    'timestamp': None,
    'clients': set()
}

# IP摄像头相关
ip_camera_url = None
ip_camera_thread = None
ip_camera_running = False

# 虚拟摄像头相关（无他伴侣等）
virtual_camera_enabled = False
virtual_camera_device_id = None  # 摄像头设备ID（0, 1, 2等）
virtual_camera_thread = None
virtual_camera_running = False

# 苹果检测相关
apple_detection_enabled = True  # 是否启用苹果检测（默认启用）
apple_detection_interval = 10  # 每N帧检测一次（降低计算量，提高性能）
apple_detection_cache = {'is_apple': False, 'confidence': 0.0, 'bbox': None}  # 缓存上一次的检测结果
apple_tracking = {
    'template': None,  # 模板图像（用于跟踪）
    'last_bbox': None,  # 上一次的边界框
    'last_frame': None,  # 上一帧图像（用于光流）
    'tracking_failures': 0,  # 跟踪失败次数（已弃用，改用时间判断）
    'last_success_time': None,  # 最后一次成功检测/跟踪的时间戳
    'max_tracking_timeout': 5.0,  # 最大跟踪超时时间（秒），超过此时间才移除红框
    'velocity': (0, 0)  # 速度（用于预测位置）
}

# 果园多机调度仿真
orchard_lock = threading.Lock()
orchard_config = build_orchard_config()
orchard_state = {
    'mission_id': None,
    'mission_name': '',
    'status': 'idle',  # idle | planning | running | completed | paused
    'tick': 0,
    'started_at': None,
    'updated_at': None,
    'drones': [],
    'assignments': {},
    'planned_paths': {},
    'scores': {},
    'apple_detection': {
        'immature': 0,
        'mature': 0,
        'overripe': 0,
        'logs': []
    },
    'disease_detection': {
        'leaf': 0,
        'fruit': 0,
        'high': 0,
        'medium': 0,
        'low': 0,
        'logs': []
    }
}
orchard_sim_thread = None
orchard_sim_stop_event = None

# 确保上传文件夹存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(VIDEO_UPLOAD_DIR, exist_ok=True)
init_database()

# 视频分析任务进度 {task_id: {status, frame, total, preview, output_path, error}}
video_analyze_tasks = {}
video_analyze_lock = threading.Lock()


def cleanup_orphaned_dispatched_tasks():
    """服务器重启时：将未在地图上查看过的「执行中」派出任务全部置为已完成，释放无人机，便于展示巡检飞行"""
    conn = get_db_connection()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    rows = conn.execute(
        "SELECT id, assignee FROM tasks WHERE status = '执行中' AND assignee IS NOT NULL AND assignee LIKE 'UAV-%'"
    ).fetchall()
    for r in rows:
        task_id = r['id']
        assignee_val = r['assignee'] or ''
        conn.execute(
            "UPDATE tasks SET status = '已完成', updated_at = ? WHERE id = ?",
            (now, task_id)
        )
        if assignee_val:
            charging_until = (datetime.now() + timedelta(minutes=8)).strftime('%Y-%m-%d %H:%M:%S')
            conn.execute(
                "UPDATE drone_fleet SET status = 'charging', current_task_id = NULL, charging_until = ?, updated_at = ? WHERE drone_id = ?",
                (charging_until, now, assignee_val)
            )
    if rows:
        conn.commit()
        print(f"[启动] 已将 {len(rows)} 个未查看的派出任务置为已完成，释放无人机用于巡检演示", flush=True)
    conn.close()


cleanup_orphaned_dispatched_tasks()

# 检测设备
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f"使用设备: {device}")

# 启动时预加载两个模型
print("=" * 60)
print("正在加载模型...")
print("=" * 60)
for model_type in ['demo1', 'demo2']:
    try:
        reload_model(model_type, device=device)
    except Exception as e:
        print(f"✗ {MODEL_CONFIGS[model_type]['name']}模型加载失败: {e}")
        print(f"  请确保模型文件存在: {MODEL_CONFIGS[model_type]['model_path']}")
print("=" * 60)
print()

def print_startup_banner(host, port):
    """打印启动信息，便于直接运行 app.py。"""
    local_ip = get_local_ip()
    local_url = f"http://127.0.0.1:{port}"
    lan_url = f"http://{local_ip}:{port}"

    print("=" * 60)
    print("统一模型管理系统 (支持WebSocket视频流)")
    print("=" * 60)
    print(f"电脑端访问地址: {local_url}")
    print(f"手机端访问地址: {lan_url}")
    print(f"本机IP地址: {local_ip}")
    print(f"使用设备: {device}")
    try:
        rules = [r.rule for r in app.url_map.iter_rules()]
        print(f"App文件: {os.path.abspath(__file__)}")
        print(f"路由数量: {len(rules)}")
        print(f"路由检查: /灌溉={'/灌溉' in rules}  /irrigation={'/irrigation' in rules}  /__debug/app={'/__debug/app' in rules}")
    except Exception:
        pass

    missing_models = []
    for model_type, config in MODEL_CONFIGS.items():
        if not os.path.exists(config['model_path']):
            missing_models.append(f"{config['name']}: {config['model_path']}")

    if missing_models:
        print()
        print("警告: 以下模型文件不存在，相关识别功能将不可用:")
        for item in missing_models:
            print(f"  - {item}")

    print("=" * 60)
    print()
    return local_url

def open_browser_async(url):
    """延迟打开浏览器，避免阻塞服务启动。"""
    def _open():
        time.sleep(1.5)
        try:
            webbrowser.open(url)
        except Exception as e:
            print(f"自动打开浏览器失败: {e}", flush=True)

    threading.Thread(target=_open, daemon=True).start()

def allowed_file(filename):
    """检查文件扩展名是否允许"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


def safe_upload_filename(original_filename):
    """
    生成可落盘且带有效后缀的文件名。
    secure_filename 会去掉中文等非 ASCII，常导致只剩「jpg」而无「.jpg」，
    PIL Image.save 无法识别格式会报 unknown file extension。
    """
    orig = (original_filename or '').strip()
    _root, ext = os.path.splitext(orig)
    ext = ext.lower()
    if not ext or ext.lstrip('.') not in app.config['ALLOWED_EXTENSIONS']:
        ext = '.jpg'
    stem = secure_filename(os.path.splitext(orig)[0])
    if not stem or stem in ('.', '..'):
        stem = uuid.uuid4().hex[:12]
    return f'{stem}{ext}'


def pil_format_for_extension(ext):
    """根据扩展名返回 PIL save 的 format。"""
    e = (ext or '').lower()
    if e in ('.jpg', '.jpeg'):
        return 'JPEG'
    if e == '.png':
        return 'PNG'
    if e == '.gif':
        return 'GIF'
    if e == '.webp':
        return 'WEBP'
    return 'JPEG'


def serialize_path(path):
    return [[int(x), int(y)] for x, y in path]


def refresh_orchard_config():
    global orchard_config
    loaded = build_orchard_config()
    with orchard_lock:
        orchard_config = loaded
    return loaded


def orchard_snapshot():
    with orchard_lock:
        snap = copy.deepcopy(orchard_state)
    return snap


def emit_orchard_state(event_name='orchard_state'):
    snap = orchard_snapshot()
    socketio.emit(event_name, {'success': True, 'data': snap})


def start_orchard_rtb_simulation():
    """仅用于：当前没有仿真线程时，驱动无人机返航到机库。"""
    global orchard_sim_thread, orchard_sim_stop_event
    if orchard_sim_thread is not None and orchard_sim_thread.is_alive():
        return
    if orchard_sim_stop_event:
        orchard_sim_stop_event.set()
    orchard_sim_stop_event = threading.Event()

    grid = orchard_config['grid']
    obstacles = orchard_config['obstacles']
    boundary_polygon = orchard_config.get('boundary_polygon')
    hangar_center = orchard_config.get('hangar_center')
    return_target = tuple(hangar_center) if hangar_center is not None else None
    drone_starts = {d['id']: tuple(d['start']) for d in orchard_config.get('drones', [])}

    def _rtb_loop():
        while not orchard_sim_stop_event.is_set():
            all_idle = True
            with orchard_lock:
                for drone in orchard_state.get('drones', []):
                    drone_id = drone.get('drone_id')
                    start_cell = drone_starts.get(drone_id)
                    dest = return_target if return_target is not None else start_cell
                    if not dest:
                        drone['status'] = '空闲'
                        continue

                    if drone.get('return_path'):
                        ret_path = drone['return_path']
                        ret_idx = drone.get('return_idx', 0)
                        if ret_idx >= len(ret_path):
                            drone['status'] = '已返航'
                            drone.pop('return_path', None)
                            drone.pop('return_idx', None)
                            continue
                        all_idle = False
                        drone['status'] = '返航中'
                        px, py = ret_path[ret_idx]
                        drone['position'] = [px, py]
                        drone['position_lnglat'] = grid_to_lnglat(px + 0.5, py + 0.5, orchard_config['geo_ref'])
                        drone['battery'] = max(10.0, round(float(drone.get('battery', 100.0)) - 0.08, 2))
                        drone['return_idx'] = ret_idx + 1
                        continue

                    curr = drone.get('position') or [0, 0]
                    cx, cy = int(round(curr[0])), int(round(curr[1]))
                    if (cx, cy) == dest:
                        drone['status'] = '已返航'
                        continue
                    return_seg = astar_path((cx, cy), dest, grid, obstacles, boundary_polygon)
                    if len(return_seg) > 1:
                        drone['return_path'] = return_seg
                        drone['return_idx'] = 0
                        all_idle = False
                    else:
                        drone['position'] = [dest[0], dest[1]]
                        drone['position_lnglat'] = grid_to_lnglat(dest[0] + 0.5, dest[1] + 0.5, orchard_config['geo_ref'])
                        drone['status'] = '已返航'

                orchard_state['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                orchard_state['status'] = 'returning' if not all_idle else 'completed'

            emit_orchard_state('orchard_state')
            if all_idle:
                break
            # 为“最快巡查完毕”提高仿真推进速度（更快移动）
            time.sleep(0.05)

    orchard_sim_thread = threading.Thread(target=_rtb_loop, daemon=True)
    orchard_sim_thread.start()


def start_orchard_simulation(mission_id, mission_name, plan_result):
    global orchard_sim_thread, orchard_sim_stop_event
    if orchard_sim_thread is not None and orchard_sim_thread.is_alive():
        if orchard_sim_stop_event:
            orchard_sim_stop_event.set()
        orchard_sim_thread.join(timeout=1.2)

    orchard_sim_stop_event = threading.Event()
    now_text = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    with orchard_lock:
        orchard_state['mission_id'] = mission_id
        orchard_state['mission_name'] = mission_name
        orchard_state['status'] = 'running'
        orchard_state['tick'] = 0
        orchard_state['started_at'] = now_text
        orchard_state['updated_at'] = now_text
        orchard_state.pop('force_rtb', None)
        orchard_state['assignments'] = plan_result['assignments']
        orchard_state['planned_paths'] = {k: serialize_path(v) for k, v in plan_result['timed_paths'].items()}
        orchard_state['planned_paths_lnglat'] = plan_result.get('timed_paths_lnglat', {})
        orchard_state['scores'] = plan_result['scores']
        orchard_state['apple_detection'] = {'immature': 0, 'mature': 0, 'overripe': 0, 'logs': []}
        orchard_state['disease_detection'] = {'leaf': 0, 'fruit': 0, 'high': 0, 'medium': 0, 'low': 0, 'logs': []}
        orchard_state['drones'] = []
        for d in orchard_config['drones']:
            orchard_state['drones'].append({
                'drone_id': d['id'],
                'name': d['name'],
                'zone_ids': plan_result['assignments'].get(d['id'], []),
                'position': list(d['start']),
                'position_lnglat': d.get('start_lnglat') or grid_to_lnglat(d['start'][0] + 0.5, d['start'][1] + 0.5, orchard_config['geo_ref']),
                'battery': float(d.get('battery', 100.0)),
                'speed': float(d.get('speed', 4.0)),
                'status': '执行中'
            })

    _reported_cells = set()
    _apple_reported_cells = set()
    _disease_reported_cells = set()
    _last_apple_tick = {}
    _last_disease_tick = {}

    def _simulate_apple_detection(drone_id, px, py, zone_ids, tick):
        """模拟无人机检测到的苹果成熟度，更新 orchard_state['apple_detection']，总量目标约5000"""
        last_t = _last_apple_tick.get(drone_id, -10**9)
        # 加快：同一架无人机至少间隔 2s 才上报一次
        if tick - last_t < 40:
            return
        _last_apple_tick[drone_id] = tick
        cell_key = (drone_id, int(px), int(py))
        if cell_key in _apple_reported_cells:
            return
        if random.random() > 0.45:
            return
        _apple_reported_cells.add(cell_key)
        zone_name = zone_ids[0] if zone_ids else '果园'
        types = ['未成熟', '成熟', '过成熟']
        weights = [0.35, 0.50, 0.15]
        mat_type = random.choices(types, weights=weights)[0]
        # 单次检测数量加大，使总量较快达到约5000
        count = random.randint(80, 180)
        now = datetime.now().strftime('%H:%M:%S')
        try:
            # 注意：该函数在 _sim_loop 的 orchard_lock 内被调用，不能二次加锁，否则会死锁
            ad = orchard_state.get('apple_detection', {'immature': 0, 'mature': 0, 'overripe': 0, 'logs': []})
            total = ad.get('immature', 0) + ad.get('mature', 0) + ad.get('overripe', 0)
            if total >= 5000:
                return
            count = min(count, 5000 - total)
            if mat_type == '未成熟':
                ad['immature'] = ad.get('immature', 0) + count
            elif mat_type == '成熟':
                ad['mature'] = ad.get('mature', 0) + count
            else:
                ad['overripe'] = ad.get('overripe', 0) + count
            log = {'time': now, 'message': f'{drone_id}于{zone_name}检测到{mat_type}苹果{count}个', 'drone_id': drone_id, 'zone': zone_name, 'type': mat_type}
            logs = ad.get('logs', [])
            logs.insert(0, log)
            ad['logs'] = logs[:15]
            orchard_state['apple_detection'] = ad
        except Exception:
            pass

    def _simulate_disease_detection(drone_id, px, py, zone_ids, tick):
        """模拟叶片/果实病虫害检测，更新 orchard_state['disease_detection']（降频避免刷屏）"""
        last_t = _last_disease_tick.get(drone_id, -10**9)
        # 提速：同一架无人机至少间隔 6s 才上报一次病虫害
        if tick - last_t < 120:
            return
        _last_disease_tick[drone_id] = tick
        cell_key = (drone_id, int(px), int(py))
        if cell_key in _disease_reported_cells:
            return
        # 提高触发概率（仍有冷却限制，不会刷屏）
        if random.random() > 0.25:
            return
        _disease_reported_cells.add(cell_key)
        zone_name = zone_ids[0] if zone_ids else '果园'
        part = random.choice(['叶片', '果实'])
        leaf_types = ['苹果褐斑病', '蚜虫危害', '红蜘蛛', '轮纹病']
        fruit_types = ['炭疽病', '轮纹病', '腐烂风险']
        risk_type = random.choice(leaf_types if part == '叶片' else fruit_types)
        level = random.choices(['低', '中', '高'], weights=[0.45, 0.40, 0.15])[0]
        now = datetime.now().strftime('%H:%M:%S')
        dd = orchard_state.get('disease_detection', {'leaf': 0, 'fruit': 0, 'high': 0, 'medium': 0, 'low': 0, 'logs': []})
        if part == '叶片':
            dd['leaf'] = dd.get('leaf', 0) + 1
        else:
            dd['fruit'] = dd.get('fruit', 0) + 1
        if level == '高':
            dd['high'] = dd.get('high', 0) + 1
        elif level == '中':
            dd['medium'] = dd.get('medium', 0) + 1
        else:
            dd['low'] = dd.get('low', 0) + 1
        msg = f'{drone_id}于{zone_name}检测到{part}{risk_type}（{level}风险）'
        log = {'time': now, 'message': msg, 'drone_id': drone_id, 'zone': zone_name, 'part': part, 'risk_type': risk_type, 'level': level}
        logs = dd.get('logs', [])
        logs.insert(0, log)
        dd['logs'] = logs[:15]
        orchard_state['disease_detection'] = dd

    def _simulate_pest_detection(drone_id, px, py, zone_ids):
        """模拟无人机巡检时发现病虫害，写入 risk_alerts 和 operation_logs"""
        cell_key = (drone_id, int(px), int(py))
        if cell_key in _reported_cells:
            return
        if random.random() > 0.05:
            return
        _reported_cells.add(cell_key)
        plot_name = zone_ids[0] if zone_ids else '果园'
        types = ['苹果褐斑病', '蚜虫危害', '红蜘蛛', '轮纹病', '炭疽病']
        risk_type = random.choice(types)
        level = random.choice(['低', '中', '高'])
        prob = round(0.3 + random.random() * 0.5, 2)
        rec = f'无人机{drone_id}于{plot_name}检测到{risk_type}，建议48小时内复查。'
        window = '未来48小时内完成处理' if level != '高' else '未来24小时内完成处理'
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            conn = get_db_connection()
            conn.execute(
                """INSERT INTO risk_alerts
                (plot_name, risk_type, risk_level, probability, operation_window, recommendation, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (plot_name, risk_type, level, prob, window, rec, now)
            )
            conn.execute(
                """INSERT INTO operation_logs
                (log_type, source, related_task_id, model_name, class_name, confidence, action_summary, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                ('risk_alert', 'orchard_drone', None, '无人机巡检', risk_type, round(prob * 100, 2),
                 rec, json.dumps({'drone_id': drone_id, 'pos': [px, py], 'zone': plot_name}, ensure_ascii=False), now)
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    drone_starts = {d['id']: tuple(d['start']) for d in orchard_config['drones']}
    hangar_center = orchard_config.get('hangar_center')
    return_target = tuple(hangar_center) if hangar_center is not None else None
    grid = orchard_config['grid']
    obstacles = orchard_config['obstacles']
    boundary_polygon = orchard_config.get('boundary_polygon')

    def _sim_loop():
        timed_paths = plan_result['timed_paths']
        max_len = max([len(v) for v in timed_paths.values()] + [1])
        while not orchard_sim_stop_event.is_set():
            force_rtb = False
            with orchard_lock:
                force_rtb = bool(orchard_state.get('force_rtb'))
                tick = orchard_state['tick']
                all_idle = True
                for drone in orchard_state['drones']:
                    drone_id = drone['drone_id']
                    start_cell = drone_starts.get(drone_id)
                    dest = return_target if return_target is not None else start_cell

                    if force_rtb and dest:
                        curr = drone.get('position') or [0, 0]
                        cx, cy = int(round(curr[0])), int(round(curr[1]))
                        if (cx, cy) == dest and not drone.get('return_path'):
                            drone['status'] = '已返航'
                            continue
                        if not drone.get('return_path'):
                            return_seg = astar_path((cx, cy), dest, grid, obstacles, boundary_polygon)
                            if len(return_seg) > 1:
                                drone['return_path'] = return_seg
                                drone['return_idx'] = 0
                                all_idle = False
                                continue
                            drone['position'] = [dest[0], dest[1]]
                            drone['position_lnglat'] = grid_to_lnglat(dest[0] + 0.5, dest[1] + 0.5, orchard_config['geo_ref'])
                            drone['status'] = '已返航'
                            continue

                    path = timed_paths.get(drone_id, [])
                    if not path and not drone.get('return_path'):
                        drone['status'] = '空闲'
                        continue

                    if drone.get('return_path'):
                        ret_path = drone['return_path']
                        ret_idx = drone.get('return_idx', 0)
                        if ret_idx >= len(ret_path):
                            drone['status'] = '已返航'
                            drone.pop('return_path', None)
                            drone.pop('return_idx', None)
                            continue
                        all_idle = False
                        drone['status'] = '返航中'
                        px, py = ret_path[ret_idx]
                        drone['position'] = [px, py]
                        drone['position_lnglat'] = grid_to_lnglat(px + 0.5, py + 0.5, orchard_config['geo_ref'])
                        drone['battery'] = max(10.0, round(drone['battery'] - 0.08, 2))
                        drone['return_idx'] = ret_idx + 1
                        continue

                    idx = min(tick, len(path) - 1)
                    px, py = path[idx]
                    new_battery = max(10.0, round(drone['battery'] - 0.08, 2))
                    dest = return_target if return_target is not None else start_cell
                    if new_battery < 15.0 and dest and (int(px), int(py)) != dest:
                        return_seg = astar_path((int(px), int(py)), dest, grid, obstacles, boundary_polygon)
                        if len(return_seg) > 1:
                            drone['return_path'] = return_seg
                            drone['return_idx'] = 0
                            all_idle = False
                            continue

                    drone['position'] = [px, py]
                    drone['position_lnglat'] = grid_to_lnglat(px + 0.5, py + 0.5, orchard_config['geo_ref'])
                    drone['battery'] = new_battery
                    if idx >= len(path) - 1:
                        drone['status'] = '已返航'
                    else:
                        drone['status'] = '执行中'
                        all_idle = False
                    _simulate_pest_detection(drone_id, px, py, drone.get('zone_ids', []))
                    _simulate_apple_detection(drone_id, px, py, drone.get('zone_ids', []), tick)
                    _simulate_disease_detection(drone_id, px, py, drone.get('zone_ids', []), tick)
                orchard_state['tick'] += 1
                orchard_state['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                if force_rtb and all_idle:
                    orchard_state['status'] = 'completed'
                    try:
                        socketio.emit('drone_activity', {'message': '已下达返航指令：全部无人机已返航到机库', 'type': 'mission_complete'})
                    except Exception:
                        pass
                    break
                if tick >= max_len and all_idle:
                    orchard_state['status'] = 'completed'
                    try:
                        socketio.emit('drone_activity', {'message': f'任务「{orchard_state.get("mission_name", "")}」已完成，全部无人机已返航', 'type': 'mission_complete'})
                    except Exception:
                        pass
                    break

            emit_orchard_state('orchard_state')
            # 每约2秒向数据大屏推送一次无人机状态摘要
            if tick > 0 and tick % 20 == 0:
                for drone in orchard_state.get('drones', []):
                    if drone.get('status') in ('执行中', '返航中'):
                        msg = f"{drone.get('drone_id', '')} 巡检中 电量{drone.get('battery', 0):.0f}% 位置({drone.get('position', [0,0])[0]:.0f},{drone.get('position', [0,0])[1]:.0f})"
                        try:
                            socketio.emit('drone_activity', {'message': msg, 'type': 'status', 'drone_id': drone.get('drone_id')})
                        except Exception:
                            pass
            time.sleep(0.05)

        conn = get_db_connection()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with orchard_lock:
            final_status = orchard_state['status']
            final_drones = copy.deepcopy(orchard_state['drones'])

        for drone in final_drones:
            conn.execute(
                """
                INSERT INTO orchard_telemetry
                (mission_id, drone_id, zone_id, pos_x, pos_y, battery, speed, drone_status, event_type, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mission_id,
                    drone['drone_id'],
                    ','.join(drone.get('zone_ids', [])),
                    float(drone['position'][0]),
                    float(drone['position'][1]),
                    float(drone['battery']),
                    float(drone.get('speed', 0.0)),
                    drone['status'],
                    'mission_tick',
                    now
                )
            )
        conn.execute(
            "UPDATE orchard_missions SET status = ?, updated_at = ? WHERE id = ?",
            (final_status, now, mission_id)
        )
        conn.commit()
        conn.close()
        emit_orchard_state('orchard_state')

    try:
        socketio.emit('drone_activity', {'message': f'任务「{mission_name}」已启动，多机协同巡检中', 'type': 'mission_start'})
    except Exception:
        pass
    orchard_sim_thread = threading.Thread(target=_sim_loop, daemon=True)
    orchard_sim_thread.start()

USERNAME_PATTERN = re.compile(r'^[a-zA-Z0-9_\u4e00-\u9fff]{2,32}$')


def safe_next_url(val):
    if not val or not isinstance(val, str):
        return None
    val = val.strip()
    if not val.startswith('/') or val.startswith('//'):
        return None
    return val


def get_current_user():
    uid = session.get('user_id')
    if not uid:
        return None
    try:
        conn = get_db_connection()
        row = conn.execute(
            'SELECT id, username, email FROM users WHERE id = ?',
            (int(uid),),
        ).fetchone()
        conn.close()
    except (sqlite3.Error, TypeError, ValueError):
        return None
    if not row:
        session.pop('user_id', None)
        return None
    return {'id': row['id'], 'username': row['username'], 'email': row['email'] or ''}


@app.context_processor
def inject_current_user():
    return {'current_user': get_current_user()}


@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_id'):
        nxt = safe_next_url(request.args.get('next')) or safe_next_url(request.form.get('next'))
        return redirect(nxt or url_for('index'))
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        nxt = safe_next_url(request.form.get('next')) or safe_next_url(request.args.get('next'))
        if not username or not password:
            flash('请输入用户名和密码', 'error')
            return render_template('login.html', next=nxt or '')
        conn = get_db_connection()
        row = conn.execute(
            'SELECT id, password_hash FROM users WHERE username = ? COLLATE NOCASE',
            (username,),
        ).fetchone()
        conn.close()
        if not row or not check_password_hash(row['password_hash'], password):
            flash('用户名或密码错误', 'error')
            return render_template('login.html', next=nxt or '')
        session['user_id'] = row['id']
        session.permanent = True
        return redirect(nxt or url_for('index'))
    return render_template('login.html', next=safe_next_url(request.args.get('next')) or '')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if session.get('user_id'):
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        password2 = request.form.get('password2') or ''
        email = (request.form.get('email') or '').strip() or None
        if not USERNAME_PATTERN.match(username):
            flash('用户名为 2～32 位，可使用字母、数字、下划线或中文', 'error')
            return render_template('register.html')
        if len(password) < 8:
            flash('密码至少 8 位', 'error')
            return render_template('register.html')
        if password != password2:
            flash('两次输入的密码不一致', 'error')
            return render_template('register.html')
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        conn = get_db_connection()
        try:
            conn.execute(
                'INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)',
                (username, email, generate_password_hash(password), now),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            flash('该用户名已被注册', 'error')
            return render_template('register.html')
        conn.close()
        flash('注册成功，请登录', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('您已退出登录', 'success')
    return redirect(url_for('login'))


@app.before_request
def require_login_unless_exempt():
    if session.get('user_id'):
        return None
    path = request.path or '/'
    if path in ('/login', '/register', '/logout'):
        return None
    if path.startswith('/static/') or path.startswith('/uploads/'):
        return None
    if path.startswith('/api/open/'):
        return None
    if path.startswith('/__debug/'):
        return None
    if path.startswith('/socket.io'):
        return None
    if request.method == 'OPTIONS':
        return None
    if path.startswith('/api/'):
        return jsonify({'success': False, 'error': '请先登录', 'login_url': '/login'}), 401
    return redirect(url_for('login', next=path))


@app.route('/')
def index():
    """主页面"""
    return render_template('index.html')

@app.route('/mobile')
def mobile():
    """移动端页面"""
    return render_template('mobile.html')

@app.route('/admin')
def admin():
    """后台管理页面"""
    return render_template('admin.html')

@app.route('/api/admin/dashboard', methods=['GET'])
def admin_dashboard():
    """后台管理面板聚合数据：灌溉、风险预警、无人机任务、识别记录等"""
    try:
        conn = get_db_connection()
        # 各模块统计
        irrigation_count = conn.execute("SELECT COUNT(*) AS c FROM irrigation_plans").fetchone()['c']
        risk_count = conn.execute("SELECT COUNT(*) AS c FROM risk_alerts").fetchone()['c']
        task_count = conn.execute("SELECT COUNT(*) AS c FROM tasks").fetchone()['c']
        task_pending = conn.execute("SELECT COUNT(*) AS c FROM tasks WHERE status IN ('待执行','执行中')").fetchone()['c']
        mission_count = conn.execute("SELECT COUNT(*) AS c FROM orchard_missions").fetchone()['c']
        op_count = conn.execute("SELECT COUNT(*) AS c FROM operation_logs").fetchone()['c']
        recog_count = conn.execute("SELECT COUNT(*) AS c FROM operation_logs WHERE log_type = 'recognition'").fetchone()['c']

        # 最近灌溉记录
        irrigation_rows = conn.execute(
            "SELECT plot_name, crop_type, priority, suggested_water_lpm, suggested_duration_min, created_at "
            "FROM irrigation_plans ORDER BY id DESC LIMIT 10"
        ).fetchall()
        recent_irrigation = [dict(r) for r in irrigation_rows]

        # 最近风险预警
        risk_rows = conn.execute(
            "SELECT plot_name, risk_type, risk_level, probability, recommendation, created_at "
            "FROM risk_alerts ORDER BY id DESC LIMIT 10"
        ).fetchall()
        recent_risk_alerts = [dict(r) for r in risk_rows]

        # 最近任务（含无人机调度）
        task_rows = conn.execute(
            "SELECT id, title, task_type, plot_name, status, assignee, created_at "
            "FROM tasks ORDER BY id DESC LIMIT 15"
        ).fetchall()
        recent_tasks = [dict(r) for r in task_rows]

        # 最近果园任务（无人机多机调度）
        mission_rows = conn.execute(
            "SELECT id, mission_name, status, score_total, created_at "
            "FROM orchard_missions ORDER BY id DESC LIMIT 10"
        ).fetchall()
        recent_missions = [dict(r) for r in mission_rows]

        # 最近操作日志（用于时间线）
        op_rows = conn.execute(
            """SELECT log_type, source, model_name, class_name, action_summary, created_at
               FROM operation_logs ORDER BY id DESC LIMIT 20"""
        ).fetchall()
        recent_operations = []
        for r in op_rows:
            d = dict(r)
            d['time'] = d['created_at'][11:16] if d.get('created_at') and len(str(d.get('created_at', ''))) > 10 else '-'
            d['title'] = _op_log_title(d)
            recent_operations.append(d)
        conn.close()

        return jsonify({
            'success': True,
            'data': {
                'metrics': {
                    'irrigation_total': irrigation_count,
                    'risk_alert_total': risk_count,
                    'task_total': task_count,
                    'task_pending': task_pending,
                    'mission_total': mission_count,
                    'operation_total': op_count,
                    'recognition_total': recog_count,
                },
                'recent_irrigation': recent_irrigation,
                'recent_risk_alerts': recent_risk_alerts,
                'recent_tasks': recent_tasks,
                'recent_missions': recent_missions,
                'recent_operations': recent_operations,
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

def _op_log_title(op):
    """将操作日志转为时间线标题"""
    lt = op.get('log_type', '')
    src = op.get('source', '')
    action = op.get('action_summary', '')
    if lt == 'irrigation_plan':
        return f"灌溉建议 - {op.get('class_name', '')} {action[:30]}"
    if lt == 'risk_alert':
        return f"风险预警 - {op.get('class_name', '')} {action[:30]}"
    if lt == 'task':
        return f"任务创建 - {action[:40]}"
    if lt == 'execution':
        return f"执行回传 - {action[:40]}"
    if src == 'orchard_planner':
        return f"无人机调度 - {action[:40]}"
    return action[:50] if action else f"{src} - {lt}"

@app.route('/api/dashboard/data', methods=['GET'])
def dashboard_data():
    """数据大屏聚合：识别、预警、设备、无人机状态（与真实数据同步）"""
    try:
        conn = get_db_connection()
        recog_total = conn.execute("SELECT COUNT(*) AS c FROM operation_logs WHERE log_type = 'recognition'").fetchone()['c']
        risk_high = conn.execute("SELECT COUNT(*) AS c FROM risk_alerts WHERE risk_level = '高'").fetchone()['c']
        risk_medium = conn.execute("SELECT COUNT(*) AS c FROM risk_alerts WHERE risk_level = '中'").fetchone()['c']
        risk_low = conn.execute("SELECT COUNT(*) AS c FROM risk_alerts WHERE risk_level = '低'").fetchone()['c']
        telemetry_total = conn.execute("SELECT COUNT(*) AS c FROM orchard_telemetry").fetchone()['c']

        # 无人机设备：从 drone_fleet 表读取真实数据
        _refresh_drone_charging(conn)
        fleet_rows = conn.execute(
            "SELECT status FROM drone_fleet"
        ).fetchall()
        conn.close()

        device_total = len(fleet_rows)
        # 在线=空闲+执行中，离线=充电中（不可用）
        online_count = sum(1 for r in fleet_rows if (r['status'] or '') in ('idle', 'executing'))
        offline_count = sum(1 for r in fleet_rows if (r['status'] or '') == 'charging')

        with orchard_lock:
            drones = orchard_state.get('drones', [])
            mission_status = orchard_state.get('status', 'idle')
            mission_name = orchard_state.get('mission_name', '')

        return jsonify({
            'success': True,
            'data': {
                'recognition_total': recog_total,
                'risk_high': risk_high,
                'risk_medium': risk_medium,
                'risk_low': risk_low,
                'device_total': device_total,
                'online_devices': online_count,
                'offline_devices': offline_count,
                'telemetry_total': telemetry_total,
                'mission_status': mission_status,
                'mission_name': mission_name,
                'drones': drones,
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/dashboard/recent_logs', methods=['GET'])
def dashboard_recent_logs():
    """数据大屏初始日志：最近操作记录（含无人机）"""
    try:
        limit = request.args.get('limit', type=int, default=20)
        conn = get_db_connection()
        rows = conn.execute(
            """SELECT log_type, source, action_summary, created_at
               FROM operation_logs
               ORDER BY id DESC LIMIT ?""",
            (limit,)
        ).fetchall()
        conn.close()
        logs = []
        for r in rows:
            msg = r['action_summary'] or f"{r['source']} - {r['log_type']}"
            logs.append({'message': msg, 'time': r['created_at'][11:19] if r['created_at'] and len(str(r['created_at'])) > 10 else ''})
        return jsonify({'success': True, 'data': logs})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/dashboard')
def dashboard():
    """数据可视化大屏"""
    return render_template('dashboard.html')


@app.route('/果园地图')
@app.route('/orchard_map')
def orchard_map():
    """俯瞰果园多机调度地图"""
    return render_template('果园地图.html', amap_js_key=AMAP_JS_KEY)

@app.route('/任务规划')
def mission_planning():
    """无人机任务规划与数据采集页面"""
    return render_template('任务规划.html')

@app.route('/无人机控制')
def uav_control():
    """无人机实时控制台页面"""
    return render_template('无人机控制.html')

@app.route('/视频分析')
@app.route('/video_analyze')
def video_analyze():
    """果园视频分析（苹果检测、成熟度、病虫害）"""
    return render_template('视频分析.html')

@app.route('/识别')
def recognition():
    """作物识别页面"""
    return render_template('识别页面.html')

@app.route('/成熟度')
def maturity():
    """成熟度评估页面"""
    return render_template('成熟度评估.html')

@app.route('/病虫害')
def disease():
    """病虫害诊断页面"""
    return render_template('病虫害诊断.html')

@app.route('/用药')
def prescription():
    """用药建议页面"""
    return render_template('用药建议.html')

@app.route('/气象')
def weather():
    """气象预警页面"""
    return render_template('气象预警.html')

@app.route('/历史')
def history():
    """历史记录页面"""
    return render_template('历史记录.html')

@app.route('/灌溉')
@app.route('/irrigation')
def irrigation():
    """智能灌溉页面（兼容中文/英文路径）"""
    return render_template('气象预警.html')

@app.route('/__debug/app')
def __debug_app():
    """调试：确认当前运行的 app.py 路径与工作目录"""
    return jsonify({
        'app_file': os.path.abspath(__file__),
        'cwd': os.getcwd(),
        'host': DEFAULT_HOST,
        'port': DEFAULT_PORT
    })

@app.route('/__debug/routes')
def __debug_routes():
    """调试：列出所有已注册路由，便于排查 404"""
    routes = []
    for r in app.url_map.iter_rules():
        routes.append({
            'rule': str(r),
            'endpoint': r.endpoint,
            'methods': sorted([m for m in r.methods if m in {'GET', 'POST', 'PUT', 'DELETE', 'PATCH'}])
        })
    routes.sort(key=lambda x: x['rule'])
    return jsonify({'count': len(routes), 'routes': routes})


@app.route('/api/orchard/config', methods=['GET'])
def orchard_config_api():
    """获取果园地图配置（分区、障碍物、无人机）"""
    latest = refresh_orchard_config()
    write_audit_log('view_orchard_config')
    return jsonify({'success': True, 'data': latest})


@app.route('/api/orchard/plan', methods=['POST'])
def orchard_plan_api():
    """生成多机分区与避障规划，并启动仿真执行"""
    if ROLE_LEVELS.get(get_request_role(), 0) < ROLE_LEVELS['operator']:
        return jsonify({'success': False, 'error': '权限不足，至少需要 operator 角色'}), 403

    data = request.get_json() or {}
    mission_name = (data.get('mission_name') or '').strip() or f"果园巡检-{datetime.now().strftime('%H%M%S')}"
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    with orchard_lock:
        orchard_state['status'] = 'planning'
        orchard_state['updated_at'] = now

    try:
        current_config = refresh_orchard_config()
        plan_result = build_orchard_plan(current_config)
    except Exception as e:
        with orchard_lock:
            orchard_state['status'] = 'idle'
            orchard_state['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'规划失败: {str(e)}'}), 500

    conn = get_db_connection()
    cursor = conn.execute(
        """
        INSERT INTO orchard_missions
        (mission_name, strategy_json, status, score_total, score_efficiency, score_energy, score_balance, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            mission_name,
            json.dumps({
                'assignments': plan_result['assignments'],
                'scores': plan_result['scores']
            }, ensure_ascii=False),
            'running',
            plan_result['scores']['total'],
            plan_result['scores']['efficiency'],
            plan_result['scores']['energy'],
            plan_result['scores']['balance'],
            now,
            now
        )
    )
    mission_id = cursor.lastrowid
    conn.execute(
        """
        INSERT INTO operation_logs
        (log_type, source, related_task_id, model_name, class_name, confidence, action_summary, payload_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            'task', 'orchard_planner', mission_id, '多机调度策略', '果园巡检', None,
            f'已生成调度计划: {mission_name}',
            json.dumps(plan_result['assignments'], ensure_ascii=False),
            now
        )
    )
    conn.commit()
    conn.close()

    start_orchard_simulation(mission_id, mission_name, plan_result)
    write_audit_log('create_orchard_plan')
    emit_orchard_state('orchard_state')
    return jsonify({
        'success': True,
        'data': {
            'mission_id': mission_id,
            'mission_name': mission_name,
            'assignments': plan_result['assignments'],
            'scores': plan_result['scores'],
            'planned_paths': {k: serialize_path(v) for k, v in plan_result['timed_paths'].items()},
            'planned_paths_lnglat': plan_result.get('timed_paths_lnglat', {})
        }
    })


@app.route('/api/orchard/reset', methods=['POST'])
def orchard_reset_api():
    """重置仿真：无人机回到起点并从头执行任务"""
    if ROLE_LEVELS.get(get_request_role(), 0) < ROLE_LEVELS['operator']:
        return jsonify({'success': False, 'error': '权限不足，至少需要 operator 角色'}), 403

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with orchard_lock:
        mission_id = orchard_state.get('mission_id')
        mission_name = orchard_state.get('mission_name') or f"果园巡检-{datetime.now().strftime('%H%M%S')}"

    current_config = refresh_orchard_config()
    plan_result = build_orchard_plan(current_config)

    conn = get_db_connection()
    if mission_id is None:
        cursor = conn.execute(
            """
            INSERT INTO orchard_missions
            (mission_name, strategy_json, status, score_total, score_efficiency, score_energy, score_balance, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mission_name,
                json.dumps({
                    'assignments': plan_result['assignments'],
                    'scores': plan_result['scores']
                }, ensure_ascii=False),
                'running',
                plan_result['scores']['total'],
                plan_result['scores']['efficiency'],
                plan_result['scores']['energy'],
                plan_result['scores']['balance'],
                now,
                now
            )
        )
        mission_id = cursor.lastrowid
    else:
        conn.execute(
            """
            UPDATE orchard_missions
            SET status = ?, score_total = ?, score_efficiency = ?, score_energy = ?, score_balance = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                'running',
                plan_result['scores']['total'],
                plan_result['scores']['efficiency'],
                plan_result['scores']['energy'],
                plan_result['scores']['balance'],
                now,
                mission_id
            )
        )
    conn.execute(
        """
        INSERT INTO operation_logs
        (log_type, source, related_task_id, model_name, class_name, confidence, action_summary, payload_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            'execution', 'orchard_planner', mission_id, '多机调度策略', '果园巡检', None,
            f'已重置任务并重新开始: {mission_name}',
            json.dumps({'reset': True, 'assignments': plan_result['assignments']}, ensure_ascii=False),
            now
        )
    )
    conn.commit()
    conn.close()

    start_orchard_simulation(mission_id, mission_name, plan_result)
    write_audit_log('reset_orchard_plan')
    emit_orchard_state('orchard_state')
    return jsonify({'success': True, 'message': '已重置并重新开始', 'data': orchard_snapshot()})


@app.route('/api/orchard/rtb', methods=['POST'])
def orchard_rtb_api():
    """一键返航到机库：中断当前任务并让所有无人机返回机库"""
    if ROLE_LEVELS.get(get_request_role(), 0) < ROLE_LEVELS['operator']:
        return jsonify({'success': False, 'error': '权限不足，至少需要 operator 角色'}), 403

    current_config = refresh_orchard_config()
    hangar_center = current_config.get('hangar_center')
    if hangar_center is None:
        return jsonify({'success': False, 'error': '未配置机库区域（hangar）'}), 400

    with orchard_lock:
        orchard_state['force_rtb'] = True
        orchard_state['status'] = 'returning'
        orchard_state['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for d in orchard_state.get('drones', []):
            d.pop('return_path', None)
            d.pop('return_idx', None)
            d['status'] = '返航中'

    # 如果当前没有仿真线程在跑，启动一个轻量返航线程驱动返航
    if orchard_sim_thread is None or (not orchard_sim_thread.is_alive()):
        start_orchard_rtb_simulation()

    write_audit_log('orchard_return_to_hangar')
    emit_orchard_state('orchard_state')
    return jsonify({'success': True, 'message': '已下达返航指令', 'data': orchard_snapshot()})


@app.route('/api/orchard/state', methods=['GET'])
def orchard_state_api():
    """获取当前果园多机调度状态"""
    write_audit_log('view_orchard_state')
    return jsonify({'success': True, 'data': orchard_snapshot()})


# 缓存：task_id -> trajectory_lnglat，避免每次轮询都重新做 A*+扫掠计算
_dispatched_traj_cache = {}

def _build_dispatched_trajectory(task_id, plot_name, config):
    """为单个任务计算完整飞行轨迹（A* + 割草机扫掠），结果缓存复用。"""
    if task_id in _dispatched_traj_cache:
        return _dispatched_traj_cache[task_id]

    geo_ref = config.get('geo_ref', {})
    zones = config.get('zones', [])
    obstacles = config.get('obstacles', [])
    grid = config.get('grid', {'width': 80, 'height': 60})
    boundary_polygon = config.get('boundary_polygon')
    hangar_center = config.get('hangar_center')
    if not zones:
        zones = [{'id': 'Z1', 'rect': [5, 5, 30, 30]}]
    if hangar_center is None:
        hangar_center = (40, 30)

    # 匹配分区
    zone = None
    for z in zones:
        if z.get('name') == plot_name or z.get('id') == plot_name:
            zone = z
            break
    if zone is None:
        idx = abs(hash(plot_name or '')) % len(zones)
        zone = zones[idx]

    rect = zone.get('rect', [5, 5, 30, 30])
    hx = int(hangar_center[0])
    hy = int(hangar_center[1])
    hangar_start = (hx, hy)

    # 分区入口
    entry = None
    for dy in range(rect[1], rect[3] + 1):
        for dx in range(rect[0], rect[2] + 1):
            if not is_cell_blocked(dx, dy, obstacles, boundary_polygon):
                entry = (dx, dy)
                break
        if entry:
            break
    if entry is None:
        entry = ((rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2)

    bs = build_blocked_set(grid, obstacles, boundary_polygon)
    go_path = astar_path(hangar_start, entry, grid, obstacles, boundary_polygon, blocked_set=bs)
    sweep_path = build_zone_lawnmower_path(zone, grid, obstacles, boundary_polygon, x_step=2, row_step=3, blocked_set=bs)
    sweep_end = sweep_path[-1] if sweep_path else entry
    return_path = astar_path(sweep_end, hangar_start, grid, obstacles, boundary_polygon, blocked_set=bs)

    full_grid_path = go_path + (sweep_path[1:] if len(go_path) > 1 and sweep_path else sweep_path) + (return_path[1:] if return_path else [])
    traj = [grid_to_lnglat(p[0] + 0.5, p[1] + 0.5, geo_ref) for p in full_grid_path]

    if len(traj) < 2:
        hll = grid_to_lnglat(hx + 0.5, hy + 0.5, geo_ref)
        cx = (rect[0] + rect[2]) / 2.0
        cy = (rect[1] + rect[3]) / 2.0
        traj = [hll, grid_to_lnglat(cx, cy, geo_ref), hll]

    _dispatched_traj_cache[task_id] = traj
    return traj


@app.route('/api/orchard/dispatched_trajectories', methods=['GET'])
def dispatched_trajectories_api():
    """获取已分配任务的无人机飞行轨迹（缓存 A*+扫掠结果，轮询时直接返回）"""
    try:
        conn = get_db_connection()
        rows = conn.execute(
            "SELECT id, title, plot_name, assignee FROM tasks WHERE status = '执行中' AND assignee IS NOT NULL AND assignee LIKE 'UAV-%'"
        ).fetchall()
        conn.close()

        if not rows:
            return jsonify({'success': True, 'data': []})

        config = refresh_orchard_config()
        result = []
        for r in rows:
            traj = _build_dispatched_trajectory(r['id'], r['plot_name'] or '', config)
            result.append({
                'task_id': r['id'],
                'drone_id': r['assignee'],
                'title': r['title'],
                'plot_name': r['plot_name'] or '',
                'trajectory_lnglat': traj
            })
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e), 'data': []}), 500


@app.route('/api/orchard/telemetry', methods=['POST'])
def orchard_telemetry_api():
    """外部回传无人机状态（可由真实设备或模拟器上报）"""
    if ROLE_LEVELS.get(get_request_role(), 0) < ROLE_LEVELS['operator']:
        return jsonify({'success': False, 'error': '权限不足，至少需要 operator 角色'}), 403

    data = request.get_json() or {}
    drone_id = str(data.get('drone_id', '')).strip()
    if not drone_id:
        return jsonify({'success': False, 'error': 'drone_id 不能为空'}), 400
    pos = data.get('position') or {}
    x = float(pos.get('x', 0.0))
    y = float(pos.get('y', 0.0))
    battery = float(data.get('battery', 100.0))
    speed = float(data.get('speed', 0.0))
    status = str(data.get('status', '执行中'))
    event_type = str(data.get('event_type', 'telemetry'))
    zone_id = str(data.get('zone_id', ''))
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    with orchard_lock:
        for drone in orchard_state['drones']:
            if drone['drone_id'] == drone_id:
                drone['position'] = [x, y]
                drone['position_lnglat'] = grid_to_lnglat(x + 0.5, y + 0.5, orchard_config['geo_ref'])
                drone['battery'] = battery
                drone['speed'] = speed
                drone['status'] = status
                break
        orchard_state['updated_at'] = now

    mission_id = orchard_state.get('mission_id')
    conn = get_db_connection()
    conn.execute(
        """
        INSERT INTO orchard_telemetry
        (mission_id, drone_id, zone_id, pos_x, pos_y, battery, speed, drone_status, event_type, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (mission_id, drone_id, zone_id, x, y, battery, speed, status, event_type, now)
    )
    conn.commit()
    conn.close()

    write_audit_log('upload_orchard_telemetry')
    emit_orchard_state('orchard_state')
    return jsonify({'success': True, 'message': '状态回传成功'})

@app.route('/api/risk_alerts', methods=['GET', 'POST'])
def risk_alerts():
    """病虫害风险预警（MVP）"""
    if request.method == 'POST':
        data = request.get_json() or {}
        plot_name = data.get('plot_name', 'A区')
        weather_temp = float(data.get('temperature', 28.0))
        humidity = float(data.get('humidity', 70.0))
        rainfall = float(data.get('rainfall', 3.0))

        alert = build_risk_alerts(plot_name, weather_temp, humidity, rainfall)
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        conn = get_db_connection()
        conn.execute(
            """
            INSERT INTO risk_alerts
            (plot_name, risk_type, risk_level, probability, operation_window, recommendation, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                alert['plot_name'], alert['risk_type'], alert['risk_level'],
                alert['probability'], alert['operation_window'], alert['recommendation'], now
            )
        )
        conn.execute(
            """
            INSERT INTO operation_logs
            (log_type, source, related_task_id, model_name, class_name, confidence, action_summary, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                'risk_alert', 'rule_engine', None, '风险规则引擎', alert['risk_type'],
                round(alert['probability'] * 100, 2), alert['recommendation'],
                json.dumps(alert, ensure_ascii=False), now
            )
        )
        conn.commit()
        conn.close()
        write_audit_log('create_risk_alert')
        return jsonify({'success': True, 'data': alert})

    limit = request.args.get('limit', type=int, default=20)
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT id, plot_name, risk_type, risk_level, probability, operation_window, recommendation, created_at
        FROM risk_alerts
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,)
    ).fetchall()
    conn.close()
    data = [
        {
            'id': row['id'],
            'plot_name': row['plot_name'],
            'risk_type': row['risk_type'],
            'risk_level': row['risk_level'],
            'probability': row['probability'],
            'operation_window': row['operation_window'],
            'recommendation': row['recommendation'],
            'timestamp': row['created_at']
        } for row in rows
    ]
    return jsonify({'success': True, 'data': data})

@app.route('/api/irrigation_plan', methods=['GET', 'POST'])
def irrigation_plan():
    """智能灌溉建议（MVP）"""
    if request.method == 'POST':
        data = request.get_json() or {}
        plan = build_irrigation_plan(
            data.get('plot_name', 'A区'),
            data.get('crop_type', '苹果'),
            data.get('growth_stage', '结果期'),
            float(data.get('soil_moisture', 52.0)),
            float(data.get('temperature', 28.0)),
            float(data.get('rainfall', 2.0))
        )
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        conn = get_db_connection()
        conn.execute(
            """
            INSERT INTO irrigation_plans
            (plot_name, crop_type, growth_stage, soil_moisture, weather_temp, weather_rainfall,
             suggested_water_lpm, suggested_duration_min, priority, recommendation, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plan['plot_name'], plan['crop_type'], plan['growth_stage'],
                plan['soil_moisture'], plan['weather_temp'], plan['weather_rainfall'],
                plan['suggested_water_lpm'], plan['suggested_duration_min'],
                plan['priority'], plan['recommendation'], now
            )
        )
        conn.execute(
            """
            INSERT INTO operation_logs
            (log_type, source, related_task_id, model_name, class_name, confidence, action_summary, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                'irrigation_plan', 'rule_engine', None, '灌溉规则引擎', plan['crop_type'],
                plan['soil_moisture'], plan['recommendation'],
                json.dumps(plan, ensure_ascii=False), now
            )
        )
        conn.commit()
        conn.close()
        write_audit_log('create_irrigation_plan')
        return jsonify({'success': True, 'data': plan})

    limit = request.args.get('limit', type=int, default=20)
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT id, plot_name, crop_type, growth_stage, soil_moisture, weather_temp, weather_rainfall,
               suggested_water_lpm, suggested_duration_min, priority, recommendation, created_at
        FROM irrigation_plans
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,)
    ).fetchall()
    conn.close()
    data = [
        {
            'id': row['id'],
            'plot_name': row['plot_name'],
            'crop_type': row['crop_type'],
            'growth_stage': row['growth_stage'],
            'soil_moisture': row['soil_moisture'],
            'temperature': row['weather_temp'],
            'rainfall': row['weather_rainfall'],
            'suggested_water_lpm': row['suggested_water_lpm'],
            'suggested_duration_min': row['suggested_duration_min'],
            'priority': row['priority'],
            'recommendation': row['recommendation'],
            'timestamp': row['created_at']
        } for row in rows
    ]
    return jsonify({'success': True, 'data': data})

@app.route('/api/weather_by_ip', methods=['GET'])
def weather_by_ip():
    """基于公网 IP 的天气兜底（浏览器定位失败时使用）"""
    try:
        # IP 粗定位
        ip_resp = requests.get('http://ip-api.com/json/?lang=zh-CN', timeout=6)
        ip_resp.raise_for_status()
        ip_data = ip_resp.json() or {}
        if ip_data.get('status') != 'success':
            return jsonify({'success': False, 'error': 'IP 定位失败'}), 502

        lat = ip_data.get('lat')
        lon = ip_data.get('lon')
        city = ip_data.get('city') or ip_data.get('regionName') or ip_data.get('country') or '当前位置'
        if lat is None or lon is None:
            return jsonify({'success': False, 'error': 'IP 定位缺少坐标'}), 502

        # 天气（当前气温 + 今日降水量）
        weather_url = (
            'https://api.open-meteo.com/v1/forecast'
            f'?latitude={lat}&longitude={lon}'
            '&current=temperature_2m&daily=precipitation_sum&past_days=0&timezone=auto'
        )
        weather_resp = requests.get(weather_url, timeout=8)
        weather_resp.raise_for_status()
        weather_data = weather_resp.json() or {}

        temp = weather_data.get('current', {}).get('temperature_2m')
        rain_list = weather_data.get('daily', {}).get('precipitation_sum') or [0]
        rain = rain_list[0] if rain_list else 0  # 今日降水量
        if temp is None:
            return jsonify({'success': False, 'error': '天气数据不完整'}), 502

        return jsonify({
            'success': True,
            'data': {
                'source': 'ip_fallback',
                'city': city,
                'latitude': lat,
                'longitude': lon,
                'temperature': round(float(temp), 1),
                'rainfall': round(float(rain or 0), 1)
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': f'天气兜底失败: {e}'}), 500

@app.route('/api/recognition_history', methods=['GET'])
def get_recognition_history():
    """获取决策与执行历史记录"""
    try:
        limit = request.args.get('limit', type=int, default=50)
        offset = request.args.get('offset', type=int, default=0)
        log_type = request.args.get('log_type', type=str, default='')

        conn = get_db_connection()
        params = []
        where_sql = ""
        if log_type:
            where_sql = "WHERE log_type = ?"
            params.append(log_type)

        total = conn.execute(
            f"SELECT COUNT(*) AS count FROM operation_logs {where_sql}",
            params
        ).fetchone()['count']
        rows = conn.execute(
            f"""
            SELECT id, log_type, source, related_task_id, model_name, class_name,
                   confidence, action_summary, payload_json, created_at
            FROM operation_logs
            {where_sql}
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            params + [limit, offset]
        ).fetchall()
        conn.close()

        history_data = []
        for row in rows:
            payload = {}
            if row['payload_json']:
                try:
                    payload = json.loads(row['payload_json'])
                except Exception:
                    payload = {}
            history_data.append({
                'id': row['id'],
                'log_type': row['log_type'],
                'source': row['source'],
                'related_task_id': row['related_task_id'],
                'model_name': row['model_name'],
                'class_name': row['class_name'],
                'confidence': row['confidence'],
                'action_summary': row['action_summary'],
                'payload': payload,
                'timestamp': row['created_at']
            })
        
        return jsonify({
            'success': True,
            'data': history_data,
            'total': total,
            'limit': limit,
            'offset': offset
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/models', methods=['GET'])
def get_models():
    """获取可用模型列表"""
    models_info = []
    for model_type, config in MODEL_CONFIGS.items():
        model_path = config['model_path']
        exists = os.path.exists(model_path)
        models_info.append({
            'type': model_type,
            'name': config['name'],
            'description': config['description'],
            'classes': config['classes'],
            'available': exists
        })
    return jsonify({'models': models_info})


# ---------- 视频分析 API ----------
@app.route('/api/video/orchard_analyze', methods=['POST'])
def api_video_orchard_analyze():
    """上传果园视频，后台处理（苹果检测+成熟度+病虫害）"""
    if process_orchard_video is None:
        return jsonify({'success': False, 'error': '视频处理模块未安装'}), 500
    if 'video' not in request.files:
        return jsonify({'success': False, 'error': '请选择视频文件'}), 400
    f = request.files['video']
    if f.filename == '':
        return jsonify({'success': False, 'error': '未选择文件'}), 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ('.mp4', '.avi', '.mov', '.mkv', '.webm'):
        return jsonify({'success': False, 'error': '仅支持 mp4/avi/mov/mkv/webm'}), 400
    task_id = datetime.now().strftime('%Y%m%d%H%M%S') + '_' + str(random.randint(1000, 9999))
    input_filename = f'input_{task_id}{ext}'
    input_path = os.path.join(VIDEO_UPLOAD_DIR, input_filename)
    output_path = os.path.join(VIDEO_UPLOAD_DIR, f'output_{task_id}.mp4')
    f.save(input_path)
    input_url = f'/static/uploads/video/{input_filename}'
    play_only = str(request.form.get('play_only', '')).lower() in ('1', 'true', 'yes')
    skip_annotate = str(request.form.get('skip_annotate', '')).lower() in ('1', 'true', 'yes')

    if play_only:
        # 仅播放：不分析。为保证浏览器可播放，必要时转码为 H.264 + faststart
        def _ffmpeg_exe():
            exe = shutil.which('ffmpeg')
            if exe:
                return exe
            try:
                import imageio_ffmpeg  # type: ignore
                return imageio_ffmpeg.get_ffmpeg_exe()
            except Exception:
                return None

        def _needs_h264_transcode(path: str) -> bool:
            try:
                size = os.path.getsize(path)
                head_n = 1024 * 1024
                tail_n = 1024 * 1024
                with open(path, 'rb') as f:
                    head = f.read(head_n)
                    if size > tail_n:
                        f.seek(max(0, size - tail_n))
                    tail = f.read(tail_n)
                blob = head + tail
                # avc1/avcC 表示 H.264；否则（如 mp4v/hvc1 等）尽量转为 H.264
                return (b'avc1' not in blob) and (b'avcC' not in blob)
            except Exception:
                return True

        def _transcode_h264(src: str, dst: str) -> None:
            exe = _ffmpeg_exe()
            if not exe:
                raise RuntimeError('未找到 ffmpeg。请先安装依赖 imageio-ffmpeg 或将 ffmpeg 加入 PATH。')
            cmd = [
                exe, '-y',
                '-i', src,
                '-map', '0:v:0',
                '-map', '0:a?',
                '-c:v', 'libx264',
                '-pix_fmt', 'yuv420p',
                '-preset', 'veryfast',
                '-crf', '23',
                '-c:a', 'aac',
                '-b:a', '128k',
                '-movflags', '+faststart',
                dst,
            ]
            p = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            if p.returncode != 0:
                tail = (p.stderr or '')[-1200:]
                raise RuntimeError('视频转码失败：' + tail)

        serve_filename = input_filename
        serve_path = input_path
        if _needs_h264_transcode(input_path):
            play_filename = f'play_{task_id}.mp4'
            play_path = os.path.join(VIDEO_UPLOAD_DIR, play_filename)
            _transcode_h264(input_path, play_path)
            serve_filename = play_filename
            serve_path = play_path

        with video_analyze_lock:
            video_analyze_tasks[task_id] = {
                'status': 'done',
                'frame': 0,
                'total': 0,
                'output_path': serve_path,
                'error': None,
                'fps': 25,
                'width': 0,
                'height': 0,
                'annotations': {},
            }
        stream_url = f'/api/video/stream/{serve_filename}'
        return jsonify({
            'success': True, 'task_id': task_id, 'input_url': input_url,
            'output_url': stream_url, 'play_only': True,
            'message': '已上传，可直接播放'
        })

    ANNOTATIONS_WINDOW = 120  # 保留最近约 5 秒标注，保证前端有密集数据做流畅跟随
    DISEASE_CN = {'Blotch_Apple': '褐斑病', 'Normal_Apple': '正常', 'Rot_Apple': '腐烂', 'Scab_Apple': '黑星病'}
    with video_analyze_lock:
        video_analyze_tasks[task_id] = {
            'status': 'processing',
            'frame': 0,
            'total': 0,
            'output_path': None,
            'error': None,
            'fps': 25,
            'width': 0,
            'height': 0,
            'annotations': {},
            'stats': {'total_apples': 0, 'maturity': {}, 'disease': {}},
        }

    def run():
        try:
            def cb(frame_idx, total, fps, w, h, ann):
                with video_analyze_lock:
                    if task_id in video_analyze_tasks:
                        t = video_analyze_tasks[task_id]
                        t.update(status='processing', frame=frame_idx, total=total, fps=fps, width=w, height=h)
                        t.setdefault('annotations', {})[frame_idx] = ann
                        anns = t['annotations']
                        if len(anns) > ANNOTATIONS_WINDOW:
                            for k in sorted(anns.keys())[:-ANNOTATIONS_WINDOW]:
                                del anns[k]
                        # 累积统计：苹果数量、成熟度、病害
                        st = t.setdefault('stats', {'total_apples': 0, 'maturity': {}, 'disease': {}})
                        if ann.get('bboxes'):
                            st['total_apples'] += len(ann['bboxes'])
                            for m in ann.get('maturity', []):
                                k = str(m[0]) if m else '未知'
                                st['maturity'][k] = st['maturity'].get(k, 0) + 1
                            for d in ann.get('disease', []):
                                k = str(d[0]) if d else '未知'
                                st['disease'][k] = st['disease'].get(k, 0) + 1
            process_orchard_video(input_path, output_path, fps_sample=2, progress_callback=cb, device=None, skip_annotate=skip_annotate)
            with video_analyze_lock:
                if task_id in video_analyze_tasks:
                    video_analyze_tasks[task_id].update(status='done', output_path=output_path)
        except Exception as e:
            with video_analyze_lock:
                if task_id in video_analyze_tasks:
                    video_analyze_tasks[task_id].update(status='error', error=str(e))
        finally:
            try:
                if os.path.exists(input_path):
                    os.remove(input_path)
            except Exception:
                pass

    threading.Thread(target=run, daemon=True).start()
    return jsonify({'success': True, 'task_id': task_id, 'input_url': input_url, 'message': '任务已启动'})


@app.route('/api/video/stream/<filename>')
def api_video_stream(filename):
    """视频流接口，确保正确的 Content-Type 和 Range 支持"""
    if '..' in filename or '/' in filename:
        return '', 404
    path = os.path.join(VIDEO_UPLOAD_DIR, filename)
    if not os.path.isfile(path):
        return '', 404
    ext = os.path.splitext(filename)[1].lower()
    mime = {'.mp4': 'video/mp4', '.webm': 'video/webm', '.mov': 'video/quicktime',
            '.avi': 'video/x-msvideo', '.mkv': 'video/x-matroska'}.get(ext, 'video/mp4')
    return send_from_directory(VIDEO_UPLOAD_DIR, filename, mimetype=mime,
                               as_attachment=False, conditional=True)


@app.route('/api/video/status/<task_id>')
def api_video_status(task_id):
    """查询视频分析任务进度"""
    DISEASE_CN = {'Blotch_Apple': '褐斑病', 'Normal_Apple': '正常', 'Rot_Apple': '腐烂', 'Scab_Apple': '黑星病'}
    with video_analyze_lock:
        t = video_analyze_tasks.get(task_id)
    if not t:
        return jsonify({'status': 'unknown', 'error': '任务不存在'}), 404
    out = {'status': t['status'], 'frame': t.get('frame', 0), 'total': t.get('total', 0), 'fps': t.get('fps', 25), 'width': t.get('width', 0), 'height': t.get('height', 0)}
    if t.get('annotations'):
        out['annotations'] = t['annotations']
    if t.get('output_path') and os.path.exists(t['output_path']):
        out['output_url'] = f'/api/video/stream/{os.path.basename(t["output_path"])}'
    if t.get('error'):
        out['error'] = t['error']
    # 识别结果汇总（病害英文转中文）
    st = t.get('stats') or {}
    if st:
        disease_cn = {DISEASE_CN.get(k, k): v for k, v in st.get('disease', {}).items()}
        out['stats'] = {
            'total_apples': st.get('total_apples', 0),
            'maturity': st.get('maturity', {}),
            'disease': disease_cn,
        }
    return jsonify(out)


@app.route('/upload', methods=['POST'])
def upload_file():
    """处理文件上传和预测"""
    try:
        # 检查是否有文件
        if 'file' not in request.files:
            return jsonify({'error': '没有上传文件'}), 400
        
        file = request.files['file']
        
        # 检查文件名
        if file.filename == '':
            return jsonify({'error': '文件名为空'}), 400
        
        # 检查文件类型
        if not allowed_file(file.filename):
            return jsonify({'error': '不支持的文件类型，请上传图片（jpg, png, jpeg等）'}), 400
        
        # 获取模型类型
        model_type = request.form.get('model_type', 'demo1')
        if model_type not in MODEL_CONFIGS:
            return jsonify({'error': f'未知的模型类型: {model_type}'}), 400
        
        # 检查模型文件是否存在
        config = MODEL_CONFIGS[model_type]
        if not os.path.exists(config['model_path']):
            return jsonify({'error': f'{config["name"]}模型文件不存在'}), 404
        
        # 保存文件（中文名等需保留合法扩展名，避免 annotated 保存时 PIL 无法识别格式）
        filename = safe_upload_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # 预测
        class_name, confidence, prob_dict, annotated_image, config = predict_and_annotate(
            filepath, 
            model_type=model_type,
            device=device,
            box_type='full'
        )
        
        # 保存标注后的图片
        annotated_filename = 'annotated_' + filename
        annotated_filepath = os.path.join(app.config['UPLOAD_FOLDER'], annotated_filename)
        _ext = os.path.splitext(filename)[1]
        annotated_image.save(annotated_filepath, format=pil_format_for_extension(_ext))
        
        # 返回结果
        action_plan = build_action_plan(class_name, round(confidence * 100, 2))
        result = {
            'success': True,
            'model_type': model_type,
            'model_name': config['name'],
            'class_name': class_name,
            'confidence': round(confidence * 100, 2),
            'description': config['description_map'].get(class_name, ''),
            'probabilities': {k: round(v * 100, 2) for k, v in prob_dict.items()},
            'original_image': f'/uploads/{filename}',
            'annotated_image': f'/uploads/{annotated_filename}',
            'action_plan': action_plan
        }
        
        # 保存历史记录
        try:
            from datetime import datetime
            history_file = os.path.join(BASE_DIR, 'recognition_history.json')
            history_data = []
            
            # 读取现有历史记录
            if os.path.exists(history_file):
                try:
                    with open(history_file, 'r', encoding='utf-8') as f:
                        history_data = json.load(f)
                except:
                    history_data = []
            
            # 添加新记录
            history_entry = {
                'id': len(history_data) + 1,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'model_type': model_type,
                'model_name': config['name'],
                'class_name': class_name,
                'confidence': round(confidence * 100, 2),
                'description': config['description_map'].get(class_name, ''),
                'original_image': f'/uploads/{filename}',
                'annotated_image': f'/uploads/{annotated_filename}',
                'probabilities': {k: round(v * 100, 2) for k, v in prob_dict.items()}
            }
            
            history_data.insert(0, history_entry)  # 新记录插入到最前面
            
            # 只保留最近1000条记录
            if len(history_data) > 1000:
                history_data = history_data[:1000]
            
            # 保存历史记录
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(history_data, f, ensure_ascii=False, indent=2)

            # 写入决策执行日志（数据库）
            conn = get_db_connection()
            conn.execute(
                """
                INSERT INTO operation_logs
                (log_type, source, related_task_id, model_name, class_name, confidence,
                 action_summary, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    'recognition',
                    'upload',
                    None,
                    config['name'],
                    class_name,
                    round(confidence * 100, 2),
                    action_plan['next_steps'][0],
                    json.dumps({
                        'model_type': model_type,
                        'action_plan': action_plan,
                        'original_image': f'/uploads/{filename}',
                        'annotated_image': f'/uploads/{annotated_filename}'
                    }, ensure_ascii=False),
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                )
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f'[历史记录] 保存失败: {e}', flush=True)
        
        return jsonify(result)
        
    except Exception as e:
        import traceback
        error_msg = str(e)
        traceback.print_exc()
        return jsonify({'error': f'处理失败: {error_msg}'}), 500

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """提供上传文件的访问"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/api/get_ai_suggestion', methods=['POST'])
def get_ai_suggestion():
    """获取AI建议（用于识别结果页面）"""
    try:
        data = request.get_json()
        if not data or 'image_path' not in data:
            return jsonify({'success': False, 'error': '缺少图片路径'}), 400
        
        image_path = data['image_path']
        class_name = data.get('class_name', '')
        confidence = data.get('confidence', 0)
        
        # 构建提示词（针对水果识别，优化为更简洁的版本以加快响应）
        prompt = f"""分析图片中的水果（识别：{class_name}，置信度：{confidence}%），提供简洁建议：
1. 识别结果确认 - 判断是否准确
2. 成熟度评估 - 简述当前状态
3. 品质建议 - 是否可食用或采收
4. 种植建议 - 后续管理要点
请直接输出建议内容，不要包含 Emoji 表情。"""
        
        # 调用云端视觉 API
        suggestion = call_doubao_api_with_prompt(image_path, prompt)
        
        return jsonify({
            'success': True,
            'suggestion': suggestion
        })
        
    except Exception as e:
        print(f'[AI建议] 获取失败: {e}', flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

def compress_image_for_api(image_path, max_size=1024, quality=85):
    """压缩图片以加快API调用速度"""
    try:
        from PIL import Image
        import io
        
        # 打开图片
        img = Image.open(image_path)
        original_size = img.size
        
        # 如果图片太大，进行压缩
        if max(original_size) > max_size:
            # 计算新尺寸（保持宽高比）
            ratio = max_size / max(original_size)
            new_size = (int(original_size[0] * ratio), int(original_size[1] * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            print(f"[AI建议] 图片已压缩: {original_size} -> {new_size}", flush=True)
        
        # 转换为JPEG格式（更小）
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # 保存到内存
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=quality, optimize=True)
        output.seek(0)
        
        return output.read()
    except Exception as e:
        print(f"[AI建议] 图片压缩失败，使用原图: {e}", flush=True)
        # 如果压缩失败，返回原图
        with open(image_path, 'rb') as f:
            return f.read()

def call_doubao_api_with_prompt(image_path, prompt):
    """使用自定义提示词调用云端视觉 API（优化版：更快速度）"""
    try:
        from doubao_config import DOUBAO_API_KEY, DOUBAO_API_ENDPOINT, DOUBAO_MODEL, check_config
    except ImportError:
        DOUBAO_API_KEY = os.getenv('DOUBAO_API_KEY', '')
        DOUBAO_API_ENDPOINT = os.getenv('DOUBAO_API_ENDPOINT', 'https://ark.cn-beijing.volces.com/api/v3/chat/completions')
        DOUBAO_MODEL = os.getenv('DOUBAO_MODEL', 'doubao-vision-32k')
    
    try:
        if not DOUBAO_API_KEY:
            return "⚠️ **AI建议服务未配置**\n\n请配置云端 API 密钥后使用此功能。"
        
        # 压缩图片以加快传输速度
        print(f"[AI建议] 正在压缩图片...", flush=True)
        image_bytes = compress_image_for_api(image_path, max_size=1024, quality=85)
        image_data = base64.b64encode(image_bytes).decode('utf-8')
        
        # 使用JPEG格式（压缩后）
        mime_type = 'image/jpeg'
        
        # 构建请求
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {DOUBAO_API_KEY}'
        }
        
        payload = {
            "model": DOUBAO_MODEL,
            "max_completion_tokens": 2048,  # 减少token数量，加快响应速度
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{image_data}"
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ]
            # 移除 reasoning_effort 参数，使用默认值以加快速度
        }
        
        print(f"[AI建议] 正在调用AI获取建议（已优化速度）...", flush=True)
        start_time = time.time()
        response = requests.post(DOUBAO_API_ENDPOINT, headers=headers, json=payload, timeout=30)
        elapsed_time = time.time() - start_time
        print(f"[AI建议] API调用耗时: {elapsed_time:.2f}秒", flush=True)
        
        if response.status_code == 200:
            result_data = response.json()
            if 'choices' in result_data and len(result_data['choices']) > 0:
                content = result_data['choices'][0]['message']['content']
                return content
            else:
                return "⚠️ AI服务返回了异常格式的响应"
        else:
            return f"⚠️ **AI建议调用失败**\n\n状态码: {response.status_code}\n错误信息: {response.text}"
    
    except requests.Timeout:
        return "⚠️ **AI建议调用超时**\n\n请求超过30秒未响应，请稍后重试。"
    except Exception as e:
        print(f"[AI建议] 错误: {e}", flush=True)
        return f"⚠️ **获取AI建议时出错**\n\n错误信息: {str(e)}"


AGRI_ASSISTANT_SYSTEM = (
    '你是农业智能助手，只围绕种植、植保、灌溉、施肥、土壤、气象农事、果品采后、病虫害防治、无人机巡田与智慧农业场景作答。'
    '用简体中文，分点简短回答，非必要不超过 220 字；若问题与农业无关，用一两句话礼貌引导回农业主题。'
    '不编造具体农药商品名与剂量，涉及用药请提醒用户以当地农技部门与标签说明为准。'
)


def _parse_agri_assistant_image_payload(image_b64, image_mime):
    """无图：(None, None, None)；成功：(raw_b64, mime, None)；失败：(None, None, err_msg)。"""
    if not image_b64 or not isinstance(image_b64, str):
        return None, None, None
    raw = image_b64.strip()
    mime = (image_mime or 'image/jpeg').strip().split(';')[0].strip()
    if not mime.startswith('image/'):
        mime = 'image/jpeg'
    if raw.startswith('data:'):
        semi = raw.find(';base64,')
        if semi >= 0:
            hdr = raw[5:semi]
            if hdr and '/' in hdr:
                mime = hdr.strip() or mime
            raw = raw[semi + 8 :]
    raw = re.sub(r'\s+', '', raw)
    if len(raw) < 32:
        return None, None, '图片数据过短'
    try:
        decoded = base64.b64decode(raw, validate=False)
    except Exception:
        return None, None, '图片 Base64 无效'
    if len(decoded) > 4 * 1024 * 1024:
        return None, None, '图片超过 4MB，请压缩后重试'
    return raw, mime, None


def call_agri_assistant_llm(chat_messages, image_b64=None, image_mime='image/jpeg'):
    """文本对话；可选最后一轮用户消息带一张图（视觉）。"""
    try:
        from doubao_config import DOUBAO_API_KEY, DOUBAO_API_ENDPOINT, DOUBAO_MODEL
    except ImportError:
        DOUBAO_API_KEY = os.getenv('DOUBAO_API_KEY', '')
        DOUBAO_API_ENDPOINT = os.getenv(
            'DOUBAO_API_ENDPOINT', 'https://ark.cn-beijing.volces.com/api/v3/chat/completions'
        )
        DOUBAO_MODEL = os.getenv('DOUBAO_MODEL', 'doubao-seed-1-6-251015')
    if not DOUBAO_API_KEY or DOUBAO_API_KEY == 'your-api-key-here':
        return None, '未配置 API 密钥：请在 web_app/doubao_config.py 中填写 DOUBAO_API_KEY'
    img_raw, vision_mime, img_err = _parse_agri_assistant_image_payload(image_b64, image_mime)
    if img_err:
        return None, img_err
    has_image = img_raw is not None

    api_messages = [{'role': 'system', 'content': AGRI_ASSISTANT_SYSTEM}]
    tail = []
    for m in chat_messages[-14:]:
        if not isinstance(m, dict):
            continue
        role = m.get('role')
        if role not in ('user', 'assistant'):
            continue
        content = str(m.get('content', '')).strip()
        if not content:
            continue
        tail.append({'role': role, 'content': content[:3500]})
    if not tail:
        return None, '没有有效的对话内容'
    if tail[-1]['role'] != 'user':
        return None, '最后一条须为用户消息'

    for i, m in enumerate(tail):
        is_last = i == len(tail) - 1
        if is_last and has_image:
            text_part = m['content'][:2000]
            if not text_part:
                text_part = '请结合图片，从农业生产角度简要分析（作物长势、疑似问题或管理建议）。'
            api_messages.append(
                {
                    'role': 'user',
                    'content': [
                        {
                            'type': 'image_url',
                            'image_url': {'url': f'data:{vision_mime};base64,{img_raw}'},
                        },
                        {'type': 'text', 'text': text_part},
                    ],
                }
            )
        else:
            api_messages.append({'role': m['role'], 'content': m['content']})

    if len(api_messages) <= 1:
        return None, '没有有效的对话内容'
    headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {DOUBAO_API_KEY}'}
    max_tokens = 520 if has_image else 400
    timeout_s = 48 if has_image else 22
    payload = {
        'model': DOUBAO_MODEL,
        'max_completion_tokens': max_tokens,
        'temperature': 0.25,
        'messages': api_messages,
    }
    t0 = time.time()
    response = requests.post(DOUBAO_API_ENDPOINT, headers=headers, json=payload, timeout=timeout_s)
    elapsed = time.time() - t0
    print(f'[农业助手] API 耗时 {elapsed:.2f}s', flush=True)
    if response.status_code != 200:
        return None, f'服务暂不可用（HTTP {response.status_code}）'
    try:
        result_data = response.json()
        choices = result_data.get('choices') or []
        if not choices:
            return None, '模型未返回内容'
        content = (choices[0].get('message') or {}).get('content') or ''
        content = str(content).strip()
        if not content:
            return None, '模型返回为空'
        return content, None
    except (ValueError, KeyError, TypeError) as e:
        return None, f'解析响应失败: {e}'


@app.route('/api/agri_assistant', methods=['POST'])
def api_agri_assistant():
    """首页悬浮农业 AI 助手：多轮文本对话。"""
    data = request.get_json(force=True, silent=True) or {}
    messages = data.get('messages')
    if not isinstance(messages, list) or len(messages) == 0:
        q = data.get('message') or data.get('q')
        if q is not None and str(q).strip():
            messages = [{'role': 'user', 'content': str(q).strip()[:3500]}]
        else:
            return jsonify({'ok': False, 'error': '请提供 messages 数组或 message 字段'}), 400
    image_b64 = data.get('image_base64')
    image_mime = data.get('image_mime') or 'image/jpeg'
    reply, err = call_agri_assistant_llm(messages, image_b64=image_b64, image_mime=image_mime)
    if err:
        return jsonify({'ok': False, 'error': err}), 503
    return jsonify({'ok': True, 'reply': reply})


@app.route('/api/diagnose_pest', methods=['POST'])
def diagnose_pest():
    """调用AI进行病虫害诊断"""
    try:
        # 检查是否有文件
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': '没有上传文件'}), 400
        
        file = request.files['file']
        
        # 检查文件名
        if file.filename == '':
            return jsonify({'success': False, 'error': '文件名为空'}), 400
        
        # 检查文件类型
        if not allowed_file(file.filename):
            return jsonify({'success': False, 'error': '不支持的文件类型，请上传图片'}), 400
        
        # 保存文件
        filename = safe_upload_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # 识别：支持叶片(apple_disease)与果实(apple_fruit_disease)两种模型
        model_type = request.form.get('model_type', 'apple_disease')
        if model_type == 'apple_fruit_disease' and os.path.exists(APPLE_FRUIT_DISEASE_MODEL_PATH):
            model_to_use = 'apple_fruit_disease'
        elif os.path.exists(APPLE_DISEASE_MODEL_PATH):
            model_to_use = 'apple_disease'
        else:
            return jsonify({
                'success': False,
                'error': '未检测到本地病害模型，请先完成训练。如需 AI 分析请点击下方「获取详细建议」。'
            }), 400
        try:
            device = get_device()
            class_name, confidence, prob_dict, _, config = predict_image(
                filepath, model_type=model_to_use, device=device
            )
            desc = config.get('description_map', {}).get(class_name, class_name)
            is_healthy = 'healthy' in class_name.lower() or 'normal' in class_name.lower()
            risk_level = '低' if is_healthy else '高'
            action_window = '无需处理，保持常规巡检' if is_healthy else '建议 3 日内复查并采取防治措施'
            treatment_plan = (
                ['保持通风与合理施肥', '必要时使用针对性药剂', '记录位置便于后续复查']
                if not is_healthy
                else ['保持当前管理']
            )
            structured_result = {
                'disease_name': desc,
                'risk_level': risk_level,
                'confidence': float(confidence),
                'action_window': action_window,
                'treatment_plan': treatment_plan[:3],
            }
            return jsonify({'success': True, 'result': structured_result})
        except Exception as e:
            print(f"[病虫害] 本地模型识别失败: {e}", flush=True)
            return jsonify({'success': False, 'error': f'本地识别失败：{str(e)}'}), 500
        
    except Exception as e:
        import traceback
        error_msg = str(e)
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'处理失败: {error_msg}'}), 500


@app.route('/api/diagnose_pest_ai', methods=['POST'])
def diagnose_pest_ai():
    """调用云端大模型返回详细建议（与本地识别分离）"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': '没有上传文件'}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': '文件名为空'}), 400
        if not allowed_file(file.filename):
            return jsonify({'success': False, 'error': '不支持的文件类型'}), 400
        filename = safe_upload_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        result = call_doubao_api(filepath)
        structured = ensure_structured_diagnosis(result)
        if structured:
            return jsonify({'success': True, 'result': structured})
        return jsonify({'success': False, 'error': 'AI 返回格式异常'}), 500
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


def call_doubao_api(image_path):
    """
    调用AI服务进行病虫害识别
    
    使用前请配置API密钥：
    1. 设置环境变量：set DOUBAO_API_KEY=你的密钥
    2. 或修改 doubao_config.py 文件中的配置
    """
    try:
        # 导入配置
        try:
            from doubao_config import DOUBAO_API_KEY, DOUBAO_API_ENDPOINT, DOUBAO_MODEL, check_config
        except ImportError:
            # 如果配置文件不存在，使用默认配置
            DOUBAO_API_KEY = os.getenv('DOUBAO_API_KEY', '')
            DOUBAO_API_ENDPOINT = os.getenv('DOUBAO_API_ENDPOINT', 'https://ark.cn-beijing.volces.com/api/v3/chat/completions')
            DOUBAO_MODEL = os.getenv('DOUBAO_MODEL', 'doubao-vision-32k')
        
        # 检查配置
        if not DOUBAO_API_KEY:
            return {
                'disease_name': '未配置API',
                'risk_level': '中',
                'confidence': 0.0,
                'action_window': '配置API后再执行诊断',
                'treatment_plan': [
                    '先完成云端 API 密钥配置',
                    '重新上传同一叶片或果实图片',
                    '配置完成后再生成正式防治建议'
                ],
                'raw_text': 'AI诊断服务未配置'
            }
        
        # 读取图片并转换为base64
        with open(image_path, 'rb') as f:
            image_data = base64.b64encode(f.read()).decode('utf-8')
        
        # 获取图片MIME类型
        file_ext = os.path.splitext(image_path)[1].lower()
        mime_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp'
        }
        mime_type = mime_types.get(file_ext, 'image/jpeg')
        
        # 构建请求头（OpenAI 兼容格式）
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {DOUBAO_API_KEY}'
        }
        
        # 构建请求体（OpenAI 兼容格式）
        payload = {
            "model": DOUBAO_MODEL,
            "max_completion_tokens": 65535,  # 根据示例设置
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{image_data}"
                            }
                        },
                        {
                            "type": "text",
                            "text": "你是一位专业农业病虫害诊断专家。请只输出JSON对象，不要输出额外文字、Markdown或Emoji。必须包含以下字段：disease_name（字符串）、risk_level（仅高/中/低）、confidence（0-1浮点数）、action_window（字符串）、treatment_plan（数组，1-3条可执行措施）。如果无法确定，请给出保守结论并降低confidence。"
                        }
                    ]
                }
            ],
            "reasoning_effort": "medium"  # 根据示例添加
        }
        
        # 发送请求
        print(f"[AI诊断] 正在调用AI进行病虫害识别...")
        response = requests.post(DOUBAO_API_ENDPOINT, headers=headers, json=payload, timeout=60)
        
        if response.status_code == 200:
            result_data = response.json()
            print(f"[AI诊断] 识别成功")
            
            # 解析响应
            if 'choices' in result_data and len(result_data['choices']) > 0:
                content = result_data['choices'][0]['message']['content']
                return ensure_structured_diagnosis(content)
            else:
                return {
                    'disease_name': '结果解析失败',
                    'risk_level': '中',
                    'confidence': 0.0,
                    'action_window': '建议人工复核',
                    'treatment_plan': ['重新上传更清晰图片', '补充叶片特写', '人工巡田确认'],
                    'raw_text': "AI服务返回了异常格式的响应"
                }
        else:
            error_text = response.text
            print(f"[AI诊断] 调用失败，状态码: {response.status_code}")
            return {
                'disease_name': '调用失败',
                'risk_level': '中',
                'confidence': 0.0,
                'action_window': '建议稍后重试',
                'treatment_plan': ['检查API密钥', '检查网络连接', '检查API配额'],
                'raw_text': f"状态码: {response.status_code}; 错误信息: {error_text}"
            }
    
    except requests.exceptions.Timeout:
        return {
            'disease_name': '请求超时',
            'risk_level': '中',
            'confidence': 0.0,
            'action_window': '建议5分钟后重试',
            'treatment_plan': ['保持现场监测', '稍后重试识别', '必要时人工复核'],
            'raw_text': 'AI诊断响应时间过长'
        }
    except requests.exceptions.RequestException as e:
        return {
            'disease_name': '网络请求错误',
            'risk_level': '中',
            'confidence': 0.0,
            'action_window': '恢复网络后重试',
            'treatment_plan': ['检查网络连接', '检查DNS/代理设置', '重试诊断请求'],
            'raw_text': str(e)
        }
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print(f"[AI诊断] 发生错误: {error_detail}")
        return {
            'disease_name': '系统异常',
            'risk_level': '中',
            'confidence': 0.0,
            'action_window': '建议人工复核并联系管理员',
            'treatment_plan': ['记录错误日志', '检查服务状态', '人工巡检确认病情'],
            'raw_text': str(e)
        }

# ==================== 二维码生成API ====================

@app.route('/api/server_info', methods=['GET'])
def get_server_info():
    """获取服务器信息，包括IP地址"""
    local_ip = get_local_ip()
    server_url = f"http://{local_ip}:5000"
    
    return jsonify({
        'ip': local_ip,
        'port': 5000,
        'url': server_url,
        'uav_url': f"{server_url}/无人机控制"
    })

@app.route('/api/ip_camera', methods=['POST'])
def set_ip_camera():
    """设置IP摄像头URL（用于易视云等IP摄像头应用）"""
    global ip_camera_url, ip_camera_thread, ip_camera_running
    
    data = request.get_json()
    url = data.get('url', '').strip()
    
    if not url:
        return jsonify({'error': 'URL不能为空'}), 400
    
    # 停止之前的线程
    if ip_camera_running:
        ip_camera_running = False
        if ip_camera_thread:
            ip_camera_thread.join(timeout=2)
    
    ip_camera_url = url
    ip_camera_running = True
    
    # 启动新线程获取视频流
    ip_camera_thread = threading.Thread(target=fetch_ip_camera_stream, daemon=True)
    ip_camera_thread.start()
    
    return jsonify({'status': 'success', 'message': 'IP摄像头已启动', 'url': url})

def fetch_ip_camera_stream():
    """从IP摄像头URL获取视频流"""
    global ip_camera_url, ip_camera_running, video_stream_data
    
    print(f'[IP摄像头] 开始从 {ip_camera_url} 获取视频流...')
    
    cap = None
    frame_count = 0
    
    while ip_camera_running:
        try:
            # 打开视频流
            if cap is None or not cap.isOpened():
                cap = cv2.VideoCapture(ip_camera_url)
                if not cap.isOpened():
                    print(f'[IP摄像头] 无法打开视频流: {ip_camera_url}')
                    time.sleep(2)
                    continue
            
            # 读取帧
            ret, frame = cap.read()
            if not ret:
                print('[IP摄像头] 读取帧失败，尝试重新连接...')
                cap.release()
                cap = None
                time.sleep(1)
                continue
            
            # 调整大小（降低分辨率）
            frame = cv2.resize(frame, (640, 480))
            
            # 转换为JPEG
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
            frame_base64 = base64.b64encode(buffer).decode('utf-8')
            
            # 更新视频流数据
            video_stream_data['frame'] = frame_base64
            video_stream_data['timestamp'] = time.time()
            
            # 广播给所有电脑端客户端
            socketio.emit('video_stream', {
                'frame': frame_base64,
                'timestamp': video_stream_data['timestamp']
            }, broadcast=True, include_self=False)
            
            frame_count += 1
            if frame_count % 100 == 0:
                print(f'[IP摄像头] 已发送 {frame_count} 帧视频')
            
            time.sleep(0.1)  # 约10fps
            
        except Exception as e:
            print(f'[IP摄像头] 错误: {e}')
            if cap:
                cap.release()
                cap = None
            time.sleep(2)
    
    if cap:
        cap.release()
    print('[IP摄像头] 视频流已停止')

def track_apple_with_template(frame, template, search_bbox):
    """
    使用模板匹配跟踪苹果位置
    
    参数:
        frame: 当前帧（OpenCV格式，BGR）
        template: 模板图像（从之前检测到的苹果区域提取）
        search_bbox: 搜索区域 (x, y, w, h)，在上一帧位置附近搜索
    
    返回:
        bbox: 新的边界框，如果跟踪失败返回None
    """
    try:
        if template is None or search_bbox is None:
            return None
        
        x, y, w, h = search_bbox
        height, width = frame.shape[:2]
        
        # 扩大搜索区域（允许摄像机移动）
        search_margin = 50
        search_x = max(0, x - search_margin)
        search_y = max(0, y - search_margin)
        search_w = min(width - search_x, w + search_margin * 2)
        search_h = min(height - search_y, h + search_margin * 2)
        
        # 提取搜索区域
        search_roi = frame[search_y:search_y+search_h, search_x:search_x+search_w]
        if search_roi.size == 0 or search_roi.shape[0] < template.shape[0] or search_roi.shape[1] < template.shape[1]:
            return None
        
        # 模板匹配
        result = cv2.matchTemplate(search_roi, template, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        
        # 如果匹配度足够高，认为跟踪成功
        if max_val > 0.5:  # 匹配度阈值
            # 计算在原图中的位置
            new_x = search_x + max_loc[0]
            new_y = search_y + max_loc[1]
            return (new_x, new_y, w, h)
        
        return None
    except Exception as e:
        return None

def locate_apple_in_frame(frame):
    """
    定位苹果在视频帧中的位置（使用颜色分割和轮廓检测）
    
    参数:
        frame: OpenCV格式的帧（numpy array，BGR格式）
    
    返回:
        bbox: 边界框 (x, y, width, height)，如果未找到返回None
    """
    try:
        # 转换为HSV颜色空间（更适合颜色分割）
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        
        # 定义苹果的颜色范围（红色、绿色、黄色）
        # 红色苹果（HSV中的红色有两个范围，因为红色在色相环的两端）
        lower_red1 = np.array([0, 50, 50])
        upper_red1 = np.array([10, 255, 255])
        lower_red2 = np.array([170, 50, 50])
        upper_red2 = np.array([180, 255, 255])
        
        # 绿色苹果
        lower_green = np.array([40, 50, 50])
        upper_green = np.array([80, 255, 255])
        
        # 黄色苹果
        lower_yellow = np.array([20, 50, 50])
        upper_yellow = np.array([30, 255, 255])
        
        # 创建颜色掩码
        mask_red1 = cv2.inRange(hsv, lower_red1, upper_red1)
        mask_red2 = cv2.inRange(hsv, lower_red2, upper_red2)
        mask_red = cv2.bitwise_or(mask_red1, mask_red2)
        mask_green = cv2.inRange(hsv, lower_green, upper_green)
        mask_yellow = cv2.inRange(hsv, lower_yellow, upper_yellow)
        
        # 合并所有颜色掩码
        mask = cv2.bitwise_or(mask_red, mask_green)
        mask = cv2.bitwise_or(mask, mask_yellow)
        
        # 形态学操作：去除噪声
        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        
        # 找到轮廓
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if len(contours) == 0:
            return None
        
        # 选择最大的轮廓（最可能是苹果）
        largest_contour = max(contours, key=cv2.contourArea)
        
        # 计算轮廓面积，过滤太小的区域
        area = cv2.contourArea(largest_contour)
        if area < 500:  # 面积阈值，可以根据实际情况调整
            return None
        
        # 获取边界框
        x, y, w, h = cv2.boundingRect(largest_contour)
        
        # 确保是正方形（取较大的边作为边长）
        size = max(w, h)
        # 计算中心点
        center_x = x + w // 2
        center_y = y + h // 2
        # 重新计算边界框，使其为正方形
        x = max(0, center_x - size // 2)
        y = max(0, center_y - size // 2)
        # 确保不超出图片边界
        height, width = frame.shape[:2]
        if x + size > width:
            x = width - size
        if y + size > height:
            y = height - size
        if x < 0:
            x = 0
        if y < 0:
            y = 0
        size = min(size, width - x, height - y)
        
        return (x, y, size, size)
        
    except Exception as e:
        print(f'[苹果定位] 定位失败: {e}', flush=True)
        return None

def draw_apple_box_on_frame(frame, bbox, confidence=0.0):
    """
    在视频帧上画苹果检测框（红色正方形）
    
    参数:
        frame: OpenCV格式的帧（numpy array）
        bbox: 边界框 (x, y, width, height)，如果为None则不画框
        confidence: 置信度（用于显示，当前未使用）
    
    返回:
        annotated_frame: 标注后的帧
    """
    annotated_frame = frame.copy()
    
    if bbox is not None:
        x, y, w, h = bbox
        color = (0, 0, 255)  # 红色 (BGR格式)
        thickness = 3
        
        # 画红色正方形框
        cv2.rectangle(annotated_frame, (x, y), (x + w, y + h), color, thickness)
    
    return annotated_frame

def detect_apple_in_frame(frame, model, config, device):
    """
    检测视频帧中是否有苹果（只检测，不画框）
    
    参数:
        frame: OpenCV格式的帧（numpy array）
        model: 已加载的demo2模型
        config: 模型配置
        device: 设备
    
    返回:
        is_apple: 是否检测到苹果
        confidence: 置信度
    """
    try:
        from torchvision import transforms
        from PIL import Image
        import torch.nn.functional as F
        
        # 将OpenCV格式转换为PIL格式
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(frame_rgb)
        
        # 预处理
        transform = transforms.Compose([
            transforms.Resize(256),
            transforms.CenterCrop(224),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])
        
        img_tensor = transform(pil_image).unsqueeze(0).to(device)
        
        # 预测
        with torch.no_grad():
            outputs = model(img_tensor)
            probabilities = F.softmax(outputs, dim=1)
            confidence, predicted = torch.max(probabilities, 1)
        
        # 获取类别
        class_idx = predicted.item()
        classes = config['classes']
        class_name = classes[class_idx]
        confidence_score = confidence.item()
        
        # 判断是否为苹果
        is_apple = (class_name == 'Apple' and confidence_score > 0.5)  # 置信度阈值0.5
        
        return is_apple, confidence_score
        
    except Exception as e:
        print(f'[苹果检测] 检测失败: {e}', flush=True)
        import traceback
        traceback.print_exc()
        return False, 0.0

def fetch_virtual_camera_stream():
    """从虚拟摄像头设备读取视频流（无他伴侣等）"""
    global virtual_camera_device_id, virtual_camera_running, video_stream_data, apple_detection_cache, apple_tracking, apple_detection_cache
    
    print(f'[虚拟摄像头] ========== 线程开始执行 ==========', flush=True)
    print(f'[虚拟摄像头] 线程ID: {threading.current_thread().ident}', flush=True)
    print(f'[虚拟摄像头] 开始从设备 {virtual_camera_device_id} 读取视频流...', flush=True)
    print(f'[虚拟摄像头] virtual_camera_running = {virtual_camera_running}', flush=True)
    
    cap = None
    frame_count = 0
    consecutive_failures = 0
    
    while virtual_camera_running:
        try:
            # 打开摄像头设备（Windows上使用DirectShow）
            if cap is None or not cap.isOpened():
                print(f'[虚拟摄像头] 尝试打开设备 {virtual_camera_device_id}...', flush=True)
                if sys.platform == 'win32':
                    cap = cv2.VideoCapture(virtual_camera_device_id, cv2.CAP_DSHOW)
                    # 设置缓冲区大小为1，减少延迟
                    if cap.isOpened():
                        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                else:
                    cap = cv2.VideoCapture(virtual_camera_device_id)
                    if cap.isOpened():
                        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                if not cap.isOpened():
                    print(f'[虚拟摄像头] 无法打开设备 {virtual_camera_device_id}，尝试其他设备...', flush=True)
                    # 尝试自动检测可用的摄像头设备（优先选择虚拟摄像头）
                    found = False
                    virtual_device_id = None
                    physical_device_id = None
                    
                    for device_id in range(10):  # 检查前10个设备
                        try:
                            if sys.platform == 'win32':
                                test_cap = cv2.VideoCapture(device_id, cv2.CAP_DSHOW)
                            else:
                                test_cap = cv2.VideoCapture(device_id)
                            
                            if test_cap.isOpened():
                                ret, test_frame = test_cap.read()
                                if ret and test_frame is not None:
                                    device_name = get_camera_device_name(device_id)
                                    is_virtual = any(keyword in device_name.lower() for keyword in 
                                                   ['virtual', 'obs', '无他', 'wuta', 'mirror', 'screen'])
                                    
                                    print(f'[虚拟摄像头] 找到可用设备: {device_id} - {device_name} (分辨率: {test_frame.shape[1]}x{test_frame.shape[0]})', flush=True)
                                    
                                    if is_virtual and virtual_device_id is None:
                                        virtual_device_id = device_id
                                    elif not is_virtual and physical_device_id is None:
                                        physical_device_id = device_id
                                    
                                    test_cap.release()
                                else:
                                    test_cap.release()
                            else:
                                test_cap.release()
                        except Exception as e:
                            print(f'[虚拟摄像头] 检测设备 {device_id} 时出错: {e}', flush=True)
                            continue
                    
                    # 优先使用虚拟摄像头
                    if virtual_device_id is not None:
                        device_id = virtual_device_id
                        print(f'[虚拟摄像头] ✅ 自动选择虚拟摄像头: 设备 {device_id}', flush=True)
                    elif physical_device_id is not None:
                        device_id = physical_device_id
                        print(f'[虚拟摄像头] ⚠️ 未找到虚拟摄像头，使用物理摄像头: 设备 {device_id}', flush=True)
                    else:
                        device_id = None
                    
                    if device_id is not None:
                        if sys.platform == 'win32':
                            cap = cv2.VideoCapture(device_id, cv2.CAP_DSHOW)
                        else:
                            cap = cv2.VideoCapture(device_id)
                        virtual_camera_device_id = device_id
                        found = True
                    
                    if not found:
                        consecutive_failures += 1
                        if consecutive_failures % 5 == 0:
                            print(f'[虚拟摄像头] 未找到可用的摄像头设备 (已尝试 {consecutive_failures} 次)', flush=True)
                        time.sleep(2)
                        continue
                    else:
                        consecutive_failures = 0
                else:
                    # 设置摄像头参数（可选）
                    try:
                        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                        print(f'[虚拟摄像头] 设备 {virtual_camera_device_id} 已打开', flush=True)
                    except:
                        pass
            
            # 读取帧（添加超时保护）
            ret = False
            frame = None
            try:
                # 设置超时：如果read()阻塞超过0.5秒，就跳过这一帧
                start_time = time.time()
                ret, frame = cap.read()
                read_time = time.time() - start_time
                
                if read_time > 0.5:
                    if frame_count % 30 == 0:  # 每30帧打印一次警告
                        print(f'[虚拟摄像头] ⚠️ 读取帧耗时过长: {read_time:.2f}秒 (设备可能响应慢)', flush=True)
                    # 如果耗时过长但读取成功，仍然使用这一帧
                    # 如果耗时过长且读取失败，ret已经是False
            except Exception as read_error:
                if frame_count % 30 == 0:  # 减少错误日志频率
                    print(f'[虚拟摄像头] 读取帧时出错: {read_error}', flush=True)
                ret = False
            
            # 验证帧数据
            if not ret or frame is None:
                consecutive_failures += 1
                if consecutive_failures % 10 == 0:
                    print(f'[虚拟摄像头] 读取帧失败 (已失败 {consecutive_failures} 次)，尝试重新连接...', flush=True)
                if cap:
                    cap.release()
                cap = None
                time.sleep(1)
                continue
            
            # 验证帧尺寸和数据类型
            if len(frame.shape) != 3 or frame.shape[0] < 10 or frame.shape[1] < 10:
                print(f'[虚拟摄像头] ⚠️ 帧数据异常: shape={frame.shape}', flush=True)
                consecutive_failures += 1
                if consecutive_failures >= 5:
                    print(f'[虚拟摄像头] 帧数据持续异常，重新连接设备...', flush=True)
                    if cap:
                        cap.release()
                    cap = None
                    time.sleep(1)
                    continue
            
            consecutive_failures = 0
            
            # 调整大小（降低分辨率以提高传输速度）
            try:
                frame = cv2.resize(frame, (640, 480))
            except Exception as resize_error:
                print(f'[虚拟摄像头] 调整帧大小失败: {resize_error}', flush=True)
                continue
            
            # 苹果检测和跟踪（每N帧检测一次，其他帧使用跟踪）
            if apple_detection_enabled:
                global apple_tracking
                current_bbox = None
                is_apple = apple_detection_cache['is_apple']
                
                # 每N帧进行一次实际检测
                if frame_count % apple_detection_interval == 0:
                    try:
                        # 获取demo2模型（用于检测苹果）
                        apple_model, apple_config = get_model('demo2', device)
                        is_apple, apple_confidence = detect_apple_in_frame(frame, apple_model, apple_config, device)
                        
                        # 如果检测到苹果，尝试定位苹果位置
                        bbox = None
                        if is_apple:
                            bbox = locate_apple_in_frame(frame)
                            if bbox is not None:
                                # 保存模板用于跟踪
                                x, y, w, h = bbox
                                height, width = frame.shape[:2]
                                # 确保边界有效
                                x = max(0, min(x, width - w))
                                y = max(0, min(y, height - h))
                                w = min(w, width - x)
                                h = min(h, height - y)
                                
                                if w > 0 and h > 0:
                                    # 提取模板（稍微扩大一点区域）
                                    template_size = max(w, h) + 20
                                    template_x = max(0, x - 10)
                                    template_y = max(0, y - 10)
                                    template_w = min(template_size, width - template_x)
                                    template_h = min(template_size, height - template_y)
                                    
                                    apple_tracking['template'] = frame[template_y:template_y+template_h, template_x:template_x+template_w].copy()
                                    apple_tracking['last_bbox'] = bbox
                                    apple_tracking['last_success_time'] = time.time()  # 更新成功时间
                                    
                                    # 计算速度（用于预测）
                                    if apple_tracking['last_bbox'] is not None and len(apple_tracking['last_bbox']) == 4:
                                        old_x, old_y = apple_tracking['last_bbox'][0], apple_tracking['last_bbox'][1]
                                        apple_tracking['velocity'] = (x - old_x, y - old_y)
                                    
                                    current_bbox = bbox
                            elif frame_count % 30 == 0:
                                print(f'[苹果检测] ⚠️ 检测到苹果但无法定位位置', flush=True)
                        
                        # 更新缓存
                        old_is_apple = apple_detection_cache['is_apple']
                        apple_detection_cache['is_apple'] = is_apple
                        apple_detection_cache['confidence'] = apple_confidence
                        
                        # 如果检测结果发生变化，通过WebSocket通知前端
                        if is_apple != old_is_apple:
                            try:
                                clients_to_send = list(video_stream_data['clients'])
                                for client_id in clients_to_send:
                                    socketio.emit('apple_detection', {
                                        'detected': is_apple,
                                        'confidence': apple_confidence
                                    }, room=client_id, namespace='/')
                                if is_apple:
                                    print(f'[苹果检测] ✅ 检测到苹果，置信度: {apple_confidence*100:.1f}%', flush=True)
                                else:
                                    print(f'[苹果检测] 未检测到苹果', flush=True)
                            except Exception as emit_error:
                                print(f'[苹果检测] 发送检测结果失败: {emit_error}', flush=True)
                    except Exception as detect_error:
                        if frame_count % 100 == 0:  # 减少错误日志频率
                            print(f'[苹果检测] 检测出错: {detect_error}', flush=True)
                
                # 在非检测帧中，使用跟踪
                else:
                    if is_apple and apple_tracking['last_bbox'] is not None and apple_tracking['template'] is not None:
                        # 尝试使用模板匹配跟踪
                        tracked_bbox = track_apple_with_template(frame, apple_tracking['template'], apple_tracking['last_bbox'])
                        
                        if tracked_bbox is not None:
                            # 跟踪成功
                            current_bbox = tracked_bbox
                            apple_tracking['last_bbox'] = tracked_bbox
                            apple_tracking['last_success_time'] = time.time()  # 更新成功时间
                            
                            # 更新速度
                            if apple_tracking['last_bbox'] is not None and len(apple_tracking['last_bbox']) == 4:
                                old_x, old_y = apple_tracking['last_bbox'][0], apple_tracking['last_bbox'][1]
                                apple_tracking['velocity'] = (tracked_bbox[0] - old_x, tracked_bbox[1] - old_y)
                        else:
                            # 跟踪失败，检查时间
                            current_time = time.time()
                            time_since_success = current_time - apple_tracking['last_success_time'] if apple_tracking['last_success_time'] is not None else float('inf')
                            
                            if time_since_success < apple_tracking['max_tracking_timeout']:
                                # 未超过5秒，使用速度预测位置
                                last_x, last_y = apple_tracking['last_bbox'][0], apple_tracking['last_bbox'][1]
                                vx, vy = apple_tracking['velocity']
                                
                                # 预测新位置（速度衰减）
                                predicted_x = int(last_x + vx * 0.8)
                                predicted_y = int(last_y + vy * 0.8)
                                
                                # 确保不超出边界
                                height, width = frame.shape[:2]
                                w, h = apple_tracking['last_bbox'][2], apple_tracking['last_bbox'][3]
                                predicted_x = max(0, min(predicted_x, width - w))
                                predicted_y = max(0, min(predicted_y, height - h))
                                
                                current_bbox = (predicted_x, predicted_y, w, h)
                                apple_tracking['last_bbox'] = current_bbox
                            else:
                                # 超过5秒未检测到，移除红框
                                current_bbox = None
                                apple_detection_cache['is_apple'] = False
                                apple_tracking['template'] = None
                                apple_tracking['last_bbox'] = None
                                apple_tracking['last_success_time'] = None
                                apple_tracking['velocity'] = (0, 0)
                
                # 更新缓存的bbox
                apple_detection_cache['bbox'] = current_bbox
                
                # 每一帧都根据缓存结果画框（确保红框持续显示，不闪烁）
                if apple_detection_cache['is_apple'] and current_bbox is not None:
                    frame = draw_apple_box_on_frame(frame, current_bbox, apple_detection_cache['confidence'])
            
            # 转换为JPEG
            try:
                _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                if buffer is None or len(buffer) == 0:
                    print(f'[虚拟摄像头] ⚠️ JPEG编码失败，跳过此帧', flush=True)
                    continue
                frame_base64 = base64.b64encode(buffer).decode('utf-8')
                if not frame_base64 or len(frame_base64) < 100:  # 太小的数据可能是损坏的
                    print(f'[虚拟摄像头] ⚠️ Base64编码数据异常，跳过此帧', flush=True)
                    continue
            except Exception as encode_error:
                print(f'[虚拟摄像头] 编码帧失败: {encode_error}', flush=True)
                continue
            
            # 更新视频流数据
            video_stream_data['frame'] = frame_base64
            video_stream_data['timestamp'] = time.time()
            
            # 发送给所有已连接的客户端
            try:
                # 获取所有连接的客户端并发送
                clients_to_send = list(video_stream_data['clients'])
                if clients_to_send:
                    if frame_count == 1:
                        print(f'[虚拟摄像头] 准备向 {len(clients_to_send)} 个客户端发送视频流', flush=True)
                    for client_id in clients_to_send:
                        try:
                            socketio.emit('video_stream', {
                                'frame': frame_base64,
                                'timestamp': video_stream_data['timestamp']
                            }, room=client_id, namespace='/')
                        except Exception as e:
                            if frame_count <= 3:  # 只在前几帧打印错误
                                print(f'[虚拟摄像头] 向客户端 {client_id} 发送失败: {e}', flush=True)
                else:
                    if frame_count == 1 or frame_count % 100 == 0:
                        print(f'[虚拟摄像头] ⚠️ 没有已注册的客户端，无法发送视频流', flush=True)
            except Exception as emit_error:
                print(f'[虚拟摄像头] 发送视频流失败: {emit_error}', flush=True)
            
            frame_count += 1
            if frame_count == 1:
                print(f'[虚拟摄像头] ✅ 成功发送第1帧视频', flush=True)
            elif frame_count % 100 == 0:
                print(f'[虚拟摄像头] 已发送 {frame_count} 帧视频', flush=True)
            
            time.sleep(0.033)  # 约30fps
            
        except Exception as e:
            print(f'[虚拟摄像头] 错误: {e}', flush=True)
            import traceback
            traceback.print_exc()
            if cap:
                cap.release()
                cap = None
            time.sleep(2)
    
    if cap:
        cap.release()
    print('[虚拟摄像头] 视频流已停止', flush=True)

@app.route('/api/virtual_camera', methods=['POST'])
def set_virtual_camera():
    """设置虚拟摄像头设备（无他伴侣等）"""
    global virtual_camera_enabled, virtual_camera_device_id, virtual_camera_thread, virtual_camera_running
    global ip_camera_running, ip_camera_thread
    
    data = request.get_json()
    device_id = data.get('device_id')  # 如果为None，则自动检测
    
    # 停止之前的IP摄像头
    if ip_camera_running:
        ip_camera_running = False
        if ip_camera_thread:
            ip_camera_thread.join(timeout=2)
    
    # 停止之前的虚拟摄像头线程
    if virtual_camera_running:
        virtual_camera_running = False
        if virtual_camera_thread:
            virtual_camera_thread.join(timeout=2)
    
    # 如果未指定设备ID，尝试自动检测（优先选择虚拟摄像头）
    if device_id is None:
        print('[虚拟摄像头] 自动检测摄像头设备（优先选择虚拟摄像头）...', flush=True)
        device_id = None
        virtual_device_id = None
        physical_device_id = None
        
        for test_id in range(10):  # 检查前10个设备
            try:
                # 在Windows上优先使用DirectShow
                if sys.platform == 'win32':
                    test_cap = cv2.VideoCapture(test_id, cv2.CAP_DSHOW)
                else:
                    test_cap = cv2.VideoCapture(test_id)
                
                if test_cap.isOpened():
                    ret, frame = test_cap.read()
                    if ret and frame is not None:
                        device_name = get_camera_device_name(test_id)
                        print(f'[虚拟摄像头] 找到可用设备: {test_id} - {device_name}', flush=True)
                        
                        # 判断是否为虚拟摄像头（扩展关键词列表）
                        device_name_lower = device_name.lower()
                        is_virtual = any(keyword in device_name_lower for keyword in 
                                       ['virtual', 'obs', '无他', 'wuta', 'mirror', 'screen', 
                                        'ivcam', 'droidcam', 'camo', 'epoccam', '虚拟', 
                                        '手机', 'phone', 'mobile', 'android', 'ios'])
                        
                        # 额外判断：设备ID >= 2 的设备更可能是虚拟摄像头
                        # （设备0和1通常是电脑的物理摄像头）
                        if not is_virtual and test_id >= 2:
                            # 对于设备ID >= 2的设备，即使名称不明确，也优先考虑为虚拟摄像头
                            print(f'[虚拟摄像头] 设备 {test_id} (ID>=2) 可能是虚拟摄像头，优先考虑', flush=True)
                            if virtual_device_id is None:
                                virtual_device_id = test_id
                                is_virtual = True  # 标记为虚拟摄像头
                                print(f'[虚拟摄像头] ✅ 将设备 {test_id} 识别为虚拟摄像头（基于设备ID）', flush=True)
                        
                        if is_virtual and virtual_device_id != test_id:
                            if virtual_device_id is None:
                                virtual_device_id = test_id
                                print(f'[虚拟摄像头] ✅ 识别为虚拟摄像头: {test_id}', flush=True)
                        elif not is_virtual and physical_device_id is None and test_id < 2:
                            # 只记录设备0和1为物理摄像头
                            physical_device_id = test_id
                            print(f'[虚拟摄像头] 识别为物理摄像头: {test_id}', flush=True)
                        
                        test_cap.release()
                    else:
                        test_cap.release()
                else:
                    test_cap.release()
            except Exception as e:
                print(f'[虚拟摄像头] 检测设备 {test_id} 时出错: {e}', flush=True)
                continue
        
        # 优先使用虚拟摄像头，如果没有找到虚拟摄像头，拒绝使用物理摄像头
        if virtual_device_id is not None:
            device_id = virtual_device_id
            print(f'[虚拟摄像头] ✅ 自动选择虚拟摄像头: 设备 {device_id}', flush=True)
        elif physical_device_id is not None:
            # 如果只找到物理摄像头，返回错误，要求用户手动选择
            error_msg = f'⚠️ 未找到虚拟摄像头设备！\n\n'
            error_msg += f'找到的物理摄像头: 设备 {physical_device_id}\n\n'
            error_msg += f'请确保：\n'
            error_msg += f'1. 无他伴侣已启动并连接手机\n'
            error_msg += f'2. 虚拟摄像头已激活\n'
            error_msg += f'3. 点击"检测设备"查看所有设备\n'
            error_msg += f'4. 手动输入虚拟摄像头的设备ID\n\n'
            error_msg += f'💡 提示：虚拟摄像头通常不是设备0或1，可能是设备2、3等'
            print(f'[虚拟摄像头] {error_msg}', flush=True)
            return jsonify({'error': error_msg}), 400
        else:
            return jsonify({'error': '未找到可用的摄像头设备\n\n请确保：\n1. 无他伴侣已启动并连接手机\n2. 虚拟摄像头已激活\n3. 或者点击"检测设备"查看所有可用设备'}), 400
    else:
        device_id = int(device_id)
    
    virtual_camera_device_id = device_id
    virtual_camera_running = True
    virtual_camera_enabled = True
    
    print(f'[虚拟摄像头] 准备启动线程，设备ID: {device_id}', flush=True)
    print(f'[虚拟摄像头] virtual_camera_running = {virtual_camera_running}', flush=True)
    
    # 启动新线程获取视频流
    try:
        virtual_camera_thread = threading.Thread(target=fetch_virtual_camera_stream, daemon=True)
        virtual_camera_thread.start()
        print(f'[虚拟摄像头] 线程已启动，线程ID: {virtual_camera_thread.ident}', flush=True)
        # 等待一小段时间确保线程开始执行
        import time
        time.sleep(0.1)
    except Exception as e:
        print(f'[虚拟摄像头] 启动线程失败: {e}', flush=True)
        import traceback
        traceback.print_exc()
        virtual_camera_running = False
        return jsonify({'error': f'启动线程失败: {str(e)}'}), 500
    
    return jsonify({
        'status': 'success', 
        'message': f'虚拟摄像头已启动（设备ID: {device_id}）',
        'device_id': device_id
    })

@app.route('/api/virtual_camera/stop', methods=['POST'])
def stop_virtual_camera():
    """停止虚拟摄像头"""
    global virtual_camera_enabled, virtual_camera_running, virtual_camera_thread
    
    if virtual_camera_running:
        virtual_camera_running = False
        if virtual_camera_thread:
            virtual_camera_thread.join(timeout=2)
    
    virtual_camera_enabled = False
    
    return jsonify({'status': 'success', 'message': '虚拟摄像头已停止'})

def get_camera_device_name(device_id):
    """尝试获取摄像头设备名称（Windows DirectShow）"""
    try:
        # 在Windows上尝试使用DirectShow后端获取设备名称
        if sys.platform == 'win32':
            try:
                # 尝试使用DirectShow
                cap = cv2.VideoCapture(device_id, cv2.CAP_DSHOW)
                if cap.isOpened():
                    # 尝试获取设备名称（某些OpenCV版本支持）
                    backend_name = cap.getBackendName()
                    cap.release()
                    return f"设备 {device_id} ({backend_name})"
            except:
                pass
        
        # 如果无法获取名称，返回默认名称
        return f"设备 {device_id}"
    except:
        return f"设备 {device_id}"

@app.route('/api/capture_photo', methods=['POST'])
def capture_photo():
    """拍照功能：保存当前视频帧到appleresult文件夹"""
    try:
        data = request.get_json()
        if not data or 'image_data' not in data:
            return jsonify({'success': False, 'error': '缺少图片数据'}), 400
        
        # 创建appleresult文件夹（如果不存在）
        apple_result_folder = os.path.join(BASE_DIR, 'appleresult')
        os.makedirs(apple_result_folder, exist_ok=True)
        
        # 解码base64图片数据
        image_data = data['image_data']
        try:
            image_bytes = base64.b64decode(image_data)
        except Exception as e:
            return jsonify({'success': False, 'error': f'Base64解码失败: {str(e)}'}), 400
        
        # 生成文件名（使用时间戳）
        from datetime import datetime
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]  # 精确到毫秒
        filename = f'apple_{timestamp}.jpg'
        filepath = os.path.join(apple_result_folder, filename)
        
        # 保存图片到appleresult文件夹
        with open(filepath, 'wb') as f:
            f.write(image_bytes)
        
        # 同时保存到uploads文件夹（用于主页识别）
        upload_filename = f'captured_{timestamp}.jpg'
        upload_filepath = os.path.join(app.config['UPLOAD_FOLDER'], upload_filename)
        with open(upload_filepath, 'wb') as f:
            f.write(image_bytes)
        
        print(f'[拍照] ✅ 成功保存图片: {filepath}', flush=True)
        print(f'[拍照] ✅ 同时保存到uploads: {upload_filepath}', flush=True)
        
        return jsonify({
            'success': True,
            'filename': filename,
            'filepath': filepath,
            'upload_filename': upload_filename,  # 用于主页识别
            'image_url': f'/uploads/{upload_filename}',  # 图片URL
            'image_data': image_data  # base64数据，用于前端显示
        })
        
    except Exception as e:
        print(f'[拍照] ❌ 保存失败: {e}', flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/virtual_camera/list', methods=['GET'])
def list_virtual_cameras():
    """列出所有可用的摄像头设备"""
    devices = []
    print('[虚拟摄像头] 正在扫描所有摄像头设备...', flush=True)
    
    for device_id in range(10):  # 检查前10个设备
        try:
            # 在Windows上优先使用DirectShow
            if sys.platform == 'win32':
                cap = cv2.VideoCapture(device_id, cv2.CAP_DSHOW)
            else:
                cap = cv2.VideoCapture(device_id)
            
            if cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None:
                    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    
                    # 尝试获取设备名称
                    device_name = get_camera_device_name(device_id)
                    
                    # 判断是否为虚拟摄像头（通过名称关键词）
                    is_virtual = any(keyword in device_name.lower() for keyword in 
                                   ['virtual', 'obs', '无他', 'wuta', 'mirror', 'screen'])
                    
                    devices.append({
                        'device_id': device_id,
                        'width': width,
                        'height': height,
                        'name': device_name,
                        'is_virtual': is_virtual,
                        'available': True
                    })
                    print(f'[虚拟摄像头] 找到设备 {device_id}: {device_name} ({width}x{height})', flush=True)
                cap.release()
            else:
                cap.release()
        except Exception as e:
            print(f'[虚拟摄像头] 检查设备 {device_id} 时出错: {e}', flush=True)
            continue
    
    # 按是否为虚拟摄像头排序，虚拟摄像头优先
    devices.sort(key=lambda x: (not x.get('is_virtual', False), x['device_id']))
    
    print(f'[虚拟摄像头] 共找到 {len(devices)} 个可用设备', flush=True)
    return jsonify({
        'status': 'success',
        'devices': devices
    })

@app.route('/api/task_plan/source_data', methods=['GET'])
def task_plan_source_data():
    """任务规划页：获取可生成任务的数据源（灌溉建议、风险预警）"""
    try:
        limit = request.args.get('limit', type=int, default=10)
        conn = get_db_connection()
        irrig_rows = conn.execute(
            """SELECT id, plot_name, crop_type, growth_stage, suggested_water_lpm, suggested_duration_min,
                      priority, recommendation, created_at
               FROM irrigation_plans ORDER BY id DESC LIMIT ?""",
            (limit,)
        ).fetchall()
        risk_rows = conn.execute(
            """SELECT id, plot_name, risk_type, risk_level, probability, operation_window, recommendation, created_at
               FROM risk_alerts ORDER BY id DESC LIMIT ?""",
            (limit,)
        ).fetchall()
        conn.close()
        irrigation = [dict(r) for r in irrig_rows]
        risk_alerts = [dict(r) for r in risk_rows]
        return jsonify({
            'success': True,
            'data': {
                'irrigation_plans': irrigation,
                'risk_alerts': risk_alerts,
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/task_plan/generate', methods=['POST'])
def task_plan_generate():
    """根据采集数据批量生成无人机任务（灌溉、喷药）并同步到后台"""
    if ROLE_LEVELS.get(get_request_role(), 0) < ROLE_LEVELS['operator']:
        return jsonify({'success': False, 'error': '权限不足，至少需要 operator 角色'}), 403
    try:
        data = request.get_json() or {}
        irrigation_ids = data.get('irrigation_ids', [])
        risk_ids = data.get('risk_ids', [])
        if not irrigation_ids and not risk_ids:
            return jsonify({'success': False, 'error': '请选择至少一条待生成任务'}), 400

        conn = get_db_connection()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        created = []

        for pid in irrigation_ids:
            row = conn.execute(
                "SELECT plot_name, crop_type, suggested_water_lpm, suggested_duration_min, priority, recommendation "
                "FROM irrigation_plans WHERE id = ?", (pid,)
            ).fetchone()
            if not row:
                continue
            detail = f"{row['recommendation']} 流量{row['suggested_water_lpm']}L/min 时长{row['suggested_duration_min']}分钟"
            cursor = conn.execute(
                """INSERT INTO tasks (title, task_type, plot_name, priority, status, assignee, detail, planned_start, planned_end, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (f"灌溉-{row['plot_name']}-{row['crop_type']}", '灌溉', row['plot_name'], row['priority'] or '中',
                 '待执行', '无人机#001', detail, now, '', now, now)
            )
            task_id = cursor.lastrowid
            conn.execute(
                """INSERT INTO operation_logs (log_type, source, related_task_id, model_name, class_name, confidence, action_summary, payload_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                ('task', 'task_plan', task_id, '任务规划', '灌溉', None, f'从灌溉建议生成: {row["plot_name"]}',
                 json.dumps({'source': 'irrigation_plan', 'source_id': pid}, ensure_ascii=False), now)
            )
            created.append({'id': task_id, 'type': '灌溉', 'title': f"灌溉-{row['plot_name']}"})

        for rid in risk_ids:
            row = conn.execute(
                "SELECT plot_name, risk_type, risk_level, recommendation, operation_window "
                "FROM risk_alerts WHERE id = ?", (rid,)
            ).fetchone()
            if not row:
                continue
            detail = f"{row['recommendation']} 处理窗口:{row['operation_window']}"
            priority = '高' if row['risk_level'] == '高' else '中' if row['risk_level'] == '中' else '低'
            cursor = conn.execute(
                """INSERT INTO tasks (title, task_type, plot_name, priority, status, assignee, detail, planned_start, planned_end, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (f"喷药-{row['plot_name']}-{row['risk_type']}", '喷药', row['plot_name'], priority,
                 '待执行', '无人机#001', detail, now, '', now, now)
            )
            task_id = cursor.lastrowid
            conn.execute(
                """INSERT INTO operation_logs (log_type, source, related_task_id, model_name, class_name, confidence, action_summary, payload_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                ('task', 'task_plan', task_id, '任务规划', '喷药', None, f'从风险预警生成: {row["plot_name"]} {row["risk_type"]}',
                 json.dumps({'source': 'risk_alert', 'source_id': rid}, ensure_ascii=False), now)
            )
            created.append({'id': task_id, 'type': '喷药', 'title': f"喷药-{row['plot_name']}-{row['risk_type']}"})

        conn.commit()
        conn.close()
        write_audit_log('task_plan_generate')
        return jsonify({'success': True, 'created': created, 'count': len(created)})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/tasks', methods=['GET', 'POST'])
def task_api():
    """任务编排中心 API"""
    if request.method == 'POST':
        if ROLE_LEVELS.get(get_request_role(), 0) < ROLE_LEVELS['operator']:
            return jsonify({'success': False, 'error': '权限不足，至少需要 operator 角色'}), 403
        data = request.get_json() or {}
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        title = data.get('title', '').strip()
        if not title:
            return jsonify({'success': False, 'error': '任务标题不能为空'}), 400
        task_type = data.get('task_type', '巡检')
        plot_name = data.get('plot_name', 'A区')
        priority = data.get('priority', '中')
        assignee = data.get('assignee', '无人机#001')
        detail = data.get('detail', '')
        planned_start = data.get('planned_start', now)
        planned_end = data.get('planned_end', '')

        conn = get_db_connection()
        cursor = conn.execute(
            """
            INSERT INTO tasks
            (title, task_type, plot_name, priority, status, assignee, detail, planned_start, planned_end, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                title, task_type, plot_name, priority, '待执行', assignee, detail,
                planned_start, planned_end, now, now
            )
        )
        task_id = cursor.lastrowid
        conn.execute(
            """
            INSERT INTO operation_logs
            (log_type, source, related_task_id, model_name, class_name, confidence, action_summary, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                'task', 'task_center', task_id, '调度中心', task_type, None,
                f'任务已创建: {title}',
                json.dumps(data, ensure_ascii=False),
                now
            )
        )
        conn.commit()
        conn.close()
        write_audit_log('create_task')
        return jsonify({'success': True, 'task_id': task_id})

    status = request.args.get('status', type=str, default='')
    conn = get_db_connection()
    if status:
        rows = conn.execute(
            """
            SELECT * FROM tasks WHERE status = ? ORDER BY id DESC
            """,
            (status,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM tasks ORDER BY id DESC").fetchall()
    conn.close()
    data = [dict(row) for row in rows]
    return jsonify({'success': True, 'data': data})

def _refresh_drone_charging(conn):
    """将已过充电时间的无人机从 charging 置为 idle"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn.execute(
        "UPDATE drone_fleet SET status = 'idle', current_task_id = NULL, charging_until = NULL, updated_at = ? WHERE status = 'charging' AND charging_until IS NOT NULL AND charging_until <= ?",
        (now, now)
    )

CHARGING_MINUTES = 8

@app.route('/api/drone_fleet', methods=['GET'])
def drone_fleet_api():
    """获取全部无人机机队（含状态：idle/executing/charging）"""
    try:
        conn = get_db_connection()
        _refresh_drone_charging(conn)
        conn.commit()
        rows = conn.execute(
            "SELECT drone_id, name, status, current_task_id, charging_until, updated_at FROM drone_fleet ORDER BY drone_id"
        ).fetchall()
        conn.close()
        data = []
        for r in rows:
            d = dict(r)
            d['charging_until'] = d.get('charging_until') or ''
            data.append(d)
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/drone_fleet/available', methods=['GET'])
def drone_fleet_available_api():
    """获取可分配无人机（仅 idle 状态）"""
    try:
        conn = get_db_connection()
        _refresh_drone_charging(conn)
        conn.commit()
        rows = conn.execute(
            "SELECT drone_id, name, status FROM drone_fleet WHERE status = 'idle' ORDER BY drone_id"
        ).fetchall()
        conn.close()
        data = [dict(r) for r in rows]
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/tasks/<int:task_id>/assign', methods=['POST'])
def assign_task_api(task_id):
    """分配无人机执行任务"""
    if ROLE_LEVELS.get(get_request_role(), 0) < ROLE_LEVELS['operator']:
        return jsonify({'success': False, 'error': '权限不足'}), 403
    data = request.get_json() or {}
    drone_id = (data.get('drone_id') or '').strip()
    if not drone_id:
        return jsonify({'success': False, 'error': '请指定 drone_id'}), 400
    try:
        conn = get_db_connection()
        _refresh_drone_charging(conn)
        task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not task:
            conn.close()
            return jsonify({'success': False, 'error': '任务不存在'}), 404
        if task['status'] != '待执行':
            conn.close()
            return jsonify({'success': False, 'error': f'任务状态为 {task["status"]}，无法分配'}), 400
        drone = conn.execute("SELECT * FROM drone_fleet WHERE drone_id = ?", (drone_id,)).fetchone()
        if not drone:
            conn.close()
            return jsonify({'success': False, 'error': '无人机不存在'}), 404
        if drone['status'] != 'idle':
            conn.close()
            return jsonify({'success': False, 'error': f'无人机 {drone_id} 当前状态为 {drone["status"]}，无法分配'}), 400
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        conn.execute(
            "UPDATE tasks SET status = '执行中', assignee = ?, updated_at = ? WHERE id = ?",
            (drone_id, now, task_id)
        )
        conn.execute(
            "UPDATE drone_fleet SET status = 'executing', current_task_id = ?, updated_at = ? WHERE drone_id = ?",
            (task_id, now, drone_id)
        )
        conn.execute(
            "INSERT INTO operation_logs (log_type, source, related_task_id, model_name, class_name, confidence, action_summary, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ('task', 'admin', task_id, '任务分配', drone_id, None, f'分配 {drone_id} 执行任务', json.dumps({'drone_id': drone_id}, ensure_ascii=False), now)
        )
        conn.commit()
        conn.close()
        # 清理旧缓存，让下次轮询重新生成最新轨迹
        _dispatched_traj_cache.pop(task_id, None)
        write_audit_log('assign_task')
        return jsonify({'success': True, 'message': f'已分配 {drone_id} 执行任务', 'drone_id': drone_id})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/tasks/batch_assign', methods=['POST'])
def batch_assign_tasks_api():
    """一键分派：将待执行任务批量分配给可用无人机"""
    if ROLE_LEVELS.get(get_request_role(), 0) < ROLE_LEVELS['operator']:
        return jsonify({'success': False, 'error': '权限不足'}), 403
    try:
        conn = get_db_connection()
        _refresh_drone_charging(conn)
        conn.commit()
        pending = conn.execute("SELECT id, title FROM tasks WHERE status = '待执行' ORDER BY id").fetchall()
        available = conn.execute("SELECT drone_id FROM drone_fleet WHERE status = 'idle' ORDER BY drone_id").fetchall()
        pending = [dict(r) for r in pending]
        available = [r['drone_id'] for r in available]
        if len(pending) > len(available):
            conn.close()
            return jsonify({
                'success': False,
                'error': f'待执行任务 {len(pending)} 个，可用无人机仅 {len(available)} 架，不足分配'
            }), 400
        assigned = []
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for i, t in enumerate(pending):
            if i >= len(available):
                break
            drone_id = available[i]
            conn.execute("UPDATE tasks SET status = '执行中', assignee = ?, updated_at = ? WHERE id = ?", (drone_id, now, t['id']))
            conn.execute("UPDATE drone_fleet SET status = 'executing', current_task_id = ?, updated_at = ? WHERE drone_id = ?", (t['id'], now, drone_id))
            conn.execute(
                "INSERT INTO operation_logs (log_type, source, related_task_id, model_name, class_name, confidence, action_summary, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ('task', 'admin', t['id'], '任务分配', drone_id, None, f'分配 {drone_id} 执行任务', json.dumps({'drone_id': drone_id}, ensure_ascii=False), now)
            )
            assigned.append({'task_id': t['id'], 'title': t['title'], 'drone_id': drone_id})
        conn.commit()
        conn.close()
        write_audit_log('batch_assign_task')
        return jsonify({'success': True, 'assigned': assigned, 'count': len(assigned)})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/tasks/<int:task_id>/status', methods=['POST'])
def update_task_status(task_id):
    """任务状态回传（无人机执行联动）"""
    if ROLE_LEVELS.get(get_request_role(), 0) < ROLE_LEVELS['operator']:
        return jsonify({'success': False, 'error': '权限不足，至少需要 operator 角色'}), 403
    data = request.get_json() or {}
    status = data.get('status', '').strip()
    valid_status = {'待执行', '执行中', '已完成', '失败', '已暂停'}
    if status not in valid_status:
        return jsonify({'success': False, 'error': f'非法状态: {status}'}), 400

    event = data.get('event', '')
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = get_db_connection()
    task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not task:
        conn.close()
        return jsonify({'success': False, 'error': '任务不存在'}), 404

    conn.execute(
        "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
        (status, now, task_id)
    )
    # 若任务完成，释放无人机并进入充电（sqlite3.Row 用索引访问，无 .get）
    assignee_val = (task['assignee'] or '') if task else ''
    if status == '已完成' and assignee_val and assignee_val.startswith('UAV-'):
        charging_until = (datetime.now() + timedelta(minutes=CHARGING_MINUTES)).strftime('%Y-%m-%d %H:%M:%S')
        conn.execute(
            "UPDATE drone_fleet SET status = 'charging', current_task_id = NULL, charging_until = ?, updated_at = ? WHERE drone_id = ?",
            (charging_until, now, assignee_val)
        )
    elif status in ('已完成', '失败', '已暂停') and assignee_val and assignee_val.startswith('UAV-'):
        conn.execute(
            "UPDATE drone_fleet SET status = 'idle', current_task_id = NULL, charging_until = NULL, updated_at = ? WHERE drone_id = ?",
            (now, assignee_val)
        )
    conn.execute(
        """
        INSERT INTO operation_logs
        (log_type, source, related_task_id, model_name, class_name, confidence, action_summary, payload_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            'execution', 'uav_console', task_id, '无人机控制台', task['task_type'], None,
            event or f'任务状态更新为 {status}',
            json.dumps({'status': status, 'event': event}, ensure_ascii=False),
            now
        )
    )
    conn.commit()
    conn.close()
    # 任务结束时清理轨迹缓存，避免缓存无效数据
    if status in ('已完成', '失败', '已暂停'):
        _dispatched_traj_cache.pop(task_id, None)
    write_audit_log('update_task_status')
    return jsonify({'success': True, 'message': '任务状态更新成功'})

@app.route('/api/yield_forecast', methods=['GET'])
@require_role('agronomist')
def yield_forecast():
    """产量预测与采收建议"""
    base_yield = request.args.get('base_yield', type=float, default=1800.0)
    area_mu = request.args.get('area_mu', type=float, default=12.0)
    maturity_score = request.args.get('maturity_score', type=float, default=0.78)
    weather_risk = request.args.get('weather_risk', type=float, default=0.25)

    forecast_total = round(base_yield * area_mu * (0.9 + maturity_score * 0.2) * (1.0 - weather_risk * 0.12), 2)
    suggested_harvest_days = 2 if maturity_score > 0.75 else 4
    recommendation = f"建议在 {suggested_harvest_days} 天内完成第一批采收，并优先处理成熟度较高地块。"

    write_audit_log('view_yield_forecast')
    return jsonify({
        'success': True,
        'data': {
            'forecast_total_kg': forecast_total,
            'harvest_window_days': suggested_harvest_days,
            'maturity_score': maturity_score,
            'weather_risk': weather_risk,
            'recommendation': recommendation
        }
    })

@app.route('/api/business_metrics', methods=['GET'])
@require_role('agronomist')
def business_metrics():
    """经营驾驶舱指标"""
    conn = get_db_connection()
    recog_total = conn.execute("SELECT COUNT(*) AS c FROM operation_logs WHERE log_type = 'recognition'").fetchone()['c']
    alert_total = conn.execute("SELECT COUNT(*) AS c FROM risk_alerts").fetchone()['c']
    task_total = conn.execute("SELECT COUNT(*) AS c FROM tasks").fetchone()['c']
    done_tasks = conn.execute("SELECT COUNT(*) AS c FROM tasks WHERE status = '已完成'").fetchone()['c']
    orchard_mission_total = conn.execute("SELECT COUNT(*) AS c FROM orchard_missions").fetchone()['c']
    orchard_mission_done = conn.execute("SELECT COUNT(*) AS c FROM orchard_missions WHERE status = 'completed'").fetchone()['c']
    orchard_telemetry_total = conn.execute("SELECT COUNT(*) AS c FROM orchard_telemetry").fetchone()['c']
    online_devices = 1 if virtual_camera_running else 0
    with orchard_lock:
        orchard_online = sum(1 for d in orchard_state['drones'] if d.get('status') == '执行中')
        orchard_device_total = max(1, len(orchard_config.get('drones', [])))
    online_devices += orchard_online
    conn.close()

    cost_per_mu = round(320 - min(80, done_tasks * 2.5), 2)
    roi_estimate = round(1.15 + min(0.55, (recog_total + alert_total + orchard_mission_done) * 0.002), 2)
    write_audit_log('view_business_metrics')
    return jsonify({
        'success': True,
        'data': {
            'recognition_total': recog_total,
            'risk_alert_total': alert_total,
            'task_total': task_total,
            'task_done_rate': round((done_tasks / task_total) * 100, 2) if task_total else 0.0,
            'online_devices': online_devices,
            'device_total': orchard_device_total + 1,
            'orchard_mission_total': orchard_mission_total,
            'orchard_mission_done_rate': round((orchard_mission_done / orchard_mission_total) * 100, 2) if orchard_mission_total else 0.0,
            'orchard_telemetry_total': orchard_telemetry_total,
            'cost_per_mu': cost_per_mu,
            'roi_estimate': roi_estimate
        }
    })

@app.route('/api/audit_logs', methods=['GET'])
@require_role('admin')
def get_audit_logs():
    limit = request.args.get('limit', type=int, default=50)
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return jsonify({'success': True, 'data': [dict(row) for row in rows]})

@app.route('/api/open/health', methods=['GET'])
def open_health():
    return jsonify({
        'success': True,
        'service': 'smart-agri-platform',
        'version': '1.0.0',
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

@app.route('/api/open/plots', methods=['GET'])
def open_plots():
    return jsonify({
        'success': True,
        'data': [
            {'plot_name': 'A区', 'crop_type': '苹果', 'area_mu': 12.0},
            {'plot_name': 'B区', 'crop_type': '梨', 'area_mu': 9.5},
            {'plot_name': 'C区', 'crop_type': '番茄', 'area_mu': 6.8}
        ]
    })

# ==================== WebSocket 视频流事件处理 ====================

@socketio.on('orchard_subscribe')
def handle_orchard_subscribe():
    """果园地图页面订阅实时状态"""
    emit('orchard_state', {'success': True, 'data': orchard_snapshot()})


@socketio.on('pc_connect')
def handle_pc_connect():
    """电脑端连接事件"""
    print(f'[WebSocket] 电脑端已连接，Session ID: {request.sid}', flush=True)
    video_stream_data['clients'].add(request.sid)
    print(f'[WebSocket] 当前已注册客户端数量: {len(video_stream_data["clients"])}', flush=True)
    emit('pc_connected', {'status': 'success'})
    
    # 如果已有视频流，立即发送最新帧
    if video_stream_data['frame']:
        print('[WebSocket] 向电脑端发送已有视频流', flush=True)
        emit('video_stream', {
            'frame': video_stream_data['frame'],
            'timestamp': video_stream_data['timestamp']
        })

@socketio.on('disconnect')
def handle_disconnect():
    """客户端断开连接"""
    if request.sid in video_stream_data['clients']:
        video_stream_data['clients'].discard(request.sid)
    print(f'[WebSocket] 客户端已断开: {request.sid}')

if __name__ == '__main__':
    local_url = print_startup_banner(DEFAULT_HOST, DEFAULT_PORT)
    if AUTO_OPEN_BROWSER:
        open_browser_async(local_url)
    
    # 使用socketio.run启动，支持WebSocket
    # host='0.0.0.0' 允许手机通过局域网访问
    # 关闭debug和reloader避免与WebSocket冲突
    # 注意：关闭debug后代码修改不会自动重启，需要手动重启
    try:
        debug_flag = os.getenv('APP_DEBUG', '0') == '1'
        reload_flag = os.getenv('APP_RELOAD', '0') == '1'
        socketio.run(
            app, 
            debug=debug_flag,  # APP_DEBUG=1 开启调试
            host=DEFAULT_HOST, 
            port=DEFAULT_PORT, 
            allow_unsafe_werkzeug=True,
            use_reloader=reload_flag,  # APP_RELOAD=1 启用自动重启（开发用）
            log_output=debug_flag  # 调试时输出日志
        )
    except Exception as e:
        print(f"启动错误: {e}")
        print("尝试使用标准Flask启动方式...")
        app.run(host=DEFAULT_HOST, port=DEFAULT_PORT, debug=False)

