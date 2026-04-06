// 页面标题映射
const ADMIN_PAGE_TITLES = {
    dashboard: '系统概览',
    irrigation: '灌溉建议',
    risk: '风险预警',
    mission: '无人机调度',
    task: '任务列表',
    history: '识别历史',
    devices: '设备管理',
    settings: '系统设置'
};

function switchPage(page) {
    // 移除所有活动状态，激活当前项
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
        if (item.dataset.page === page) item.classList.add('active');
    });

    // 隐藏所有页面内容
    document.querySelectorAll('.admin-content').forEach(content => {
        content.classList.remove('active');
    });

    // 更新顶栏标题
    const titleEl = document.getElementById('adminPageTitle');
    const breadEl = document.getElementById('adminBreadcrumb');
    if (titleEl) titleEl.textContent = ADMIN_PAGE_TITLES[page] || '系统概览';
    if (breadEl) breadEl.textContent = 'Admin / ' + (ADMIN_PAGE_TITLES[page] || page);

    // 查找并显示目标页面
    const pageId = page + 'Page';
    const targetPage = document.getElementById(pageId);

    if (targetPage) {
        targetPage.classList.add('active');

        if (page === 'history') {
            setTimeout(() => loadAdminHistory(), 100);
        } else if (page === 'dashboard') {
            setTimeout(() => loadAdminDashboard(), 100);
        } else if (page === 'irrigation') {
            setTimeout(() => loadAdminIrrigation(), 100);
        } else if (page === 'risk') {
            setTimeout(() => loadAdminRisk(), 100);
        } else if (page === 'mission') {
            setTimeout(() => loadAdminMission(), 100);
        } else if (page === 'task') {
            setTimeout(() => loadAdminTask(), 100);
        }
    } else {
        // 如果页面未定义，显示开发中提示
        const main = document.querySelector('.main-container');
        let newPage = document.createElement('div');
        newPage.id = pageId;
        newPage.className = 'admin-content active';
        newPage.innerHTML = `
            <div class="content-panel-glass" style="margin-top:20px; text-align:center; padding:100px; animation: fadeInUp 0.5s ease-out;">
                <div style="font-size:5rem; filter: drop-shadow(0 0 20px var(--primary));">🚧</div>
                <h2 style="color:var(--primary); margin-top:30px; font-size: 2rem; font-weight: 900;">${page.toUpperCase()} 智能模块对接中</h2>
                <p style="color:var(--text-dim); font-size: 1.1rem; margin-top: 15px;">该模块正在接入实时 AI 数据流，预计下个版本同步...</p>
                <button onclick="switchPage('dashboard')" class="btn-logout-minimal" style="margin-top: 40px; padding: 12px 30px;">返回控制面板</button>
            </div>
        `;
        main.appendChild(newPage);
    }
}

// 初始化模拟图表
function initChart() {
    const canvas = document.getElementById('accuracyChart');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const width = canvas.parentElement.offsetWidth;
    const height = canvas.parentElement.offsetHeight;

    canvas.width = width;
    canvas.height = height;

    const points = [85, 88, 86, 92, 90, 94, 96];
    const step = width / (points.length - 1);

    // 绘制渐变背景
    const gradient = ctx.createLinearGradient(0, 0, 0, height);
    gradient.addColorStop(0, 'rgba(0, 255, 157, 0.2)');
    gradient.addColorStop(1, 'rgba(0, 255, 157, 0)');

    ctx.beginPath();
    ctx.moveTo(0, height);
    points.forEach((p, i) => {
        const x = i * step;
        const y = height - (p / 100 * height * 0.7);
        ctx.lineTo(x, y);
    });
    ctx.lineTo(width, height);
    ctx.fillStyle = gradient;
    ctx.fill();

    // 绘制折线
    ctx.beginPath();
    ctx.moveTo(0, height - (points[0] / 100 * height * 0.7));
    points.forEach((p, i) => {
        const x = i * step;
        const y = height - (p / 100 * height * 0.7);
        ctx.lineTo(x, y);

        // 绘制发光点
        ctx.save();
        ctx.shadowBlur = 15;
        ctx.shadowColor = '#00ff9d';
        ctx.fillStyle = '#fff';
        ctx.beginPath();
        ctx.arc(x, y, 5, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
    });
    ctx.strokeStyle = '#00ff9d';
    ctx.lineWidth = 4;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.stroke();

    // 绘制辅助线
    ctx.strokeStyle = 'rgba(255,255,255,0.05)';
    ctx.lineWidth = 1;
    for (let i = 1; i < 5; i++) {
        const y = height - (i * 20 / 100 * height * 0.7);
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
        ctx.stroke();
    }
}

// 加载后台管理面板聚合数据（灌溉、风险预警、无人机任务等）
function loadAdminDashboard() {
    fetch('/api/admin/dashboard')
        .then(r => r.json())
        .then(data => {
            if (!data.success) {
                console.error('Dashboard load failed:', data.error);
                return;
            }
            const d = data.data || {};
            const m = d.metrics || {};

            // 指标卡片
            const setMetric = (id, val) => {
                const el = document.getElementById(id);
                if (el) el.textContent = val ?? '0';
            };
            setMetric('metricIrrigation', m.irrigation_total);
            setMetric('metricRisk', m.risk_alert_total);
            setMetric('metricTaskPending', m.task_pending);
            setMetric('metricTaskTotal', m.task_total ? `共 ${m.task_total} 项` : '共 0 项');
            setMetric('metricMission', m.mission_total);

            // 实时动态时间线
            const timeline = document.getElementById('adminTaskTimeline');
            if (timeline) {
                const ops = d.recent_operations || [];
                if (ops.length === 0) {
                    timeline.innerHTML = '<div style="text-align:center; padding:40px; color:var(--text-dim);">暂无数据，请到灌溉、病虫害、果园地图等页面生成数据</div>';
                } else {
                    timeline.innerHTML = ops.map(o => `
                        <div class="timeline-item">
                            <div class="time">${o.time || '-'}</div>
                            <div class="content">
                                <div class="title">${o.title || o.action_summary || '-'}</div>
                                <div class="desc">${o.source || ''} · ${o.created_at || ''}</div>
                            </div>
                            <div class="status success"></div>
                        </div>
                    `).join('');
                }
            }
        })
        .catch(err => {
            console.error('Dashboard load error:', err);
            const timeline = document.getElementById('adminTaskTimeline');
            if (timeline) timeline.innerHTML = '<div style="text-align:center; padding:40px; color:var(--warning);">加载失败，请刷新重试</div>';
        });
}

// 灌溉建议页数据
function loadAdminIrrigation() {
    const el = document.getElementById('adminIrrigationList');
    if (!el) return;
    el.innerHTML = '<div style="text-align:center; padding:40px; color:var(--text-dim);">正在加载...</div>';
    fetch('/api/admin/dashboard')
        .then(r => r.json())
        .then(data => {
            const list = (data.success && data.data) ? data.data.recent_irrigation || [] : [];
            if (list.length === 0) {
                el.innerHTML = '<div style="text-align:center; padding:40px; color:var(--text-dim);">暂无数据，请到 <a href="/灌溉" style="color:var(--primary);">智能灌溉</a> 生成建议</div>';
            } else {
                el.innerHTML = list.map(i => `
                    <div class="detail-item" style="padding: 20px; background: rgba(255,255,255,0.02); border-radius: 15px; margin-bottom: 15px;">
                        <div style="display: flex; align-items: center; gap: 20px;">
                            <div style="font-size: 2rem;">💧</div>
                            <div style="flex: 1;">
                                <div style="font-weight: 800; color: #fff;">${i.plot_name || '-'} · ${i.crop_type || ''} · ${i.priority || ''}优先级</div>
                                <div style="font-size: 0.85rem; color: var(--text-dim); margin-top: 4px;">${i.suggested_water_lpm} L/min · ${i.suggested_duration_min} 分钟</div>
                                <div style="font-size: 0.85rem; color: var(--text-dim); margin-top: 4px;">${i.created_at}</div>
                            </div>
                        </div>
                    </div>
                `).join('');
            }
        })
        .catch(() => { el.innerHTML = '<div style="text-align:center; padding:40px; color:var(--warning);">加载失败</div>'; });
}

// 风险预警页数据
function loadAdminRisk() {
    const el = document.getElementById('adminRiskList');
    if (!el) return;
    el.innerHTML = '<div style="text-align:center; padding:40px; color:var(--text-dim);">正在加载...</div>';
    fetch('/api/admin/dashboard')
        .then(r => r.json())
        .then(data => {
            const list = (data.success && data.data) ? data.data.recent_risk_alerts || [] : [];
            if (list.length === 0) {
                el.innerHTML = '<div style="text-align:center; padding:40px; color:var(--text-dim);">暂无数据，请到 <a href="/病虫害" style="color:var(--primary);">病虫害</a> 生成预警</div>';
            } else {
                el.innerHTML = list.map(r => `
                    <div class="detail-item" style="padding: 20px; background: rgba(255,255,255,0.02); border-radius: 15px; margin-bottom: 15px;">
                        <div style="display: flex; align-items: center; gap: 20px;">
                            <div style="font-size: 2rem;">🛡️</div>
                            <div style="flex: 1;">
                                <div style="font-weight: 800; color: #fff;">${r.plot_name || '-'} · ${r.risk_type || ''} · ${r.risk_level || ''}</div>
                                <div style="font-size: 0.85rem; color: var(--text-dim); margin-top: 4px;">发生概率 ${(r.probability * 100 || 0).toFixed(0)}% · ${r.created_at}</div>
                                <div style="font-size: 0.85rem; color: var(--text-dim); margin-top: 4px;">${r.recommendation || ''}</div>
                            </div>
                        </div>
                    </div>
                `).join('');
            }
        })
        .catch(() => { el.innerHTML = '<div style="text-align:center; padding:40px; color:var(--warning);">加载失败</div>'; });
}

// 无人机调度页数据
function loadAdminMission() {
    const el = document.getElementById('adminMissionList');
    if (!el) return;
    el.innerHTML = '<div style="text-align:center; padding:40px; color:var(--text-dim);">正在加载...</div>';
    fetch('/api/admin/dashboard')
        .then(r => r.json())
        .then(data => {
            const list = (data.success && data.data) ? data.data.recent_missions || [] : [];
            if (list.length === 0) {
                el.innerHTML = '<div style="text-align:center; padding:40px; color:var(--text-dim);">暂无数据，请到 <a href="/果园地图" style="color:var(--primary);">果园地图</a> 生成调度</div>';
            } else {
                el.innerHTML = list.map(m => `
                    <div class="detail-item" style="padding: 20px; background: rgba(255,255,255,0.02); border-radius: 15px; margin-bottom: 15px;">
                        <div style="display: flex; align-items: center; gap: 20px;">
                            <div style="font-size: 2rem;">🛸</div>
                            <div style="flex: 1;">
                                <div style="font-weight: 800; color: #fff;">${m.mission_name || '-'} · ${m.status || ''}</div>
                                <div style="font-size: 0.85rem; color: var(--text-dim); margin-top: 4px;">得分 ${m.score_total ?? '-'} · ${m.created_at}</div>
                            </div>
                        </div>
                    </div>
                `).join('');
            }
        })
        .catch(() => { el.innerHTML = '<div style="text-align:center; padding:40px; color:var(--warning);">加载失败</div>'; });
}

// 任务列表页：加载无人机状态摘要
function loadAdminDroneStatus() {
    const el = document.getElementById('adminDroneStatus');
    if (!el) return;
    fetch('/api/drone_fleet')
        .then(r => r.json())
        .then(res => {
            if (!res.success || !res.data) return;
            const list = res.data;
            const idle = list.filter(d => d.status === 'idle').length;
            const executing = list.filter(d => d.status === 'executing').length;
            const charging = list.filter(d => d.status === 'charging').length;
            el.textContent = `空闲 ${idle} | 执行中 ${executing} | 充电 ${charging}`;
        })
        .catch(() => { });
}

// 任务列表页数据（使用 /api/tasks 获取完整任务列表）
function loadAdminTask() {
    loadAdminDroneStatus();
    const el = document.getElementById('adminTaskList');
    if (!el) return;
    el.innerHTML = '<div style="text-align:center; padding:40px; color:var(--text-dim);">正在加载...</div>';
    fetch('/api/tasks')
        .then(r => r.json())
        .then(data => {
            const list = (data.success && data.data) ? data.data : [];
            if (list.length === 0) {
                el.innerHTML = '<div style="text-align:center; padding:40px; color:var(--text-dim);">暂无数据，请到 <a href="/任务规划" style="color:var(--primary);">任务规划</a> 创建</div>';
            } else {
                el.innerHTML = list.map(t => {
                    const isPending = t.status === '待执行';
                    const isExecuting = t.status === '执行中';
                    const isDone = t.status === '已完成';
                    let assignBtn = '';
                    if (isPending) {
                        assignBtn = `<button class="btn-modal btn-modal-primary" style="padding: 6px 16px; font-size: 0.85rem;" data-assign-task-id="${t.id}" data-assign-task-title="${(t.title || '').replace(/"/g, '&quot;')}">分配无人机</button>`;
                    } else if (isExecuting) {
                        assignBtn = `<span class="data-badge" style="background: rgba(0,255,157,0.15); color: var(--primary); margin-right:8px;">🚁 ${t.assignee || ''}</span><button class="btn-modal btn-modal-secondary" style="padding: 6px 12px; font-size: 0.8rem;" data-complete-task-id="${t.id}">标记完成</button>`;
                    }
                    const doneStyle = isDone ? 'opacity: 0.6; text-decoration: line-through;' : '';
                    return `
                    <div class="detail-item" style="padding: 20px; background: rgba(255,255,255,0.02); border-radius: 15px; margin-bottom: 15px; display: flex; align-items: center; gap: 20px; ${doneStyle}">
                        <div style="font-size: 2rem;">🗂️</div>
                        <div style="flex: 1;">
                            <div style="font-weight: 800; color: #fff;">${t.title || '-'} · ${t.status || ''}</div>
                            <div style="font-size: 0.85rem; color: var(--text-dim); margin-top: 4px;">${t.assignee || '-'} · ${t.task_type || ''} · ${t.created_at || ''}</div>
                        </div>
                        <div>${assignBtn}</div>
                    </div>`;
                }).join('');
                el.querySelectorAll('[data-assign-task-id]').forEach(btn => {
                    btn.addEventListener('click', () => showAssignModal(parseInt(btn.dataset.assignTaskId), btn.dataset.assignTaskTitle));
                });
                el.querySelectorAll('[data-complete-task-id]').forEach(btn => {
                    btn.addEventListener('click', () => completeTask(parseInt(btn.dataset.completeTaskId)));
                });
            }
        })
        .catch(() => { el.innerHTML = '<div style="text-align:center; padding:40px; color:var(--warning);">加载失败</div>'; });
}

function showAssignModal(taskId, taskTitle) {
    fetch('/api/drone_fleet/available')
        .then(r => r.json())
        .then(res => {
            const drones = (res.success && res.data) ? res.data : [];
            if (drones.length === 0) {
                showAdminAlert('无可用无人机', '当前没有空闲无人机，请等待充电或任务完成。');
                return;
            }
            let overlay = document.getElementById('adminAssignModalOverlay');
            if (!overlay) {
                overlay = document.createElement('div');
                overlay.id = 'adminAssignModalOverlay';
                overlay.className = 'custom-modal-overlay';
                document.body.appendChild(overlay);
            }
            overlay.innerHTML = `
                <div class="custom-modal-card" style="max-width: 420px;">
                    <div class="custom-modal-title"><span>🚁</span> 分配无人机</div>
                    <div class="custom-modal-content">
                        <p style="margin-bottom: 12px;">任务：${(taskTitle || '').replace(/</g, '&lt;')}</p>
                        <p style="margin-bottom: 8px; font-size: 0.9rem;">可选无人机（空闲）：</p>
                        <div id="adminDroneList" style="max-height: 200px; overflow-y: auto; display: flex; flex-direction: column; gap: 8px;"></div>
                    </div>
                    <div class="custom-modal-actions">
                        <button class="btn-modal btn-modal-secondary" id="adminAssignCancel">取消</button>
                    </div>
                </div>`;
            const listEl = overlay.querySelector('#adminDroneList');
            drones.forEach(d => {
                const btn = document.createElement('button');
                btn.className = 'btn-modal btn-modal-primary';
                btn.style.cssText = 'padding: 10px 16px; text-align: left; width: 100%;';
                btn.textContent = `${d.drone_id} · ${d.name}`;
                btn.onclick = () => doAssign(taskId, d.drone_id, overlay);
                listEl.appendChild(btn);
            });
            overlay.classList.add('active');
            overlay.querySelector('#adminAssignCancel').onclick = () => overlay.classList.remove('active');
        })
        .catch(() => showAdminAlert('加载失败', '获取可用无人机失败'));
}

function completeTask(taskId) {
    fetch(`/api/tasks/${taskId}/status`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-User-Role': 'admin' },
        body: JSON.stringify({ status: '已完成', event: '管理员手动标记完成' })
    })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                loadAdminTask();
                showAdminAlert('已完成', '任务已标记完成，无人机将进入充电状态（约 8 分钟）');
            } else {
                showAdminAlert('操作失败', data.error || '未知错误');
            }
        })
        .catch(() => showAdminAlert('请求失败', '网络错误'));
}

function doAssign(taskId, droneId, overlay) {
    if (overlay) overlay.classList.remove('active');
    fetch(`/api/tasks/${taskId}/assign`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-User-Role': 'admin' },
        body: JSON.stringify({ drone_id: droneId })
    })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                loadAdminTask();
                showAdminConfirm('分配成功', `已分配 ${droneId} 执行任务，是否前往果园地图查看飞行轨迹？`, '前往地图', '留在此页')
                    .then(go => { if (go) window.location.href = '/果园地图'; });
            } else {
                showAdminAlert('分配失败', data.error || '未知错误');
            }
        })
        .catch(() => showAdminAlert('请求失败', '网络错误'));
}

function showAdminAlert(title, content) {
    let overlay = document.getElementById('adminModalOverlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'adminModalOverlay';
        overlay.className = 'custom-modal-overlay';
        document.body.appendChild(overlay);
    }
    overlay.innerHTML = `
        <div class="custom-modal-card">
            <div class="custom-modal-title"><span>🔔</span> ${title}</div>
            <div class="custom-modal-content">${content}</div>
            <div class="custom-modal-actions">
                <button class="btn-modal btn-modal-primary" id="adminModalOk">确定</button>
            </div>
        </div>`;
    overlay.classList.add('active');
    overlay.querySelector('#adminModalOk').onclick = () => overlay.classList.remove('active');
}

function showAdminConfirm(title, content, okText, cancelText) {
    return new Promise(resolve => {
        let overlay = document.getElementById('adminModalOverlay');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'adminModalOverlay';
            overlay.className = 'custom-modal-overlay';
            document.body.appendChild(overlay);
        }
        overlay.innerHTML = `
            <div class="custom-modal-card">
                <div class="custom-modal-title"><span>❓</span> ${title}</div>
                <div class="custom-modal-content">${content}</div>
                <div class="custom-modal-actions">
                    <button class="btn-modal btn-modal-secondary" id="adminModalCancel">${cancelText || '取消'}</button>
                    <button class="btn-modal btn-modal-primary" id="adminModalOk">${okText || '确定'}</button>
                </div>
            </div>`;
        overlay.classList.add('active');
        overlay.querySelector('#adminModalCancel').onclick = () => { overlay.classList.remove('active'); resolve(false); };
        overlay.querySelector('#adminModalOk').onclick = () => { overlay.classList.remove('active'); resolve(true); };
    });
}

// 一键分派
document.getElementById('btnBatchAssign')?.addEventListener('click', function () {
    const btn = this;
    btn.disabled = true;
    btn.textContent = '分派中...';
    fetch('/api/tasks/batch_assign', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-User-Role': 'admin' }
    })
        .then(r => r.json())
        .then(data => {
            btn.disabled = false;
            btn.textContent = '一键分派';
            if (data.success) {
                loadAdminTask();
                const count = data.count || 0;
                if (count > 0) {
                    showAdminConfirm('分派完成', `已分派 ${count} 个任务，是否前往果园地图查看飞行轨迹？`, '前往地图', '留在此页')
                        .then(go => { if (go) window.location.href = '/果园地图'; });
                } else {
                    showAdminAlert('提示', '没有待执行任务需要分派');
                }
            } else {
                showAdminAlert('分派失败', data.error || '未知错误');
            }
        })
        .catch(() => {
            btn.disabled = false;
            btn.textContent = '一键分派';
            showAdminAlert('请求失败', '网络错误');
        });
});

document.addEventListener('DOMContentLoaded', () => {
    initChart();
    loadAdminDashboard();

    // 支持 hash 跳转：/admin#task 直接打开任务列表
    const hash = (window.location.hash || '').replace(/^#/, '');
    if (hash && ['dashboard', 'irrigation', 'risk', 'mission', 'task', 'history', 'devices', 'settings'].includes(hash)) {
        switchPage(hash);
    }

    // 窗口调整大小时重绘图表
    window.addEventListener('resize', () => {
        initChart();
    });

    // 磁性交互重构版
    const metricCards = document.querySelectorAll('.metric-glass-card');
    metricCards.forEach(card => {
        card.addEventListener('mousemove', (e) => {
            const rect = card.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;

            const xc = ((x - rect.width / 2) / (rect.width / 2));
            const yc = ((y - rect.height / 2) / (rect.height / 2));

            const maxRotation = 4; // 限制旋转，更显高级
            const rotateY = xc * maxRotation;
            const rotateX = -yc * maxRotation;

            card.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateY(-10px)`;
            card.style.borderColor = 'var(--primary)';
        });

        card.addEventListener('mouseleave', () => {
            card.style.transform = 'perspective(1000px) rotateX(0) rotateY(0) translateY(0)';
            card.style.borderColor = 'var(--glass-border)';
        });
    });
});

// 历史记录相关功能（完全套用移动端逻辑）
function refreshAdminHistory() {
    loadAdminHistory();
}

function loadAdminHistory() {
    const historyList = document.getElementById('adminHistoryList');
    if (!historyList) return;

    // 显示加载状态
    historyList.innerHTML = '<div style="text-align: center; padding: 40px; color: var(--text-dim);">正在加载历史记录...</div>';

    fetch('/api/recognition_history?limit=50&offset=0')
        .then(response => response.json())
        .then(data => {
            if (data.success && data.data.length > 0) {
                historyList.innerHTML = '';
                data.data.forEach(item => {
                    const historyItem = createAdminHistoryItem(item);
                    historyList.appendChild(historyItem);
                });

                // 更新底部提示
                const bottomText = document.getElementById('adminHistoryBottomText');
                if (bottomText) {
                    bottomText.textContent = `--- 已加载 ${data.data.length} 条历史记录 ---`;
                }
            } else {
                historyList.innerHTML = '<div style="text-align: center; padding: 40px; color: var(--text-dim);">暂无历史记录</div>';
            }
        })
        .catch(error => {
            historyList.innerHTML = `<div style="text-align: center; padding: 40px; color: var(--warning);">加载失败: ${error.message}</div>`;
            console.error('加载历史记录失败:', error);
        });
}

// 创建历史记录项（完全套用移动端样式）
function createAdminHistoryItem(item) {
    const div = document.createElement('div');
    div.className = 'detail-item';
    div.style.cssText = 'padding: 20px; background: rgba(255,255,255,0.02); border-radius: 15px; margin-bottom: 15px; cursor: pointer; transition: all 0.3s;';

    // 悬停效果（与移动端一致）
    div.addEventListener('mouseenter', () => {
        div.style.background = 'rgba(255,255,255,0.05)';
        div.style.transform = 'translateX(5px)';
    });
    div.addEventListener('mouseleave', () => {
        div.style.background = 'rgba(255,255,255,0.02)';
        div.style.transform = 'translateX(0)';
    });

    // 获取类别图标和标题（与移动端逻辑完全一致）
    const { icon, title } = getAdminHistoryItemInfo(item);

    // 格式化置信度显示（与移动端一致）
    const confidenceText = item.confidence ? `${item.class_name} (${item.confidence}%)` : item.class_name;

    // 使用与移动端完全相同的HTML结构
    div.innerHTML = `
        <div style="display: flex; align-items: center; gap: 20px; width: 100%;">
            <div style="font-size: 2rem;">${icon}</div>
            <div style="flex: 1;">
                <div style="font-weight: 800; color: #fff;">${title}</div>
                <div style="font-size: 0.85rem; color: var(--text-dim); margin-top: 4px;">${item.timestamp}</div>
            </div>
            <div style="text-align: right;">
                <div style="color: var(--primary); font-weight: 800;">${confidenceText}</div>
                <div style="font-size: 0.8rem; color: var(--accent); margin-top: 4px;">查看详情 ></div>
            </div>
        </div>
    `;

    // 点击查看详情
    div.addEventListener('click', () => {
        console.log('查看详情:', item);
    });

    return div;
}

// 获取历史记录项的图标和标题（与移动端逻辑完全一致）
function getAdminHistoryItemInfo(item) {
    const modelName = item.model_name || '';
    const className = item.class_name || '';

    // 根据模型名称和类别判断（与移动端完全一致）
    if (modelName.includes('成熟度') || modelName.includes('maturity')) {
        return {
            icon: '🍎',
            title: '成熟度评估'
        };
    } else if (modelName.includes('识别') || modelName.includes('classification')) {
        return {
            icon: '🌾',
            title: '作物识别'
        };
    } else {
        // 根据类别判断图标（与移动端完全一致）
        const iconMap = {
            'Apple': '🍎',
            'Banana': '🍌',
            'Orange': '🍊',
            '成熟': '✅',
            '未成熟': '⏳',
            '过熟': '⚠️'
        };
        return {
            icon: iconMap[className] || '🌾',
            title: modelName || '识别记录'
        };
    }
}

function getClassIcon(className) {
    const iconMap = {
        'Apple': '🍎',
        'Banana': '🍌',
        'Orange': '🍊',
        '成熟': '✅',
        '未成熟': '⏳',
        '过熟': '⚠️'
    };
    return iconMap[className] || '🌾';
}

