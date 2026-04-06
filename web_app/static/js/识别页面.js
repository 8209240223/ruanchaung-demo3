// 识别页面JavaScript - 高级特效版
let selectedModelType = 'demo2'; // 默认使用demo2（多类别水果分类）
let availableModels = [];

// 页面加载时加载模型列表
window.addEventListener('DOMContentLoaded', async function() {
    await loadModels();
    initCardInteractions();
});

// 磁性卡片特效 - 修复稳定版
function initCardInteractions() {
    const cards = document.querySelectorAll('.card-glass, .model-card');
    cards.forEach(card => {
        card.style.transition = 'transform 0.1s ease-out';
        
        card.addEventListener('mousemove', (e) => {
            const rect = card.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            
            const xc = ((x - rect.width / 2) / (rect.width / 2));
            const yc = ((y - rect.height / 2) / (rect.height / 2));
            
            const maxRotation = 5;
            const rotateY = xc * maxRotation;
            const rotateX = -yc * maxRotation;
            
            card.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateY(-5px) scale(1.01)`;
        });
        
        card.addEventListener('mouseleave', () => {
            card.style.transition = 'transform 0.5s cubic-bezier(0.2, 0.8, 0.2, 1)';
            card.style.transform = 'perspective(1000px) rotateX(0) rotateY(0) translateY(0) scale(1)';
        });
    });
}

// 文字逐字显示
function typeWriter(element, text, speed = 30) {
    if (!element) return;
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

async function loadModels() {
    try {
        const response = await fetch('/api/models');
        const data = await response.json();
        availableModels = data.models;
        renderModelCards(data.models);
        
        // 更新当前模型信息
        const currentModel = availableModels.find(m => m.type === selectedModelType);
        if (currentModel) {
            updateModelDisplay(currentModel);
        }
    } catch (error) {
        console.error('加载模型列表失败:', error);
    }
}

function renderModelCards(models) {
    const modelCards = document.getElementById('modelCards');
    if (!modelCards) return;
    
    // 如果页面上有modelCards容器，则渲染。如果没有（例如在独立的功能页中可能隐藏了选择），则跳过。
    // 在 识别页面.html 中，我们目前没有显式展示所有模型卡片，而是直接锁定 demo2。
}

function updateModelDisplay(model) {
    const modelInfo = document.getElementById('modelInfo');
    if (modelInfo) {
        modelInfo.innerHTML = `
            <div style="display:flex; align-items:center; gap:15px;">
                <div style="font-size:2rem;">🧠</div>
                <div>
                    <div style="color:var(--primary); font-weight:800; font-size:1.1rem;">当前AI引擎: ${model.name}</div>
                    <div style="color:var(--text-dim); font-size:0.9rem;">${model.description}</div>
                </div>
            </div>
        `;
    }
}

// 文件上传处理
const uploadBox = document.getElementById('uploadBox');
const fileInput = document.getElementById('fileInput');
const uploadBtn = document.getElementById('uploadBtn');
const resultSection = document.getElementById('resultSection');
const loading = document.getElementById('loading');
const previewSection = document.getElementById('previewSection');

if (uploadBox && fileInput) {
    uploadBox.addEventListener('click', () => fileInput.click());
    
    fileInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            handleFile(file);
        }
    });
}

if (uploadBtn) {
    uploadBtn.addEventListener('click', () => {
        const file = fileInput.files[0];
        if (file) {
            uploadAndPredict(file);
        }
    });
}

function handleFile(file) {
    if (!file.type.startsWith('image/')) {
        alert('请上传图片文件！');
        return;
    }
    
    const reader = new FileReader();
    reader.onload = (e) => {
        const previewImage = document.getElementById('previewImage');
        if (previewImage) {
            previewImage.src = e.target.result;
        }
        if (previewSection) previewSection.style.display = 'block';
        if (uploadBtn) uploadBtn.style.display = 'block';
        if (resultSection) resultSection.style.display = 'none';
    };
    reader.readAsDataURL(file);
}

function uploadAndPredict(file) {
    if (loading) loading.style.display = 'block';
    if (resultSection) resultSection.style.display = 'none';
    if (uploadBtn) uploadBtn.disabled = true;
    
    const formData = new FormData();
    formData.append('file', file);
    formData.append('model_type', selectedModelType);
    
    fetch('/upload', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (loading) loading.style.display = 'none';
        if (uploadBtn) uploadBtn.disabled = false;
        
        if (data.success) {
            displayResult(data);
        } else {
            alert(data.error || '预测失败，请重试！');
        }
    })
    .catch(error => {
        if (loading) loading.style.display = 'none';
        if (uploadBtn) uploadBtn.disabled = false;
        alert('网络错误：' + error.message);
    });
}

function displayResult(data) {
    if (resultSection) {
        resultSection.style.display = 'block';
        resultSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
    
    const resultClass = document.getElementById('resultClass');
    const confidenceText = document.getElementById('confidenceText');
    const confidenceFill = document.getElementById('confidenceFill');
    const resultDescription = document.getElementById('resultDescription');
    const probabilityList = document.getElementById('probabilityList');
    const annotatedImage = document.getElementById('annotatedImage');
    
    if (resultClass) {
        resultClass.textContent = data.class_name;
        resultClass.style.animation = 'glowPulse 2s infinite';
    }
    
    if (confidenceText) confidenceText.textContent = `${data.confidence}%`;
    if (confidenceFill) {
        confidenceFill.style.width = '0%';
        setTimeout(() => {
            confidenceFill.style.transition = 'width 1s cubic-bezier(0.2, 0.8, 0.2, 1)';
            confidenceFill.style.width = `${data.confidence}%`;
        }, 100);
    }
    
    if (resultDescription) {
        typeWriter(resultDescription, data.description);
    }
    
    if (annotatedImage) {
        annotatedImage.src = data.annotated_image;
        annotatedImage.style.opacity = '0';
        setTimeout(() => {
            annotatedImage.style.transition = 'opacity 1s';
            annotatedImage.style.opacity = '1';
        }, 300);
    }
    
    if (probabilityList) {
        probabilityList.innerHTML = '';
        const sortedProbs = Object.entries(data.probabilities)
            .sort((a, b) => b[1] - a[1]);
        
        sortedProbs.forEach(([className, prob], index) => {
            const item = document.createElement('div');
            item.className = 'detail-item';
            item.style.animation = `fadeInUp 0.5s ease-out ${index * 0.1}s both`;
            
            item.innerHTML = `
                <span class="detail-label">${className}</span>
                <span class="detail-value">${prob}%</span>
            `;
            probabilityList.appendChild(item);
        });
    }

    renderActionPlan(data.action_plan);
}

function renderActionPlan(actionPlan) {
    const section = document.getElementById('actionPlanSection');
    const content = document.getElementById('actionPlanContent');
    if (!section || !content) return;

    if (!actionPlan) {
        section.style.display = 'none';
        content.innerHTML = '';
        return;
    }

    const steps = (actionPlan.next_steps || []).map(step => `<li>${step}</li>`).join('');
    content.innerHTML = `
        <div><strong>紧急程度：</strong>${actionPlan.urgency || '中'}</div>
        <div><strong>预计收益：</strong>${actionPlan.expected_benefit || '待评估'}</div>
        <div><strong>下一步动作：</strong><ul style="margin: 8px 0 0 18px;">${steps}</ul></div>
        <div><strong>注意事项：</strong>${actionPlan.notes || '无'}</div>
    `;
    section.style.display = 'block';
}

// 重新上传
const resetBtn = document.getElementById('resetBtn');
if (resetBtn) {
    resetBtn.onclick = () => {
        if (fileInput) fileInput.value = '';
        if (previewSection) previewSection.style.display = 'none';
        if (resultSection) resultSection.style.display = 'none';
        if (uploadBtn) uploadBtn.style.display = 'none';
        const section = document.getElementById('actionPlanSection');
        const content = document.getElementById('actionPlanContent');
        if (section) section.style.display = 'none';
        if (content) content.innerHTML = '';
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };
}
