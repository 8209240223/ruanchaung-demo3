// 数据可视化大屏JavaScript - 实时无人机数据联动
function updateTime() {
    const now = new Date();
    const timeStr = now.toLocaleString('zh-CN');
    const timeElement = document.getElementById('currentTime');
    if (timeElement) timeElement.textContent = timeStr;
}
updateTime();
setInterval(updateTime, 1000);

// 加载并更新大屏指标
function loadDashboardMetrics() {
    fetch('/api/dashboard/data')
        .then(r => r.json())
        .then(data => {
            if (!data.success || !data.data) return;
            const d = data.data;
            const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v ?? '0'; };
            set('metricRecognition', d.recognition_total);
            set('warningHigh', d.risk_high);
            set('warningMedium', d.risk_medium);
            set('warningLow', d.risk_low);
            set('metricDevices', d.device_total);
            set('deviceOnline', d.online_devices);
            set('deviceOffline', d.offline_devices);
            set('statRecognition', d.recognition_total);
            set('statTelemetry', d.telemetry_total);
            set('statOnline', `${d.online_devices || 0}/${d.device_total || 0}`);
        })
        .catch(() => { });
}

// 加载初始日志
function loadInitialLogs() {
    fetch('/api/dashboard/recent_logs?limit=15')
        .then(r => r.json())
        .then(data => {
            if (!data.success || !data.data || !data.data.length) {
                addLogEntry('智慧农业监测中心已启动');
                addLogEntry('等待无人机数据接入，请到果园地图生成调度');
                return;
            }
            data.data.reverse().forEach(log => {
                addLogEntry(log.message, log.time);
            });
        })
        .catch(() => {
            addLogEntry('智慧农业监测中心已启动');
        });
}

// 初始化饼图 (优化版：标签直接绘制在图上，字体更大)
function initPieChart() {
    const canvas = document.getElementById('cropPieChart');
    if (!canvas) return;

    // 设置画布分辨率（提高清晰度）
    const dpr = window.devicePixelRatio || 1;
    const container = canvas.parentElement;
    const displayWidth = container.offsetWidth || 500;
    const displayHeight = container.offsetHeight || 500;

    canvas.width = displayWidth * dpr;
    canvas.height = displayHeight * dpr;
    canvas.style.width = displayWidth + 'px';
    canvas.style.height = displayHeight + 'px';

    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);

    const centerX = displayWidth / 2;
    const centerY = displayHeight / 2;
    const radius = Math.min(displayWidth, displayHeight) * 0.35;
    const innerRadius = radius * 0.6; // 环形图

    const data = [
        { label: '苹果', value: 35, color: '#00ff9d' }, // 霓虹绿
        { label: '梨', value: 25, color: '#00d2ff' },   // 电光蓝
        { label: '番茄', value: 20, color: '#ff3e3e' }, // 鲜红
        { label: '其他', value: 20, color: '#bd00ff' }  // 亮紫
    ];

    let currentAngle = -Math.PI / 2;

    // 绘制饼图扇形
    data.forEach((item, index) => {
        const sliceAngle = (item.value / 100) * 2 * Math.PI;
        const midAngle = currentAngle + sliceAngle / 2;

        // 绘制外环扇形
        ctx.beginPath();
        ctx.moveTo(centerX + Math.cos(currentAngle) * innerRadius, centerY + Math.sin(currentAngle) * innerRadius);
        ctx.arc(centerX, centerY, radius, currentAngle, currentAngle + sliceAngle);
        ctx.arc(centerX, centerY, innerRadius, currentAngle + sliceAngle, currentAngle, true);
        ctx.closePath();

        // 填充颜色（带发光效果）
        ctx.shadowBlur = 20;
        ctx.shadowColor = item.color;
        ctx.fillStyle = item.color;
        ctx.fill();
        ctx.shadowBlur = 0;

        // 绘制边框
        ctx.strokeStyle = 'rgba(255,255,255,0.3)';
        ctx.lineWidth = 2;
        ctx.stroke();

        // 计算标签位置
        const labelRadius = radius + 40;
        const labelX = centerX + Math.cos(midAngle) * labelRadius;
        const labelY = centerY + Math.sin(midAngle) * labelRadius;

        // 绘制文字
        const labelText = item.label;
        const percentText = item.value + '%';
        const fontSize = 24;
        const percentFontSize = 28;

        // 绘制连线
        ctx.beginPath();
        ctx.moveTo(centerX + Math.cos(midAngle) * radius, centerY + Math.sin(midAngle) * radius);
        ctx.lineTo(labelX - Math.cos(midAngle) * 10, labelY - Math.sin(midAngle) * 10);
        ctx.strokeStyle = item.color;
        ctx.lineWidth = 2;
        ctx.stroke();

        ctx.font = `bold ${fontSize}px 'Microsoft YaHei', 'PingFang SC', sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';

        // 绘制阴影文字背景
        ctx.fillStyle = 'rgba(0, 0, 0, 0.8)';
        const textToDraw = `${labelText} ${percentText}`;
        const metrics = ctx.measureText(textToDraw);
        const tw = metrics.width + 20;
        const th = fontSize + 15;

        ctx.fillRect(labelX - tw / 2, labelY - th / 2, tw, th);

        // 绘制文字
        ctx.fillStyle = '#ffffff';
        ctx.fillText(textToDraw, labelX, labelY);

        currentAngle += sliceAngle;
    });

    // 绘制中心遮罩
    ctx.beginPath();
    ctx.arc(centerX, centerY, innerRadius, 0, 2 * Math.PI);
    ctx.fillStyle = '#050a15';
    ctx.fill();
    ctx.strokeStyle = 'rgba(0, 255, 157, 0.3)';
    ctx.lineWidth = 3;
    ctx.stroke();

    ctx.fillStyle = 'rgba(255, 255, 255, 0.6)';
    ctx.font = `bold 20px 'Microsoft YaHei', sans-serif`;
    ctx.textAlign = 'center';
    ctx.fillText('作物分布', centerX, centerY);
}

// 滚动日志动画（支持实时无人机消息）
function addLogEntry(message, timeStr) {
    const logContainer = document.getElementById('logContainer');
    if (!logContainer) return;
    if (!timeStr) {
        const now = new Date();
        timeStr = now.toLocaleTimeString('zh-CN', { hour12: false });
    }
    const logItem = document.createElement('div');
    logItem.className = 'log-item';
    logItem.style.opacity = '0';
    logItem.style.transform = 'translateX(-20px)';
    logItem.innerHTML = `<span style="color:var(--accent)">[${timeStr}]</span> ${message}`;
    logContainer.insertBefore(logItem, logContainer.firstChild);
    setTimeout(() => {
        logItem.style.transition = 'all 0.5s ease';
        logItem.style.opacity = '1';
        logItem.style.transform = 'translateX(0)';
    }, 10);
    while (logContainer.children.length > 25) {
        logContainer.removeChild(logContainer.lastChild);
    }
}

// WebSocket 连接，接收无人机实时动态
let dashboardSocket = null;
function connectDashboardSocket() {
    if (typeof io === 'undefined') return;
    dashboardSocket = io();
    dashboardSocket.on('drone_activity', function (data) {
        if (data && data.message) {
            addLogEntry(data.message);
        }
    });
    dashboardSocket.on('connect', function () {
        addLogEntry('数据大屏已连接，实时接收无人机动态');
    });
}

window.addEventListener('load', () => {
    initPieChart();
    loadDashboardMetrics();
    loadInitialLogs();
    connectDashboardSocket();
    setInterval(loadDashboardMetrics, 10000); // 每10秒刷新指标
});

window.addEventListener('resize', () => {
    initPieChart();
});
