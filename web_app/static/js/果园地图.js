(function () {
    const btnLoad = document.getElementById('btnLoad');
    const btnPlan = document.getElementById('btnPlan');
    const btnReset = document.getElementById('btnReset');
    const btnRestart = document.getElementById('btnRestart');
    const missionNameEl = document.getElementById('missionName');
    const missionStatusEl = document.getElementById('missionStatus');
    const missionTickEl = document.getElementById('missionTick');
    const scoreTotalEl = document.getElementById('scoreTotal');
    const scoreDetailEl = document.getElementById('scoreDetail');
    const droneListEl = document.getElementById('droneList');
    const toggleZones = document.getElementById('toggleZones');
    const toggleObstacles = document.getElementById('toggleObstacles');
    const togglePaths = document.getElementById('togglePaths');

    const zoneColors = ['#20bf6b', '#26de81', '#2ecc71', '#55efc4', '#00b894', '#0fb9b1'];
    const pathColors = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6', '#1abc9c', '#e67e22', '#34495e', '#e91e63', '#00bcd4', '#8bc34a', '#ff5722'];
    let config = null;
    let state = null;
    let map = null;
    const overlays = {
        boundary: [],
        zones: [],
        obstacles: [],
        hangar: [],
        paths: [],
        dispatched_paths: [],
        drones: {},
        dispatched_drones: {}
    };
    let dispatchedTrajectories = [];
    let staticRendered = false;
    // 记录每条派出任务路径首次出现时间，用于纯 JS 端动画（与仿真无关）
    var dispatchedStartTimes = {};

    function fetchJson(url, options) {
        const opt = Object.assign({ cache: 'no-store' }, options || {});
        return fetch(url, opt).then(function (r) {
            return r.text().then(function (text) {
                try {
                    return JSON.parse(text);
                } catch (e) {
                    const head = String(text || '').trim().slice(0, 120);
                    throw new Error('接口返回非JSON(' + r.status + ')，可能后端未重启或接口不存在。响应开头: ' + head);
                }
            });
        });
    }

    function ensureAmapReady() {
        if (!window.AMap) {
            throw new Error('AMap 加载失败，请确认 Key 为 Web端(JS API) 且白名单含 127.0.0.1/localhost');
        }
    }

    function initMap(center) {
        ensureAmapReady();
        if (map) return;
        var satellite = new AMap.TileLayer.Satellite();
        var roadNet = new AMap.TileLayer.RoadNet();
        map = new AMap.Map('amapContainer', {
            zoom: 18,
            center: center,
            layers: [satellite, roadNet],
            viewMode: '2D'
        });
    }

    function cellToLngLat(x, y) {
        const ref = (config && config.geo_ref) || {};
        const originLng = Number(ref.origin_lng || 116.3975);
        const originLat = Number(ref.origin_lat || 39.9098);
        const cellMeter = Number(ref.cell_meter || 3.0);

        const metersX = x * cellMeter;
        const metersY = y * cellMeter;
        const dLat = metersY / 111320;
        const dLng = metersX / (111320 * Math.cos(originLat * Math.PI / 180));
        return [originLng + dLng, originLat - dLat];
    }

    function rectToPolygon(rect) {
        const x1 = rect[0], y1 = rect[1], x2 = rect[2], y2 = rect[3];
        return [
            cellToLngLat(x1, y1),
            cellToLngLat(x2 + 1, y1),
            cellToLngLat(x2 + 1, y2 + 1),
            cellToLngLat(x1, y2 + 1)
        ];
    }

    function zoneToPolygonLngLat(zone) {
        return zone.polygon_lnglat || rectToPolygon(zone.rect);
    }

    function obstacleToPolygonLngLat(obstacle) {
        return obstacle.polygon_lnglat || rectToPolygon(obstacle.rect);
    }

    function clearLayer(layerKey) {
        const list = overlays[layerKey] || [];
        list.forEach(function (o) { map.remove(o); });
        overlays[layerKey] = [];
    }

    function renderZones() {
        if (!map || !config) return;
        clearLayer('zones');
        if (!toggleZones.checked) return;
        (config.zones || []).forEach(function (z, idx) {
            const color = zoneColors[idx % zoneColors.length];
            const poly = new AMap.Polygon({
                path: zoneToPolygonLngLat(z),
                strokeColor: color,
                strokeWeight: 2,
                fillColor: color,
                fillOpacity: 0.28
            });
            const c = z.polygon_lnglat && z.polygon_lnglat[0] ? z.polygon_lnglat[0] : cellToLngLat((z.rect[0] + z.rect[2]) / 2, (z.rect[1] + z.rect[3]) / 2);
            const label = new AMap.Text({
                text: z.id + ' ' + z.name,
                position: c,
                style: {
                    background: 'rgba(0,0,0,0.4)',
                    border: 'none',
                    color: '#e8f8f5',
                    padding: '3px 6px',
                    borderRadius: '6px'
                }
            });
            overlays.zones.push(poly, label);
        });
        map.add(overlays.zones);
    }

    function renderObstacles() {
        if (!map || !config) return;
        clearLayer('obstacles');
        if (!toggleObstacles.checked) return;
        (config.obstacles || []).forEach(function (o) {
            const poly = new AMap.Polygon({
                path: obstacleToPolygonLngLat(o),
                strokeColor: '#ff7979',
                strokeWeight: 2,
                fillColor: '#a83a3a',
                fillOpacity: 0.42
            });
            overlays.obstacles.push(poly);
        });
        map.add(overlays.obstacles);
    }

    function renderHangar() {
        if (!map || !config) return;
        clearLayer('hangar');
        const path = config.hangar_polygon_lnglat || [];
        if (path.length < 3) return;
        const poly = new AMap.Polygon({
            path: path,
            strokeColor: '#3498db',
            strokeWeight: 3,
            fillColor: '#3498db',
            fillOpacity: 0.35
        });
        overlays.hangar.push(poly);
        const center = config.hangar_center;
        if (center && config.geo_ref) {
            const lnglat = cellToLngLat(center[0] + 0.5, center[1] + 0.5);
            const label = new AMap.Text({
                text: '无人机机库',
                position: lnglat,
                style: {
                    background: 'rgba(52,152,219,0.8)',
                    border: 'none',
                    color: '#fff',
                    padding: '4px 8px',
                    borderRadius: '6px'
                }
            });
            overlays.hangar.push(label);
        }
        map.add(overlays.hangar);
    }

    function renderPaths() {
        if (!map || !state) return;
        clearLayer('paths');
        if (!togglePaths.checked) return;
        const source = state.planned_paths_lnglat || {};
        const fallback = state.planned_paths || {};
        const tick = state.tick != null ? state.tick : 0;
        const drones = state.drones || [];
        const droneMap = {};
        drones.forEach(function (d) { droneMap[d.drone_id] = d; });
        const keys = (Object.keys(source).length ? Object.keys(source) : Object.keys(fallback)).sort();
        keys.forEach(function (droneId, idx) {
            const points = source[droneId] || [];
            const fullPath = points.length ? points : (fallback[droneId] || []).map(function (p) {
                return cellToLngLat(p[0] + 0.5, p[1] + 0.5);
            });
            if (fullPath.length < 2) return;
            const drone = droneMap[droneId];
            const endIdx = Math.min(tick, fullPath.length - 1);
            let pathToShow = fullPath.slice(0, endIdx + 1);
            if (drone && drone.position_lnglat) {
                pathToShow = pathToShow.concat([drone.position_lnglat]);
            }
            if (pathToShow.length < 2) return;
            const color = pathColors[idx % pathColors.length];
            const polyline = new AMap.Polyline({
                path: pathToShow,
                strokeColor: color,
                strokeWeight: 3,
                strokeOpacity: 0.9
            });
            overlays.paths.push(polyline);
        });
        map.add(overlays.paths);
    }

    function renderDispatchedPaths() {
        if (!map) return;
        clearLayer('dispatched_paths');
        if (!dispatchedTrajectories || !dispatchedTrajectories.length) return;
        const dispatchedColors = ['#ffc107', '#ff9800', '#ff5722', '#e91e63', '#00e5ff', '#76ff03'];
        const nowMs = Date.now();
        const TOTAL_ANIM_MS = 60000;  // 管理员派出无人机：60秒走完全程，飞行更慢

        dispatchedTrajectories.forEach(function (item, idx) {
            const fullPath = item.trajectory_lnglat || [];
            if (fullPath.length < 2) return;
            const key = item.task_id;

            if (!dispatchedStartTimes[key]) {
                dispatchedStartTimes[key] = nowMs;
            }
            const elapsed = nowMs - dispatchedStartTimes[key];
            const msPerStep = TOTAL_ANIM_MS / fullPath.length;
            const endIdx = Math.min(Math.floor(elapsed / msPerStep), fullPath.length - 1);
            const pathToShow = fullPath.slice(0, endIdx + 1);
            if (pathToShow.length < 2) return;

            const color = dispatchedColors[idx % dispatchedColors.length];
            const polylineDone = new AMap.Polyline({
                path: pathToShow,
                strokeColor: color,
                strokeWeight: 5,
                strokeOpacity: 0.95,
                lineJoin: 'round',
                lineCap: 'round'
            });
            overlays.dispatched_paths.push(polylineDone);

            if (endIdx < fullPath.length - 1) {
                const polylineRemain = new AMap.Polyline({
                    path: fullPath.slice(endIdx),
                    strokeColor: color,
                    strokeWeight: 2,
                    strokeOpacity: 0.25,
                    strokeStyle: 'dashed',
                    lineJoin: 'round'
                });
                overlays.dispatched_paths.push(polylineRemain);
            }
        });
        if (overlays.dispatched_paths.length) map.add(overlays.dispatched_paths);

        const activeKeys = dispatchedTrajectories.map(function (t) { return t.task_id; });
        Object.keys(dispatchedStartTimes).forEach(function (k) {
            if (activeKeys.indexOf(parseInt(k)) === -1) delete dispatchedStartTimes[k];
        });
    }

    function syncDroneMarkers() {
        if (!map || !state) return;
        const live = {};
        const liveDispatched = {};
        const dispatchedDroneIds = new Set(
            (dispatchedTrajectories || []).map(function (d) { return d.drone_id; })
        );

        (state.drones || []).forEach(function (d) {
            if (dispatchedDroneIds.has(d.drone_id)) {
                if (overlays.drones[d.drone_id]) {
                    map.remove(overlays.drones[d.drone_id]);
                    delete overlays.drones[d.drone_id];
                }
                return;
            }
            const pos = d.position_lnglat || cellToLngLat(d.position[0] + 0.5, d.position[1] + 0.5);
            live[d.drone_id] = true;
            // 根据状态选颜色：执行中→青色，返航中→橙色，已返航/已完成→灰色
            const simColors = {
                '执行中': { bg: 'rgba(0,230,255,0.92)', border: '#00bcd4', txt: '#000' },
                '返航中': { bg: 'rgba(255,152,0,0.92)', border: '#e65100', txt: '#000' },
                '已返航': { bg: 'rgba(120,120,120,0.8)', border: '#555', txt: '#fff' },
                '已完成': { bg: 'rgba(120,120,120,0.8)', border: '#555', txt: '#fff' }
            };
            const sc = simColors[d.status] || { bg: 'rgba(0,230,255,0.92)', border: '#00bcd4', txt: '#000' };
            const labelHtml = '<div style="background:' + sc.bg + ';color:' + sc.txt + ';padding:2px 7px;border-radius:6px;font-weight:800;font-size:12px;border:1.5px solid ' + sc.border + ';white-space:nowrap;">✈ ' + d.drone_id + '</div>';
            if (!overlays.drones[d.drone_id]) {
                overlays.drones[d.drone_id] = new AMap.Marker({
                    position: pos,
                    title: d.drone_id,
                    label: { content: labelHtml, direction: 'top', offset: new AMap.Pixel(0, -2) }
                });
                map.add(overlays.drones[d.drone_id]);
            } else {
                overlays.drones[d.drone_id].setPosition(pos);
                overlays.drones[d.drone_id].setLabel({ content: labelHtml, direction: 'top', offset: new AMap.Pixel(0, -2) });
            }
        });

        // 管理员派出任务无人机（UAV-xx，黄色标签）
        const TOTAL_ANIM_MS2 = 60000;
        (dispatchedTrajectories || []).forEach(function (d) {
            if (!d.trajectory_lnglat || !d.trajectory_lnglat.length) return;
            const key = d.task_id;
            const nowMs2 = Date.now();
            const t0 = dispatchedStartTimes[key] || nowMs2;
            const msPerStep2 = TOTAL_ANIM_MS2 / d.trajectory_lnglat.length;
            const idx2 = Math.min(Math.floor((nowMs2 - t0) / msPerStep2), d.trajectory_lnglat.length - 1);
            const pos = d.trajectory_lnglat[idx2];
            if (!pos) return;
            const droneId = d.drone_id;
            liveDispatched[droneId] = true;
            const labelHtml2 = '<div style="background:rgba(255,193,7,0.92);color:#000;padding:2px 7px;border-radius:6px;font-weight:800;font-size:12px;border:1.5px solid #ff9800;white-space:nowrap;">✈ ' + droneId + '</div>';
            if (!overlays.dispatched_drones[droneId]) {
                overlays.dispatched_drones[droneId] = new AMap.Marker({
                    position: pos,
                    title: droneId + ' (执行任务中)',
                    label: { content: labelHtml2, direction: 'top', offset: new AMap.Pixel(0, -2) }
                });
                map.add(overlays.dispatched_drones[droneId]);
            } else {
                overlays.dispatched_drones[droneId].setPosition(pos);
            }
        });

        Object.keys(overlays.drones).forEach(function (droneId) {
            if (!live[droneId]) {
                map.remove(overlays.drones[droneId]);
                delete overlays.drones[droneId];
            }
        });
        Object.keys(overlays.dispatched_drones).forEach(function (droneId) {
            if (!liveDispatched[droneId]) {
                map.remove(overlays.dispatched_drones[droneId]);
                delete overlays.dispatched_drones[droneId];
            }
        });
    }

    function renderBoundary() {
        if (!map || !config) return;
        clearLayer('boundary');
        const boundary = config.boundary_polygon_lnglat || [];
        if (boundary.length < 3) return;
        const poly = new AMap.Polygon({
            path: boundary,
            strokeColor: '#f5cd79',
            strokeWeight: 3,
            fillOpacity: 0.0
        });
        overlays.boundary.push(poly);
        map.add(poly);
    }

    function renderStaticLayers() {
        if (!map || !config) return;
        renderBoundary();
        renderZones();
        renderObstacles();
        renderHangar();
        staticRendered = true;
    }

    function renderMap() {
        if (!map || !config) return;
        if (!staticRendered) {
            renderStaticLayers();
        }
        renderPaths();
        renderDispatchedPaths();
        syncDroneMarkers();
    }

    function updateRightPanel(snapshot) {
        if (!snapshot) return;
        missionNameEl.textContent = snapshot.mission_name || '未启动';
        missionStatusEl.textContent = snapshot.status || 'idle';
        missionTickEl.textContent = snapshot.tick != null ? snapshot.tick : '-';
        const scores = snapshot.scores || {};
        scoreTotalEl.textContent = scores.total != null ? scores.total : '-';
        scoreDetailEl.textContent = (scores.total != null)
            ? ('效率/能耗/均衡：' + scores.efficiency + ' / ' + scores.energy + ' / ' + scores.balance)
            : '效率/能耗/均衡：-';

        const drones = snapshot.drones || [];
        if (!drones.length) {
            droneListEl.innerHTML = '<div class="drone-item"><div><strong>无人机起飞中…</strong></div><div class="mini">正在加载无人机状态，请稍候</div></div>';
            return;
        }
        droneListEl.innerHTML = drones.map(function (d) {
            const cls = (d.status === '已完成' || d.status === '已返航') ? 'status-ok' : (d.status === '执行中' || d.status === '返航中' ? 'status-run' : 'status-stop');
            return '<div class="drone-item">' +
                '<div><strong>' + d.drone_id + '</strong> <span class="' + cls + '">' + d.status + '</span></div>' +
                '<div class="mini">分区: ' + ((d.zone_ids || []).join(',') || '-') + '</div>' +
                '<div class="mini">位置: (' + Number(d.position[0]).toFixed(1) + ', ' + Number(d.position[1]).toFixed(1) + ')</div>' +
                '<div class="mini">电量: ' + Number(d.battery).toFixed(1) + '%  速度: ' + Number(d.speed).toFixed(1) + 'm/s</div>' +
                '</div>';
        }).join('');
    }

    var applePopupDismissTimer = null;
    var diseasePopupDismissTimer = null;
    var lastAppleSig = '';
    var lastDiseaseSig = '';
    var lastAppleShowAt = 0;
    var lastDiseaseShowAt = 0;
    var appleCycleIdx = 0;
    var diseaseCycleIdx = 0;

    function showPopup(el, dismissMs, which) {
        if (!el) return;
        el.classList.remove('hidden');
        var timerRef = which === 'apple' ? applePopupDismissTimer : diseasePopupDismissTimer;
        if (timerRef) clearTimeout(timerRef);
        timerRef = setTimeout(function () {
            el.classList.add('hidden');
            if (which === 'apple') applePopupDismissTimer = null;
            else diseasePopupDismissTimer = null;
        }, dismissMs);
        if (which === 'apple') applePopupDismissTimer = timerRef;
        else diseasePopupDismissTimer = timerRef;
    }

    function updateApplePopup(snapshot) {
        var el = document.getElementById('applePopup');
        if (!el) return;
        var status = (snapshot && snapshot.status) || '';
        if (!(status === 'running' || status === 'returning')) {
            el.classList.add('hidden');
            return;
        }
        var ad = (snapshot && snapshot.apple_detection) || {};
        var imm = ad.immature || 0, mat = ad.mature || 0, over = ad.overripe || 0;
        var logs = ad.logs || [];
        document.getElementById('appleImmature').textContent = imm;
        document.getElementById('appleMature').textContent = mat;
        document.getElementById('appleOverripe').textContent = over;
        var logsEl = document.getElementById('appleLogs');
        logsEl.innerHTML = logs.slice(0, 5).map(function (l) {
            return '<div class="log-item"><span class="time">[' + (l.time || '') + ']</span>' + (l.message || '') + '</div>';
        }).join('');

        var nowMs = Date.now();
        var head = logs[0] || null;
        var sig = head ? ((head.time || '') + '|' + (head.message || '')) : '';
        var hasNew = sig && sig !== lastAppleSig;
        if (hasNew) {
            lastAppleSig = sig;
            lastAppleShowAt = nowMs;
            showPopup(el, 12000, 'apple');
            return;
        }

        // 轮播机制：没有新日志时，也按间隔弹出一次（避免“弹两条就没了”）
        if (!logs.length) return;
        // 加快苹果成熟度弹窗频率
        var intervalMs = 3500;
        if (nowMs - lastAppleShowAt < intervalMs) return;
        // 仅在弹窗当前隐藏时轮播（防止一直霸屏）
        if (!el.classList.contains('hidden')) return;
        appleCycleIdx = (appleCycleIdx + 1) % Math.min(logs.length, 5);
        var item = logs[appleCycleIdx] || logs[0];
        var cycSig = (item.time || '') + '|' + (item.message || '') + '|idx=' + appleCycleIdx;
        if (cycSig === lastAppleSig) return;
        lastAppleSig = cycSig;
        lastAppleShowAt = nowMs;
        showPopup(el, 10000, 'apple');
    }

    function updateDiseasePopup(snapshot) {
        var el = document.getElementById('diseasePopup');
        if (!el) return;
        var status = (snapshot && snapshot.status) || '';
        if (!(status === 'running' || status === 'returning')) {
            el.classList.add('hidden');
            return;
        }
        var dd = (snapshot && snapshot.disease_detection) || {};
        var leaf = dd.leaf || 0, fruit = dd.fruit || 0;
        var high = dd.high || 0, med = dd.medium || 0, low = dd.low || 0;
        var logs = dd.logs || [];
        document.getElementById('diseaseLeaf').textContent = leaf;
        document.getElementById('diseaseFruit').textContent = fruit;
        document.getElementById('diseaseHigh').textContent = high;
        document.getElementById('diseaseMedium').textContent = med;
        document.getElementById('diseaseLow').textContent = low;
        var logsEl = document.getElementById('diseaseLogs');
        logsEl.innerHTML = logs.slice(0, 5).map(function (l) {
            return '<div class="log-item"><span class="time">[' + (l.time || '') + ']</span>' + (l.message || '') + '</div>';
        }).join('');

        var nowMs = Date.now();
        // 第一次拿到日志就先弹一次，保证能看到病虫害消息
        if (logs.length && !lastDiseaseShowAt) {
            lastDiseaseSig = ((logs[0].time || '') + '|' + (logs[0].message || ''));
            lastDiseaseShowAt = nowMs;
            showPopup(el, 14000, 'disease');
            return;
        }
        var head = logs[0] || null;
        var sig = head ? ((head.time || '') + '|' + (head.message || '')) : '';
        var hasNew = sig && sig !== lastDiseaseSig;
        if (hasNew) {
            lastDiseaseSig = sig;
            lastDiseaseShowAt = nowMs;
            showPopup(el, 14000, 'disease');
            return;
        }

        if (!logs.length) return;
        // 更快的轮播弹出频率
        var intervalMs = 9000;
        if (nowMs - lastDiseaseShowAt < intervalMs) return;
        if (!el.classList.contains('hidden')) return;
        diseaseCycleIdx = (diseaseCycleIdx + 1) % Math.min(logs.length, 5);
        var item = logs[diseaseCycleIdx] || logs[0];
        var cycSig = (item.time || '') + '|' + (item.message || '') + '|idx=' + diseaseCycleIdx;
        if (cycSig === lastDiseaseSig) return;
        lastDiseaseSig = cycSig;
        lastDiseaseShowAt = nowMs;
        showPopup(el, 11000, 'disease');
    }

    var fastPollTimer = null;
    var steadyPollTimer = null;
    var lastOrchardStatus = '';

    // 自定义美化弹窗系统
    function showCustomAlert(title, content) {
        return new Promise((resolve) => {
            let overlay = document.getElementById('customModalOverlay');
            if (!overlay) {
                overlay = document.createElement('div');
                overlay.id = 'customModalOverlay';
                overlay.className = 'custom-modal-overlay';
                document.body.appendChild(overlay);
            }
            overlay.innerHTML = `
            <div class="custom-modal-card">
                <div class="custom-modal-title"><span>🔔</span> ${title}</div>
                <div class="custom-modal-content">${content}</div>
                <div class="custom-modal-actions">
                    <button class="btn-modal btn-modal-primary" id="customModalOk">确定</button>
                </div>
            </div>
        `;
            overlay.classList.add('active');
            document.getElementById('customModalOk').onclick = () => {
                overlay.classList.remove('active');
                setTimeout(() => resolve(), 300);
            };
        });
    }

    function showCustomConfirm(title, content, okText = '确定', cancelText = '取消') {
        return new Promise((resolve) => {
            let overlay = document.getElementById('customModalOverlay');
            if (!overlay) {
                overlay = document.createElement('div');
                overlay.id = 'customModalOverlay';
                overlay.className = 'custom-modal-overlay';
                document.body.appendChild(overlay);
            }
            overlay.innerHTML = `
            <div class="custom-modal-card">
                <div class="custom-modal-title"><span>❓</span> ${title}</div>
                <div class="custom-modal-content">${content}</div>
                <div class="custom-modal-actions">
                    <button class="btn-modal btn-modal-secondary" id="customModalCancel">${cancelText}</button>
                    <button class="btn-modal btn-modal-primary" id="customModalOk">${okText}</button>
                </div>
            </div>
        `;
            overlay.classList.add('active');
            document.getElementById('customModalCancel').onclick = () => {
                overlay.classList.remove('active');
                setTimeout(() => resolve(false), 300);
            };
            document.getElementById('customModalOk').onclick = () => {
                overlay.classList.remove('active');
                setTimeout(() => resolve(true), 300);
            };
        });
    }

    function pollState() {
        fetchJson('/api/orchard/state')
            .then(async function (res) {
                if (!res || !res.success) return;
                var prev = lastOrchardStatus;
                state = res.data;
                lastOrchardStatus = state.status || '';
                updateRightPanel(state);
                updateApplePopup(state);
                updateDiseasePopup(state);
                renderMap();
                // 无人机全部返航后提示跳转任务规划
                if ((prev === 'running' || prev === 'returning') && lastOrchardStatus === 'completed') {
                    const confirmed = await showCustomConfirm('采集完成', '飞行数据已采集完成，是否跳转到任务规划生成任务？', '立即前往', '留在地图');
                    if (confirmed) {
                        window.location.href = '/任务规划';
                    }
                }
            })
            .catch(function () { });
    }

    function pollDispatchedTrajectories() {
        fetch('/api/orchard/dispatched_trajectories', { cache: 'no-store' })
            .then(function (r) { return r.json(); })
            .then(function (res) {
                if (res && res.success && Array.isArray(res.data)) {
                    dispatchedTrajectories = res.data;
                    // 只更新派出任务轨迹，避免全量重绘造成卡顿
                    if (map) renderDispatchedPaths();
                }
            })
            .catch(function () { });
    }

    function startFastPoll() {
        if (fastPollTimer) return;
        var count = 0;
        function fastPoll() {
            pollState();
            count++;
            if (count < 120 && state && (state.status === 'running' || state.status === 'returning')) {
                fastPollTimer = setTimeout(fastPoll, 200);
            } else {
                fastPollTimer = null;
            }
        }
        fastPoll();
    }

    function ensureSteadyPoll() {
        if (steadyPollTimer) return;
        steadyPollTimer = setInterval(function () {
            if (state && (state.status === 'running' || state.status === 'returning')) {
                pollState();
            }
        }, 600);
    }

    function loadConfig() {
        fetchJson('/api/orchard/config')
            .then(function (res) {
                if (!res.success) return;
                config = res.data;
                staticRendered = false;
                const boundary = config.boundary_polygon_lnglat || [];
                const grid = config.grid || { width: 80, height: 60 };
                const center = boundary.length ? boundary[0] : cellToLngLat(grid.width / 2, grid.height / 2);
                initMap(center);
                renderMap();
                if (boundary.length) {
                    map.setFitView(overlays.boundary.concat(overlays.zones).concat(overlays.obstacles).concat(overlays.hangar), false, [40, 40, 40, 40], 17);
                }
                pollState();
                pollDispatchedTrajectories();
            })
            .catch(function (e) {
                showCustomAlert('加载失败', '加载地图配置失败: ' + e.message);
            });
    }

    btnLoad.addEventListener('click', loadConfig);
    btnPlan.addEventListener('click', function () {
        if (!map) {
            fetchJson('/api/orchard/config').then(function (res) {
                if (res.success) {
                    config = res.data;
                    staticRendered = false;
                    var boundary = config.boundary_polygon_lnglat || [];
                    var grid = config.grid || { width: 80, height: 60 };
                    var center = boundary.length ? boundary[0] : [120.808, 37.361];
                    initMap(center);
                    renderMap();
                    if (boundary.length) {
                        map.setFitView(overlays.boundary.concat(overlays.zones).concat(overlays.obstacles).concat(overlays.hangar), false, [40, 40, 40, 40], 17);
                    }
                }
                triggerPlan();
            }).catch(function () { triggerPlan(); });
        } else {
            triggerPlan();
        }
    });

    function triggerPlan() {
        btnPlan.disabled = true;
        missionStatusEl.textContent = '起飞中';
        droneListEl.innerHTML = '<div class="drone-item"><div><strong>无人机起飞中…</strong></div><div class="mini">正在生成最优巡查路径</div></div>';
        fetchJson('/api/orchard/plan', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-User-Role': 'operator' },
            body: JSON.stringify({ mission_name: '果园多机协同巡检' })
        }).then(function (res) {
            if (res.success) {
                state = state || {};
                state.planned_paths = res.data.planned_paths || {};
                state.planned_paths_lnglat = res.data.planned_paths_lnglat || {};
                state.mission_name = res.data.mission_name;
                state.status = 'running';
                state.tick = 0;
                if (!map) {
                    var center = (config && config.boundary_polygon_lnglat && config.boundary_polygon_lnglat[0]) || [120.808, 37.361];
                    initMap(center);
                }
                pollState();
                startFastPoll();
                ensureSteadyPoll();
            } else {
                showCustomAlert('规划失败', res.error || '规划失败');
            }
        }).catch(function (e) {
            showCustomAlert('请求失败', '请求失败: ' + e.message);
            pollState();
        }).finally(function () {
            btnPlan.disabled = false;
        });
    }

    btnReset.addEventListener('click', function () {
        btnReset.disabled = true;
        fetchJson('/api/orchard/rtb', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-User-Role': 'operator' },
            body: JSON.stringify({})
        }).then(function (res) {
            if (res.success) {
                pollState();
            } else {
                showCustomAlert('返航失败', res.error || '返航失败');
            }
        }).catch(function (e) {
            showCustomAlert('请求失败', '请求失败: ' + e.message);
        }).finally(function () {
            btnReset.disabled = false;
        });
    });

    if (btnRestart) {
        btnRestart.addEventListener('click', function () {
            btnRestart.disabled = true;
            fetchJson('/api/orchard/reset', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-User-Role': 'operator' },
                body: JSON.stringify({})
            }).then(function (res) {
                if (res.success) {
                    pollState();
                } else {
                    showCustomAlert('重置失败', res.error || '重置失败');
                }
            }).catch(function (e) {
                showCustomAlert('请求失败', '请求失败: ' + e.message);
            }).finally(function () {
                btnRestart.disabled = false;
            });
        });
    }

    [toggleZones, toggleObstacles, togglePaths].forEach(function (el) {
        el.addEventListener('change', function () {
            // 静态图层（边界/分区/障碍/机库）只在需要时重绘，避免频繁重绘导致卡顿/闪回
            staticRendered = false;
            renderMap();
        });
    });

    if (window.io) {
        const socket = io({ transports: ['polling'] });
        socket.on('connect', function () {
            socket.emit('orchard_subscribe');
        });
        socket.on('orchard_state', function (payload) {
            if (!payload || !payload.success) return;
            state = payload.data;
            updateRightPanel(state);
            updateApplePopup(state);
            updateDiseasePopup(state);
            renderMap();
        });
    }

    try {
        ensureAmapReady();
        loadConfig();
        // 每 2 秒从后端刷新一次派出任务列表
        setInterval(pollDispatchedTrajectories, 2000);
        // 高频动画帧：每 250ms 重绘一次派出路径 + 无人机位置，实现平滑飞行动画
        setInterval(function () {
            if (map && dispatchedTrajectories && dispatchedTrajectories.length) {
                renderDispatchedPaths();
                syncDroneMarkers();
            }
        }, 250);
        ensureSteadyPoll();
    } catch (e) {
        showCustomAlert('初始化失败', '高德地图初始化失败：' + e.message);
    }
})();
