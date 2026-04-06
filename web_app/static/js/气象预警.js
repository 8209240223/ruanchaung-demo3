const createPlanBtn = document.getElementById('createPlanBtn');
const planResult = document.getElementById('planResult');
const planHistory = document.getElementById('planHistory');
const fetchWeatherBtn = document.getElementById('fetchWeatherBtn');
const weatherStatus = document.getElementById('weatherStatus');

let locationMap = null;
let locationMarker = null;

function initMap() {
    const el = document.getElementById('locationMap');
    if (!el || typeof L === 'undefined') return;
    locationMap = L.map('locationMap').setView([35, 105], 4);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        maxZoom: 19
    }).addTo(locationMap);
}

function showLocationOnMap(lat, lon, label) {
    if (!locationMap || typeof L === 'undefined') return;
    if (locationMarker) {
        locationMarker.remove();
    }
    locationMarker = L.marker([lat, lon]).addTo(locationMap);
    if (label) {
        locationMarker.bindPopup(label).openPopup();
    }
    locationMap.setView([lat, lon], 13);
}

if (createPlanBtn) {
    createPlanBtn.addEventListener('click', () => {
        createIrrigationPlan();
    });
}
if (fetchWeatherBtn) {
    fetchWeatherBtn.addEventListener('click', () => {
        fetchLocationAndWeather(true);
    });
}

document.addEventListener('DOMContentLoaded', () => {
    initMap();
    loadIrrigationHistory();
    // 进入页面时自动尝试获取定位与天气（不阻塞，用户可随时手动修改）
    fetchLocationAndWeather(false);
});

/**
 * 获取当前位置并请求天气，自动填充气温、降雨量；可选填充地块名称（逆地理）。
 * @param {boolean} isManual - 是否用户点击按钮触发（用于提示文案）
 */
function fetchLocationAndWeather(isManual) {
    const setStatus = (msg, isError = false) => {
        if (weatherStatus) {
            weatherStatus.textContent = msg;
            weatherStatus.style.color = isError ? '#ff6b6b' : 'var(--text-dim)';
        }
    };
    const fillWeatherInputs = (temp, rain) => {
        const tempEl = document.getElementById('temperature');
        const rainEl = document.getElementById('rainfall');
        if (temp != null && tempEl) {
            tempEl.value = Math.round(Number(temp) * 10) / 10;
        }
        if (rain != null && rainEl) {
            rainEl.value = Math.round(Number(rain) * 10) / 10;
        }
    };
    const fillPlotName = (name, title = '') => {
        const plotEl = document.getElementById('plotName');
        if (!plotEl || !name) return;
        plotEl.value = String(name);
        plotEl.title = title || '';
    };
    const estimateSoilMoisture = (temp, rain) => {
        // 经验估算：以 45% 为基线，降雨提高湿度，较高气温会加快蒸发而降低湿度
        const t = Number(temp);
        const r = Number(rain);
        const base = 45;
        const rainGain = 2.2 * (isNaN(r) ? 0 : r);
        const heatLoss = 0.9 * Math.max((isNaN(t) ? 22 : t) - 22, 0);
        const estimate = base + rainGain - heatLoss;
        return Math.max(25, Math.min(90, Math.round(estimate * 10) / 10));
    };
    const fillEstimatedSoilMoisture = (temp, rain, sourceText = '天气') => {
        const soilEl = document.getElementById('soilMoisture');
        if (!soilEl) return null;
        const estimated = estimateSoilMoisture(temp, rain);
        soilEl.value = estimated;
        soilEl.title = `估算依据：土壤湿度≈45 + 2.2×降雨(mm) - 0.9×max(气温-22,0)，并限制在25%~90%。数据源：${sourceText}`;
        return estimated;
    };
    const fetchWeatherByCoords = (lat, lon) => {
        const url = `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}&current=temperature_2m&daily=precipitation_sum&past_days=0&timezone=auto`;
        return fetch(url).then((res) => res.json());
    };
    const fallbackByIp = () => {
        return fetch('/api/weather_by_ip')
            .then((res) => res.json())
            .then((data) => {
                if (!data.success) {
                    throw new Error(data.error || 'IP 兜底失败');
                }
                const info = data.data || {};
                fillWeatherInputs(info.temperature, info.rainfall);
                const soil = fillEstimatedSoilMoisture(info.temperature, info.rainfall, 'IP定位天气');
                if (info.city) {
                    fillPlotName(info.city, `IP定位城市：${info.city}`);
                }
                if (info.latitude != null && info.longitude != null) {
                    showLocationOnMap(info.latitude, info.longitude, info.city ? `IP定位：${info.city}` : '当前位置');
                }
                setStatus(`地块 ${info.city || '当前城市'}，今日降水量 ${info.rainfall ?? 0} mm，气温 ${info.temperature ?? '-'}°C，土壤湿度估算 ${soil ?? '-'}%。`);
            });
    };

    if (isManual) {
        setStatus('正在获取定位与天气…');
    }

    if (!navigator.geolocation) {
        fallbackByIp().catch(() => {
            setStatus('您的浏览器不支持定位，且 IP 兜底失败，请手动填写气温与降雨量。', true);
        });
        return;
    }

    navigator.geolocation.getCurrentPosition(
        (position) => {
            const lat = position.coords.latitude;
            const lon = position.coords.longitude;
            if (isManual) setStatus('定位成功，正在获取天气…');

            fetchWeatherByCoords(lat, lon)
                .then((data) => {
                    const temp = data.current?.temperature_2m;
                    const rain = data.daily?.precipitation_sum?.[0];
                    fillWeatherInputs(temp, rain);
                    const soil = fillEstimatedSoilMoisture(temp, rain, 'GPS定位天气');
                    setStatus(`地块已填充，今日降水量 ${rain ?? 0} mm，气温 ${temp ?? '-'}°C，土壤湿度估算 ${soil ?? '-'}%。`);
                    showLocationOnMap(lat, lon, 'GPS定位');

                    // 逆地理：用 Nominatim 获取地点名称，可选填充地块名称
                    const nominatimUrl = `https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lon}&format=json`;
                    fetch(nominatimUrl, {
                        headers: { 'Accept-Language': 'zh-CN,zh;q=0.9', 'User-Agent': 'SmartAgriIrrigation/1.0' }
                    })
                        .then((r) => r.json())
                        .then((addr) => {
                            const city = addr.address?.city || addr.address?.town || addr.address?.village || addr.address?.county || addr.address?.state;
                            const name = addr.display_name?.split(',')[0] || city || '当前定位';
                            if (city || name) {
                                fillPlotName(city || name, '当前定位：' + (addr.display_name || ''));
                                if (locationMarker) locationMarker.setPopupContent(city || name);
                            }
                        })
                        .catch(() => { });
                })
                .catch((err) => {
                    fallbackByIp().catch(() => {
                        setStatus('天气获取失败，请手动填写气温与降雨量。' + (err.message ? ' ' + err.message : ''), true);
                    });
                });
        },
        () => {
            fallbackByIp().catch(() => {
                setStatus('定位不可用且 IP 兜底失败，请手动填写气温与降雨量。', true);
            });
        },
        { enableHighAccuracy: false, timeout: 15000, maximumAge: 600000 }
    );
}

function createIrrigationPlan() {
    const payload = {
        plot_name: document.getElementById('plotName')?.value?.trim() || 'A区',
        crop_type: document.getElementById('cropType')?.value?.trim() || '苹果',
        growth_stage: document.getElementById('growthStage')?.value || '结果期',
        soil_moisture: parseFloat(document.getElementById('soilMoisture')?.value || '52'),
        temperature: parseFloat(document.getElementById('temperature')?.value || '28'),
        rainfall: parseFloat(document.getElementById('rainfall')?.value || '2')
    };

    if (planResult) {
        planResult.innerHTML = '正在生成灌溉建议...';
    }

    fetch('/api/irrigation_plan', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-User-Role': 'agronomist'
        },
        body: JSON.stringify(payload)
    })
        .then(response => response.json())
        .then(data => {
            if (!planResult) return;
            if (!data.success) {
                planResult.innerHTML = `<div style="color:#ff6b6b;">生成失败：${data.error || '未知错误'}</div>`;
                return;
            }
            const plan = data.data;
            const priorityColor = plan.priority === '高' ? '#ff6b6b' : plan.priority === '中' ? '#ffc107' : '#00ff9d';
            planResult.innerHTML = `
            <div style="padding:12px; border-radius:12px; border:1px solid ${priorityColor}; background:rgba(255,255,255,0.03);">
                <div><strong>地块：</strong>${plan.plot_name}</div>
                <div><strong>作物：</strong>${plan.crop_type}（${plan.growth_stage}）</div>
                <div><strong>优先级：</strong><span style="color:${priorityColor}; font-weight:700;">${plan.priority}</span></div>
                <div><strong>建议流量：</strong>${plan.suggested_water_lpm} L/min</div>
                <div><strong>建议时长：</strong>${plan.suggested_duration_min} 分钟</div>
                <div><strong>建议说明：</strong>${plan.recommendation}</div>
            </div>
        `;
            loadIrrigationHistory();
        })
        .catch(error => {
            if (planResult) {
                planResult.innerHTML = `<div style="color:#ff6b6b;">请求失败：${error.message}</div>`;
            }
        });
}

function loadIrrigationHistory() {
    if (!planHistory) return;
    planHistory.innerHTML = '正在加载历史建议...';
    fetch('/api/irrigation_plan?limit=10')
        .then(response => response.json())
        .then(data => {
            if (!data.success || !data.data || !data.data.length) {
                planHistory.innerHTML = '<div style="color:var(--text-dim);">暂无历史建议</div>';
                return;
            }
            planHistory.innerHTML = data.data.map(item => `
                <div style="padding:10px; border-radius:10px; border:1px solid var(--glass-border); background:rgba(255,255,255,0.02);">
                    <div><strong>${item.plot_name}</strong> | ${item.crop_type} | ${item.priority}优先级</div>
                    <div style="font-size:0.9rem; color:var(--text-dim); margin-top:4px;">
                        ${item.suggested_water_lpm} L/min · ${item.suggested_duration_min} 分钟 · ${item.timestamp}
                    </div>
                </div>
            `).join('');
        })
        .catch(error => {
            planHistory.innerHTML = `<div style="color:#ff6b6b;">加载失败：${error.message}</div>`;
        });
}



