const logTypeFilter = document.getElementById('logTypeFilter');
const refreshHistoryBtn = document.getElementById('refreshHistoryBtn');

function loadHistory() {
    const historyList = document.querySelector('.history-list');
    if (!historyList) return;
    
    // 显示加载状态
    historyList.innerHTML = '<div style="text-align: center; padding: 40px; color: var(--text-dim);">正在加载历史记录...</div>';
    
    const logType = logTypeFilter ? logTypeFilter.value : '';
    const query = logType ? `?limit=50&offset=0&log_type=${encodeURIComponent(logType)}` : '?limit=50&offset=0';

    fetch(`/api/recognition_history${query}`)
        .then(response => response.json())
        .then(data => {
            if (data.success && data.data.length > 0) {
                historyList.innerHTML = '';
                data.data.forEach(item => {
                    const historyItem = createHistoryItem(item);
                    historyList.appendChild(historyItem);
                });
                
                // 更新底部提示
                const bottomText = document.querySelector('main > div:last-child p');
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

// 创建历史记录项
function createHistoryItem(item) {
    const div = document.createElement('div');
    div.className = 'detail-item';
    div.style.cssText = 'padding: 20px; background: rgba(255,255,255,0.02); border-radius: 15px; margin-bottom: 15px; cursor: pointer; transition: all 0.3s;';
    
    // 悬停效果
    div.addEventListener('mouseenter', () => {
        div.style.background = 'rgba(255,255,255,0.05)';
        div.style.transform = 'translateX(5px)';
    });
    div.addEventListener('mouseleave', () => {
        div.style.background = 'rgba(255,255,255,0.02)';
        div.style.transform = 'translateX(0)';
    });
    
    // 获取类别图标和标题
    const { icon, title } = getHistoryItemInfo(item);
    
    const confidenceText = item.confidence !== null && item.confidence !== undefined
        ? `${item.class_name || '-'} (${Number(item.confidence).toFixed(2)}%)`
        : (item.class_name || '-');
    
    div.innerHTML = `
        <div style="display: flex; align-items: center; gap: 20px; width: 100%;">
            <div style="font-size: 2rem;">${icon}</div>
            <div style="flex: 1;">
                <div style="font-weight: 800; color: #fff;">${title}</div>
                <div style="font-size: 0.85rem; color: var(--text-dim); margin-top: 4px;">${item.timestamp}</div>
                <div style="font-size: 0.85rem; color: var(--text-dim); margin-top: 4px;">${item.action_summary || '无摘要'}</div>
            </div>
            <div style="text-align: right;">
                <div style="color: var(--primary); font-weight: 800;">${confidenceText}</div>
                <div style="font-size: 0.8rem; color: var(--accent); margin-top: 4px;">${item.log_type || 'log'} ></div>
            </div>
        </div>
    `;
    
    // 点击查看详情
    div.addEventListener('click', () => {
        // 可以跳转到详情页面或显示详情
        console.log('查看详情:', item);
    });
    
    return div;
}

// 获取历史记录项的图标和标题
function getHistoryItemInfo(item) {
    const modelName = item.model_name || '';
    const className = item.class_name || '';
    const logType = item.log_type || '';

    if (logType === 'risk_alert') {
        return { icon: '🛡️', title: '风险预警' };
    }
    if (logType === 'irrigation_plan') {
        return { icon: '💧', title: '灌溉建议' };
    }
    if (logType === 'task') {
        return { icon: '🗂️', title: '任务创建' };
    }
    if (logType === 'execution') {
        return { icon: '🎮', title: '执行回传' };
    }
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
        // 根据类别判断图标
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

// 页面加载时自动加载历史记录
document.addEventListener('DOMContentLoaded', () => {
    loadHistory();
    if (logTypeFilter) {
        logTypeFilter.addEventListener('change', loadHistory);
    }
    if (refreshHistoryBtn) {
        refreshHistoryBtn.addEventListener('click', loadHistory);
    }
});



