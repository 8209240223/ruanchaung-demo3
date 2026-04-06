// 移动端JavaScript
function updateTime() {
    const now = new Date();
    const timeStr = now.toLocaleTimeString('zh-CN', { hour12: false });
    document.getElementById('currentTime').textContent = timeStr;
}

// 更新时间
updateTime();
setInterval(updateTime, 1000);

// 导航功能
function navigateToPage(page) {
    const routes = {
        '无人机控制': '/无人机控制',
        '任务规划': '/任务规划',
        '识别': '/识别',
        '成熟度': '/成熟度',
        '病虫害': '/病虫害',
        '用药': '/用药',
        '气象': '/气象',
        '历史': '/历史',
        '视频分析': '/视频分析'
    };

    if (routes[page]) {
        window.location.href = routes[page];
    }
}

// 底部导航切换
function switchNav(nav) {
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => item.classList.remove('active'));

    event.currentTarget.classList.add('active');

    // 这里可以添加页面切换逻辑
    console.log('切换到:', nav);
}

