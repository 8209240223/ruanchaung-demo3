// 病虫害诊断页面 JavaScript - 集成云端 AI 识别
const uploadBox = document.getElementById('uploadBox');
const fileInput = document.getElementById('fileInput');
const diagnoseBtn = document.getElementById('diagnoseBtn');
const previewSection = document.getElementById('previewSection');
const previewImage = document.getElementById('previewImage');
const resultSection = document.getElementById('resultSection');
const loading = document.getElementById('loading');
const errorMessage = document.getElementById('errorMessage');
const diagnosisResult = document.getElementById('diagnosisResult');
const resetBtn = document.getElementById('resetBtn');
const riskEvaluateBtn = document.getElementById('riskEvaluateBtn');
const riskAlertResult = document.getElementById('riskAlertResult');

let currentFile = null;

// 上传框点击事件
if (uploadBox && fileInput) {
    uploadBox.addEventListener('click', () => fileInput.click());

    // 拖拽支持
    uploadBox.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadBox.style.borderColor = 'var(--primary)';
        uploadBox.style.background = 'rgba(0, 255, 157, 0.1)';
    });

    uploadBox.addEventListener('dragleave', () => {
        uploadBox.style.borderColor = 'var(--accent)';
        uploadBox.style.background = 'rgba(0, 210, 255, 0.05)';
    });

    uploadBox.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadBox.style.borderColor = 'var(--accent)';
        uploadBox.style.background = 'rgba(0, 210, 255, 0.05)';

        const file = e.dataTransfer.files[0];
        if (file && file.type.startsWith('image/')) {
            handleFile(file);
        } else {
            showError('请上传图片文件！');
        }
    });

    fileInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            handleFile(file);
        }
    });
}

// 处理文件
function handleFile(file) {
    if (!file.type.startsWith('image/')) {
        showError('请上传图片文件！');
        return;
    }

    if (file.size > 16 * 1024 * 1024) {
        showError('文件大小不能超过16MB！');
        return;
    }

    currentFile = file;

    const reader = new FileReader();
    reader.onload = (e) => {
        previewImage.src = e.target.result;
        previewSection.style.display = 'block';
        diagnoseBtn.style.display = 'block';
        resultSection.style.display = 'none';
        hideError();

        // 滚动到预览区域
        previewSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    };
    reader.readAsDataURL(file);
}

// 启动识别（本地模型）
if (diagnoseBtn) {
    diagnoseBtn.addEventListener('click', () => {
        if (currentFile) {
            diagnoseLocal(currentFile);
        }
    });
}

function diagnoseLocal(file) {
    if (loading) loading.style.display = 'block';
    if (resultSection) resultSection.style.display = 'none';
    if (diagnoseBtn) diagnoseBtn.disabled = true;
    hideError();
    const modelType = document.querySelector('input[name="modelType"]:checked')?.value || 'apple_disease';
    const formData = new FormData();
    formData.append('file', file);
    formData.append('model_type', modelType);
    fetch('/api/diagnose_pest', { method: 'POST', body: formData })
        .then(response => response.json())
        .then(data => {
            if (loading) loading.style.display = 'none';
            if (diagnoseBtn) diagnoseBtn.disabled = false;
            if (data.success) {
                resultSection.style.display = 'block';
                displayDiagnosisResult(data.result);
            } else {
                showError(data.error || '识别失败，请重试');
            }
        })
        .catch(error => {
            if (loading) loading.style.display = 'none';
            if (diagnoseBtn) diagnoseBtn.disabled = false;
            showError('网络错误：' + error.message);
        });
}

// 获取详细建议（云端大模型）
const aiDetailBtn = document.getElementById('aiDetailBtn');
const aiDetailLoading = document.getElementById('aiDetailLoading');
const aiDetailResult = document.getElementById('aiDetailResult');

if (aiDetailBtn) {
    aiDetailBtn.addEventListener('click', () => {
        if (!currentFile) {
            showError('请先上传图片并点击「启动识别」后再获取详细建议');
            return;
        }
        if (aiDetailResult) aiDetailResult.style.display = 'none';
        if (aiDetailLoading) aiDetailLoading.style.display = 'block';
        aiDetailBtn.disabled = true;
        hideError();
        const formData = new FormData();
        formData.append('file', currentFile);
        fetch('/api/diagnose_pest_ai', { method: 'POST', body: formData })
            .then(response => response.json())
            .then(data => {
                if (aiDetailLoading) aiDetailLoading.style.display = 'none';
                aiDetailBtn.disabled = false;
                if (data.success && aiDetailResult) {
                    aiDetailResult.style.display = 'block';
                    renderAiDetailResult(data.result);
                } else {
                    showError(data.error || '获取详细建议失败');
                }
            })
            .catch(error => {
                if (aiDetailLoading) aiDetailLoading.style.display = 'none';
                aiDetailBtn.disabled = false;
                showError('网络错误：' + error.message);
            });
    });
}

function renderAiDetailResult(result) {
    if (!aiDetailResult) return;
    if (typeof result === 'object' && result !== null) {
        const confidencePct = Math.round((Number(result.confidence || 0) * 100) * 100) / 100;
        const plans = Array.isArray(result.treatment_plan) ? result.treatment_plan : [];
        const levelColor = result.risk_level === '高' ? '#ff6b6b' : result.risk_level === '中' ? '#ffc107' : '#00ff9d';
        aiDetailResult.innerHTML = `
            <div style="margin-bottom:12px; color:var(--text-dim); font-size:0.9rem;">系统详细建议</div>
            <div style="display:grid; gap:8px;">
                <div><strong>分析情况：</strong>${result.disease_name || '未知'}</div>
                <div><strong>风险等级：</strong><span style="color:${levelColor}; font-weight:700;">${result.risk_level || '中'}</span></div>
                <div><strong>置信度：</strong>${confidencePct}%</div>
                <div><strong>处理时窗：</strong>${result.action_window || '-'}</div>
                <div><strong>防治措施：</strong><ul style="margin:6px 0 0 18px;">${plans.slice(0, 5).map(p => '<li>' + p + '</li>').join('')}</ul></div>
            </div>
        `;
    } else {
        aiDetailResult.textContent = typeof result === 'string' ? result : JSON.stringify(result);
    }
}

// 显示诊断结果（结构化输出优先）
function displayDiagnosisResult(result) {
    if (resultSection) {
        resultSection.style.display = 'block';
        resultSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    if (diagnosisResult) {
        diagnosisResult.innerHTML = '';

        if (typeof result === 'object' && result !== null) {
            const confidencePct = Math.round((Number(result.confidence || 0) * 100) * 100) / 100;
            const plans = Array.isArray(result.treatment_plan) ? result.treatment_plan : [];
            const levelColor = result.risk_level === '高' ? '#ff6b6b' : result.risk_level === '中' ? '#ffc107' : '#00ff9d';
            diagnosisResult.innerHTML = `
                <div style="display:grid; gap:10px;">
                    <div><strong>病虫害名称：</strong>${result.disease_name || '未知'}</div>
                    <div><strong>风险等级：</strong><span style="color:${levelColor}; font-weight:700;">${result.risk_level || '中'}</span></div>
                    <div><strong>置信度：</strong>${confidencePct}%</div>
                    <div><strong>处理时窗：</strong>${result.action_window || '未来48小时内复查'}</div>
                    <div><strong>防治措施：</strong>
                        <ul style="margin: 8px 0 0 18px;">
                            ${plans.slice(0, 3).map(p => `<li>${p}</li>`).join('')}
                        </ul>
                    </div>
                </div>
            `;
            return;
        }

        const formattedResult = formatDiagnosisResult(result);
        typeWriter(diagnosisResult, formattedResult, 20);
    }
}

// 格式化诊断结果
function formatDiagnosisResult(result) {
    if (typeof result === 'string') {
        // 如果结果包含配置提示，直接返回
        if (result.includes('⚠️') || result.includes('API密钥')) {
            return result;
        }

        // 尝试格式化文本（添加换行和结构）
        let formatted = result;

        // 检测是否有编号列表
        formatted = formatted.replace(/\n(\d+\.)/g, '\n\n$1');

        // 检测是否有标题（如"1. 病虫害类型"）
        formatted = formatted.replace(/(\d+\.\s*[^：:]+[：:])/g, '\n\n**$1**\n');

        return formatted;
    }

    return JSON.stringify(result, null, 2);
}

// 打字机效果
function typeWriter(element, text, speed = 20) {
    if (!element) return;

    let i = 0;
    function type() {
        if (i < text.length) {
            // 处理Markdown格式（简单版本）
            if (text[i] === '\n') {
                element.innerHTML += '<br>';
            } else if (text.substring(i, i + 2) === '**') {
                // 简单的粗体标记
                i += 2;
                const endBold = text.indexOf('**', i);
                if (endBold !== -1) {
                    element.innerHTML += '<strong>' + text.substring(i, endBold) + '</strong>';
                    i = endBold + 2;
                }
            } else {
                element.textContent += text[i];
            }
            i++;
            setTimeout(type, speed);
        }
    }
    type();
}

// 重新上传
if (resetBtn) {
    resetBtn.addEventListener('click', () => {
        if (fileInput) fileInput.value = '';
        currentFile = null;
        if (previewSection) previewSection.style.display = 'none';
        if (resultSection) resultSection.style.display = 'none';
        if (diagnoseBtn) {
            diagnoseBtn.style.display = 'none';
            diagnoseBtn.disabled = false;
        }
        if (aiDetailResult) {
            aiDetailResult.style.display = 'none';
            aiDetailResult.innerHTML = '';
        }
        if (aiDetailLoading) aiDetailLoading.style.display = 'none';
        if (aiDetailBtn) aiDetailBtn.disabled = false;
        hideError();
        window.scrollTo({ top: 0, behavior: 'smooth' });
    });
}

if (riskEvaluateBtn) {
    riskEvaluateBtn.addEventListener('click', () => {
        createRiskAlert();
    });
}

function createRiskAlert() {
    const plotName = document.getElementById('riskPlot')?.value?.trim() || 'A区';
    const temperature = parseFloat(document.getElementById('riskTemp')?.value || '28');
    const humidity = parseFloat(document.getElementById('riskHumidity')?.value || '72');
    const rainfall = parseFloat(document.getElementById('riskRainfall')?.value || '5');

    if (riskAlertResult) {
        riskAlertResult.innerHTML = '正在生成预警...';
    }

    fetch('/api/risk_alerts', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-User-Role': 'agronomist'
        },
        body: JSON.stringify({
            plot_name: plotName,
            temperature: temperature,
            humidity: humidity,
            rainfall: rainfall
        })
    })
        .then(response => response.json())
        .then(data => {
            if (!riskAlertResult) return;
            if (!data.success) {
                riskAlertResult.innerHTML = `<div style="color:#ff6b6b;">生成失败：${data.error || '未知错误'}</div>`;
                return;
            }
            const alert = data.data;
            const probability = Math.round((alert.probability || 0) * 100);
            const levelColor = alert.risk_level === '高' ? '#ff6b6b' : alert.risk_level === '中' ? '#ffc107' : '#00ff9d';
            riskAlertResult.innerHTML = `
            <div style="padding:12px; border-radius:12px; border:1px solid ${levelColor}; background:rgba(255,255,255,0.03);">
                <div><strong>地块：</strong>${alert.plot_name}</div>
                <div><strong>风险类型：</strong>${alert.risk_type}</div>
                <div><strong>风险等级：</strong><span style="color:${levelColor}; font-weight:700;">${alert.risk_level}</span></div>
                <div><strong>发生概率：</strong>${probability}%</div>
                <div><strong>处理窗口：</strong>${alert.operation_window}</div>
                <div><strong>建议：</strong>${alert.recommendation}</div>
            </div>
        `;
        })
        .catch(error => {
            if (riskAlertResult) {
                riskAlertResult.innerHTML = `<div style="color:#ff6b6b;">请求失败：${error.message}</div>`;
            }
        });
}

// 显示错误
function showError(message) {
    if (errorMessage) {
        errorMessage.textContent = message;
        errorMessage.style.display = 'block';
        errorMessage.style.animation = 'shake 0.5s ease-in-out';
        errorMessage.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
}

// 隐藏错误
function hideError() {
    if (errorMessage) {
        errorMessage.style.display = 'none';
    }
}

// 添加shake动画
if (!document.getElementById('shakeStyle')) {
    const style = document.createElement('style');
    style.id = 'shakeStyle';
    style.textContent = `
        @keyframes shake {
            0%, 100% { transform: translateX(0); }
            25% { transform: translateX(-10px); }
            75% { transform: translateX(10px); }
        }
    `;
    document.head.appendChild(style);
}
