// 全局变量
let selectedModelType = 'demo1'; // 默认选择demo1
let availableModels = [];

// 页面入口导航
function navigateToEntry(entry) {
    const routes = {
        'mobile': '/mobile',
        'admin': '/admin',
        'dashboard': '/dashboard',
        'uav': '/无人机控制'
    };
    if (routes[entry]) {
        window.location.href = routes[entry];
    }
}

// 动态卡片交互特效 (磁性旋转效果 - 修复版)
function initCardInteractions() {
    const cards = document.querySelectorAll('.entry-card, .model-card');
    cards.forEach(card => {
        card.style.transition = 'transform 0.1s ease-out';
        
        card.addEventListener('mousemove', (e) => {
            const rect = card.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            
            const xc = ((x - rect.width / 2) / (rect.width / 2));
            const yc = ((y - rect.height / 2) / (rect.height / 2));
            
            const maxRotation = 8; // 首页卡片可以稍大一点，但控制在8度内
            const rotateY = xc * maxRotation;
            const rotateX = -yc * maxRotation;
            
            card.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateY(-10px) scale(1.03)`;
        });
        
        card.addEventListener('mouseleave', () => {
            card.style.transition = 'transform 0.5s cubic-bezier(0.2, 0.8, 0.2, 1)';
            card.style.transform = 'perspective(1000px) rotateX(0) rotateY(0) translateY(0) scale(1)';
        });
    });
}

// 文字逐字显示特效
function typeWriter(element, text, speed = 30) {
    element.textContent = '';
    let i = 0;
    function type() {
        if (i < text.length) {
            element.textContent += text.charAt(i);
            i++;
            setTimeout(type, speed);
        }
    }
    type();
}

// 获取DOM元素
const uploadBox = document.getElementById('uploadBox');
const fileInput = document.getElementById('fileInput');
const uploadBtn = document.getElementById('uploadBtn');
const previewSection = document.getElementById('previewSection');
const previewImage = document.getElementById('previewImage');
const resultSection = document.getElementById('resultSection');
const loading = document.getElementById('loading');
const errorMessage = document.getElementById('errorMessage');
const modelCards = document.getElementById('modelCards');
const modelInfo = document.getElementById('modelInfo');

// 页面加载时获取可用模型列表
window.addEventListener('DOMContentLoaded', async () => {
    await loadModels();
    initCardInteractions();
    
    // 检查是否有待识别的拍照图片
    checkCapturedImage();
});

// 检查并处理拍照后的图片
function checkCapturedImage() {
    try {
        const capturedImageData = sessionStorage.getItem('capturedImage');
        if (capturedImageData) {
            const imageInfo = JSON.parse(capturedImageData);
            
            // 清除sessionStorage
            sessionStorage.removeItem('capturedImage');
            
            // 显示提示
            if (uploadBox) {
                uploadBox.style.border = '3px solid var(--primary)';
                uploadBox.style.boxShadow = '0 0 20px var(--primary)';
            }
            
            // 创建File对象从base64数据
            const base64Data = imageInfo.image_data;
            const byteCharacters = atob(base64Data);
            const byteNumbers = new Array(byteCharacters.length);
            for (let i = 0; i < byteCharacters.length; i++) {
                byteNumbers[i] = byteCharacters.charCodeAt(i);
            }
            const byteArray = new ArrayBuffer(byteNumbers.length);
            const uint8Array = new Uint8Array(byteArray);
            for (let i = 0; i < byteNumbers.length; i++) {
                uint8Array[i] = byteNumbers[i];
            }
            const blob = new Blob([byteArray], { type: 'image/jpeg' });
            const file = new File([blob], imageInfo.filename || 'captured_image.jpg', { type: 'image/jpeg' });
            
            // 将文件设置到fileInput（这样uploadAndPredict可以正确获取）
            const dataTransfer = new DataTransfer();
            dataTransfer.items.add(file);
            if (fileInput) {
                fileInput.files = dataTransfer.files;
            }
            
            // 拍照功能：自动识别（不显示在上传框中，直接显示在预览区域）
            const reader = new FileReader();
            reader.onload = (e) => {
                // 显示在预览区域
                previewImage.src = e.target.result;
                previewSection.style.display = 'block';
                uploadBtn.style.display = 'block';
                resultSection.style.display = 'none';
                hideError();
                
                // 延迟1.5秒后自动点击识别按钮
                setTimeout(() => {
                    if (uploadBtn && uploadBtn.style.display !== 'none') {
                        uploadBtn.click();
                    }
                }, 1500);
            };
            reader.readAsDataURL(file);
            
            console.log('[主页] 检测到拍照图片，自动加载并识别');
        }
    } catch (error) {
        console.error('[主页] 处理拍照图片失败:', error);
    }
}

// 加载模型列表
async function loadModels() {
    try {
        const response = await fetch('/api/models');
        const data = await response.json();
        availableModels = data.models;
        renderModelCards();
    } catch (error) {
        console.error('加载模型列表失败:', error);
        showError('无法加载模型列表');
    }
}

// 渲染模型卡片
function renderModelCards() {
    modelCards.innerHTML = '';
    
    availableModels.forEach(model => {
        const card = document.createElement('div');
        card.className = `model-card ${model.available ? '' : 'unavailable'}`;
        if (model.type === selectedModelType && model.available) {
            card.classList.add('selected');
        }
        
        if (model.available) {
            card.addEventListener('click', () => selectModel(model.type));
        }
        
        card.innerHTML = `
            <div class="model-card-title">${model.name}</div>
            <div class="model-card-description">${model.description}</div>
            <div class="model-card-classes">类别: ${model.classes.join(', ')}</div>
            <div class="model-card-status ${model.available ? 'available' : 'unavailable'}">
                ${model.available ? '✓ 可用' : '✗ 不可用'}
            </div>
        `;
        
        modelCards.appendChild(card);
    });
    // 重新初始化交互，因为模型卡片是动态生成的
    initCardInteractions();
}

// 选择模型
function selectModel(modelType) {
    selectedModelType = modelType;
    renderModelCards();
    
    // 更新模型信息显示
    const model = availableModels.find(m => m.type === modelType);
    if (model) {
        modelInfo.innerHTML = `
            <div class="model-info-title" style="color:var(--primary); font-weight:800; font-size:1.2rem;">当前选择的模型: ${model.name}</div>
            <div style="color:var(--text-dim); margin-top:5px;">${model.description}</div>
        `;
    }
}

// 上传框点击事件
uploadBox.addEventListener('click', () => {
    fileInput.click();
});

// 文件选择事件
fileInput.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) {
        handleFile(file);
    }
});

// 拖拽事件
uploadBox.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadBox.classList.add('dragover');
});

uploadBox.addEventListener('dragleave', () => {
    uploadBox.classList.remove('dragover');
});

uploadBox.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadBox.classList.remove('dragover');
    
    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith('image/')) {
        handleFile(file);
    } else {
        showError('请上传图片文件！');
    }
});

// 处理文件（普通上传，只显示在上传框中，不自动识别）
function handleFile(file) {
    // 检查文件类型
    if (!file.type.startsWith('image/')) {
        showError('请上传图片文件！');
        return;
    }
    
    // 检查文件大小（16MB）
    if (file.size > 16 * 1024 * 1024) {
        showError('文件大小不能超过16MB！');
        return;
    }
    
    // 检查模型是否可用
    const model = availableModels.find(m => m.type === selectedModelType);
    if (!model || !model.available) {
        showError('所选模型不可用，请选择其他模型！');
        return;
    }
    
    // 在上传框中显示图片预览
    const reader = new FileReader();
    reader.onload = (e) => {
        const uploadPreview = document.getElementById('uploadPreview');
        const scannerIcon = document.getElementById('scannerIcon');
        const uploadInfo = document.getElementById('uploadInfo');
        
        // 显示图片预览
        uploadPreview.src = e.target.result;
        uploadPreview.style.display = 'block';
        
        // 隐藏上传图标和信息
        if (scannerIcon) scannerIcon.style.display = 'none';
        if (uploadInfo) uploadInfo.style.display = 'none';
        
        // 显示识别按钮
        uploadBtn.style.display = 'block';
        
        // 隐藏之前的预览区域和结果区域
        previewSection.style.display = 'none';
        resultSection.style.display = 'none';
        hideError();
    };
    reader.readAsDataURL(file);
}

// 上传按钮点击事件
uploadBtn.addEventListener('click', () => {
    const file = fileInput.files[0];
    if (file) {
        uploadAndPredict(file);
    }
});

// 重新上传按钮
document.getElementById('resetBtn').addEventListener('click', () => {
    resetForm();
});

// 上传并预测
function uploadAndPredict(file) {
    // 如果没有传入file参数，从fileInput获取
    if (!file) {
        file = fileInput.files[0];
    }
    
    if (!file) {
        showError('请先选择图片！');
        return;
    }
    
    // 显示加载动画
    loading.style.display = 'block';
    resultSection.style.display = 'none';
    uploadBtn.disabled = true;
    hideError();
    
    // 创建FormData
    const formData = new FormData();
    formData.append('file', file);
    formData.append('model_type', selectedModelType);
    
    // 发送请求
    fetch('/upload', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        loading.style.display = 'none';
        uploadBtn.disabled = false;
        
        if (data.success) {
            // 显示预览区域（从上传框移动到预览区域）
            const uploadPreview = document.getElementById('uploadPreview');
            if (uploadPreview && uploadPreview.src) {
                previewImage.src = uploadPreview.src;
                previewSection.style.display = 'block';
            }
            
            displayResult(data);
        } else {
            showError(data.error || '预测失败，请重试！');
        }
    })
    .catch(error => {
        loading.style.display = 'none';
        uploadBtn.disabled = false;
        showError('网络错误：' + error.message);
        console.error('Error:', error);
    });
}

// 显示结果
function displayResult(data) {
    // 显示结果区域
    resultSection.style.display = 'block';
    
    // 更新模型信息
    modelInfo.innerHTML = `
        <div class="model-info-title" style="color:var(--accent); font-weight:800;">使用的模型: ${data.model_name}</div>
        <div style="font-size:0.9rem; opacity:0.8;">模型类型: ${data.model_type}</div>
    `;
    
    // 显示主要结果
    document.getElementById('resultClass').textContent = data.class_name;
    document.getElementById('confidenceText').textContent = `${data.confidence}%`;
    document.getElementById('confidenceFill').style.width = `${data.confidence}%`;
    
    // 动画显示置信度条
    document.getElementById('confidenceFill').animate([
        { width: '0%' },
        { width: `${data.confidence}%` }
    ], { duration: 1000, easing: 'cubic-bezier(0.2, 0.8, 0.2, 1)' });

    // 逐字显示描述
    const descElement = document.getElementById('resultDescription');
    typeWriter(descElement, data.description);
    
    // 显示概率列表
    const probabilityList = document.getElementById('probabilityList');
    probabilityList.innerHTML = '';
    
    // 按概率排序
    const sortedProbs = Object.entries(data.probabilities)
        .sort((a, b) => b[1] - a[1]);
    
    sortedProbs.forEach(([className, prob], index) => {
        const item = document.createElement('div');
        item.className = 'probability-item';
        item.style.animation = `cardIn 0.5s ease-out ${index * 0.1}s both`;
        
        if (className === data.class_name) {
            item.classList.add('selected');
            item.style.borderColor = 'var(--primary)';
            item.style.boxShadow = '0 0 15px rgba(0, 255, 157, 0.2)';
        }
        
        item.innerHTML = `
            <div class="probability-label">${className}</div>
            <div class="probability-value">${prob}%</div>
        `;
        
        probabilityList.appendChild(item);
    });
    
    // 显示标注后的图片
    const annotatedImg = document.getElementById('annotatedImage');
    annotatedImg.src = data.annotated_image;
    annotatedImg.style.animation = 'fadeInUp 0.8s ease-out';
    
    // 自动获取AI建议
    getAISuggestion(data);
    renderActionPlan(data.action_plan);
    
    // 滚动到结果区域
    resultSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function renderActionPlan(actionPlan) {
    const section = document.getElementById('actionPlanSection');
    const card = document.getElementById('actionPlanCard');
    if (!section || !card) return;

    if (!actionPlan) {
        section.style.display = 'none';
        card.innerHTML = '';
        return;
    }

    const steps = (actionPlan.next_steps || []).map(step => `<li style="margin: 6px 0;">${step}</li>`).join('');
    card.innerHTML = `
        <div style="display:grid; gap:10px;">
            <div><strong>紧急程度：</strong>${actionPlan.urgency || '中'}</div>
            <div><strong>预计收益：</strong>${actionPlan.expected_benefit || '待评估'}</div>
            <div><strong>下一步动作：</strong><ul style="margin:8px 0 0 18px;">${steps}</ul></div>
            <div><strong>注意事项：</strong>${actionPlan.notes || '无'}</div>
        </div>
    `;
    section.style.display = 'block';
}

// 获取AI建议
function getAISuggestion(data) {
    const aiSuggestionSection = document.getElementById('aiSuggestionSection');
    const aiLoading = document.getElementById('aiLoading');
    const aiContent = document.getElementById('aiContent');
    
    // 显示AI建议区域
    aiSuggestionSection.style.display = 'block';
    aiLoading.style.display = 'block';
    aiContent.style.display = 'none';
    
    // 获取图片路径（优先使用原始图片，如果没有则使用标注后的图片）
    let imagePath;
    if (data.original_image) {
        imagePath = data.original_image.replace('/uploads/', 'uploads/');
    } else {
        // 从annotated_image中提取原始文件名
        const imageUrl = data.annotated_image;
        imagePath = imageUrl.replace('/uploads/', 'uploads/').replace('annotated_', '');
    }
    
    // 调用API获取建议
    fetch('/api/get_ai_suggestion', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            image_path: imagePath,
            class_name: data.class_name,
            confidence: data.confidence
        })
    })
    .then(response => response.json())
    .then(result => {
        aiLoading.style.display = 'none';
        
        if (result.success) {
            aiContent.style.display = 'block';
            // 将Markdown格式的建议转换为HTML
            aiContent.innerHTML = formatMarkdownToHTML(result.suggestion);
        } else {
            aiContent.style.display = 'block';
            aiContent.innerHTML = `<div style="color: var(--text-dim); padding: 20px; text-align: center;">⚠️ ${result.error || '获取AI建议失败'}</div>`;
        }
    })
    .catch(error => {
        aiLoading.style.display = 'none';
        aiContent.style.display = 'block';
        aiContent.innerHTML = `<div style="color: var(--text-dim); padding: 20px; text-align: center;">⚠️ 网络错误：${error.message}</div>`;
        console.error('[AI建议] 获取失败:', error);
    });
}

// 将Markdown格式转换为HTML
function formatMarkdownToHTML(markdown) {
    let html = markdown;
    
    // 转换标题
    html = html.replace(/^### (.*$)/gim, '<h4 style="color: var(--accent); margin-top: 20px; margin-bottom: 10px; font-size: 1.1rem;">$1</h4>');
    html = html.replace(/^## (.*$)/gim, '<h3 style="color: var(--primary); margin-top: 25px; margin-bottom: 15px; font-size: 1.3rem;">$1</h3>');
    html = html.replace(/^# (.*$)/gim, '<h2 style="color: var(--primary); margin-top: 30px; margin-bottom: 20px; font-size: 1.5rem;">$1</h2>');
    
    // 转换粗体
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong style="color: var(--primary);">$1</strong>');
    
    // 转换列表
    html = html.replace(/^\d+\.\s+(.*$)/gim, '<li style="margin: 8px 0; padding-left: 10px; color: var(--text-bright);">$1</li>');
    html = html.replace(/^-\s+(.*$)/gim, '<li style="margin: 8px 0; padding-left: 10px; color: var(--text-bright);">$1</li>');
    
    // 包装列表项
    html = html.replace(/(<li.*<\/li>)/g, '<ul style="margin: 15px 0; padding-left: 25px; list-style: none;">$1</ul>');
    
    // 转换段落
    html = html.split('\n\n').map(para => {
        if (!para.trim()) return '';
        if (para.startsWith('<')) return para;
        return `<p style="margin: 12px 0; line-height: 1.8; color: var(--text-bright);">${para.trim()}</p>`;
    }).join('');
    
    return html;
}

// 删除功能
document.getElementById('deleteBtn').addEventListener('click', () => {
    if (confirm('确定要删除当前图片和所有识别结果吗？')) {
        deleteAll();
    }
});

function deleteAll() {
    // 清除所有显示内容
    fileInput.value = '';
    previewSection.style.display = 'none';
    resultSection.style.display = 'none';
    uploadBtn.style.display = 'none';
    loading.style.display = 'none';
    document.getElementById('aiSuggestionSection').style.display = 'none';
    const actionPlanSection = document.getElementById('actionPlanSection');
    const actionPlanCard = document.getElementById('actionPlanCard');
    if (actionPlanSection) actionPlanSection.style.display = 'none';
    if (actionPlanCard) actionPlanCard.innerHTML = '';
    hideError();
    
    // 清除上传框中的预览
    const uploadPreview = document.getElementById('uploadPreview');
    const scannerIcon = document.getElementById('scannerIcon');
    const uploadInfo = document.getElementById('uploadInfo');
    
    if (uploadPreview) {
        uploadPreview.src = '';
        uploadPreview.style.display = 'none';
    }
    if (scannerIcon) {
        scannerIcon.style.display = 'flex';
    }
    if (uploadInfo) {
        uploadInfo.style.display = 'block';
    }
    
    // 清除预览图片
    if (previewImage) {
        previewImage.src = '';
    }
    
    // 清除标注图片
    const annotatedImg = document.getElementById('annotatedImage');
    if (annotatedImg) {
        annotatedImg.src = '';
    }
    
    // 清除AI建议内容
    const aiContent = document.getElementById('aiContent');
    if (aiContent) {
        aiContent.innerHTML = '';
    }
    
    console.log('[删除] 已清除所有内容');
}

// 重置表单
function resetForm() {
    fileInput.value = '';
    previewSection.style.display = 'none';
    resultSection.style.display = 'none';
    uploadBtn.style.display = 'none';
    loading.style.display = 'none';
    const actionPlanSection = document.getElementById('actionPlanSection');
    const actionPlanCard = document.getElementById('actionPlanCard');
    if (actionPlanSection) actionPlanSection.style.display = 'none';
    if (actionPlanCard) actionPlanCard.innerHTML = '';
    hideError();
    
    // 恢复上传框显示
    const uploadPreview = document.getElementById('uploadPreview');
    const scannerIcon = document.getElementById('scannerIcon');
    const uploadInfo = document.getElementById('uploadInfo');
    
    if (uploadPreview) {
        uploadPreview.src = '';
        uploadPreview.style.display = 'none';
    }
    if (scannerIcon) {
        scannerIcon.style.display = 'flex';
    }
    if (uploadInfo) {
        uploadInfo.style.display = 'block';
    }
}

// 显示错误
function showError(message) {
    errorMessage.textContent = message;
    errorMessage.style.display = 'block';
    errorMessage.style.animation = 'shake 0.5s ease-in-out';
}

// 隐藏错误
function hideError() {
    errorMessage.style.display = 'none';
}
