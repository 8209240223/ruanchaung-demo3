/**
 * 农业 AI 助手：拖动、图片、语音（Web Speech API）
 */
(function () {
  'use strict';

  var root = document.getElementById('agri-assistant-widget');
  if (!root) return;

  var fab = document.getElementById('agri-asst-fab');
  var panel = document.getElementById('agri-asst-panel');
  var head = document.querySelector('.agri-asst-head');
  var closeBtn = document.getElementById('agri-asst-close');
  var messagesEl = document.getElementById('agri-asst-messages');
  var input = document.getElementById('agri-asst-input');
  var sendBtn = document.getElementById('agri-asst-send');
  var fileInput = document.getElementById('agri-asst-file');
  var imgBtn = document.getElementById('agri-asst-img');
  var micBtn = document.getElementById('agri-asst-mic');
  var previewWrap = document.getElementById('agri-asst-preview');
  var previewImg = document.getElementById('agri-asst-preview-img');
  var previewRemove = document.getElementById('agri-asst-preview-remove');

  var history = [];
  var pendingImage = null;
  var tx = 0;
  var ty = 0;
  var dragState = null;
  var fabPointer = null;
  var recognition = null;
  var listening = false;
  var resizeState = null;
  var RESIZE_MIN_W = 280;
  var RESIZE_MIN_H = 320;

  function setOpen(open) {
    root.classList.toggle('agri-asst--open', open);
    if (fab) fab.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (open && input) {
      setTimeout(function () {
        input.focus();
      }, 120);
    }
  }

  function applyTransform() {
    root.style.setProperty('--asst-tx', tx + 'px');
    root.style.setProperty('--asst-ty', ty + 'px');
  }

  function clampToViewport() {
    var el = root.classList.contains('agri-asst--open') ? panel : fab;
    if (!el) return;
    applyTransform();
    var r = el.getBoundingClientRect();
    var pad = 8;
    if (r.left < pad) tx += pad - r.left;
    if (r.right > window.innerWidth - pad) tx -= r.right - (window.innerWidth - pad);
    if (r.top < pad) ty += pad - r.top;
    if (r.bottom > window.innerHeight - pad) ty -= r.bottom - (window.innerHeight - pad);
    applyTransform();
  }

  function onDragStart(clientX, clientY, target) {
    if (target && target.closest && target.closest('.agri-asst-close')) return;
    if (target && target.closest && target.closest('.agri-asst-resize')) return;
    dragState = { lastX: clientX, lastY: clientY };
    if (head) head.style.cursor = 'grabbing';
  }

  function onDragMove(clientX, clientY) {
    if (!dragState) return;
    var dx = clientX - dragState.lastX;
    var dy = clientY - dragState.lastY;
    dragState.lastX = clientX;
    dragState.lastY = clientY;
    tx += dx;
    ty += dy;
    clampToViewport();
  }

  function onDragEnd() {
    if (dragState) {
      dragState = null;
      if (head) head.style.cursor = 'grab';
    }
  }

  function getMaxPanelSize() {
    return {
      w: Math.min(window.innerWidth - 24, 900),
      h: window.innerHeight - 72,
    };
  }

  function applyPanelSize(w, h) {
    if (!panel) return;
    var max = getMaxPanelSize();
    w = Math.max(RESIZE_MIN_W, Math.min(max.w, w));
    h = Math.max(RESIZE_MIN_H, Math.min(max.h, h));
    panel.style.width = Math.round(w) + 'px';
    panel.style.height = Math.round(h) + 'px';
    panel.style.maxWidth = 'none';
    panel.style.maxHeight = 'none';
  }

  function onResizeMove(clientX, clientY) {
    if (!resizeState || !panel) return;
    var dx = clientX - resizeState.lastX;
    var dy = clientY - resizeState.lastY;
    resizeState.lastX = clientX;
    resizeState.lastY = clientY;
    var w = resizeState.w;
    var h = resizeState.h;
    var d = resizeState.dir;
    if (d.indexOf('e') >= 0) w += dx;
    if (d.indexOf('w') >= 0) w -= dx;
    if (d.indexOf('s') >= 0) h += dy;
    if (d.indexOf('n') >= 0) h -= dy;
    applyPanelSize(w, h);
    var rw = parseFloat(panel.style.width);
    var rh = parseFloat(panel.style.height);
    if (!isNaN(rw)) resizeState.w = rw;
    if (!isNaN(rh)) resizeState.h = rh;
    clampToViewport();
  }

  function onResizeEnd() {
    if (!resizeState) return;
    resizeState = null;
    if (panel) panel.classList.remove('agri-asst-panel--resizing');
  }

  function bindResizeHandle(el) {
    el.addEventListener('mousedown', function (e) {
      if (!panel || !root.classList.contains('agri-asst--open')) return;
      if (e.button !== 0) return;
      e.stopPropagation();
      e.preventDefault();
      var dir = el.getAttribute('data-dir');
      if (!dir) return;
      var r = panel.getBoundingClientRect();
      resizeState = {
        dir: dir,
        lastX: e.clientX,
        lastY: e.clientY,
        w: r.width,
        h: r.height,
      };
      panel.classList.add('agri-asst-panel--resizing');
    });
    el.addEventListener(
      'touchstart',
      function (ev) {
        if (!panel || !root.classList.contains('agri-asst--open')) return;
        if (ev.touches.length !== 1) return;
        ev.stopPropagation();
        ev.preventDefault();
        var t = ev.touches[0];
        var dir = el.getAttribute('data-dir');
        if (!dir) return;
        var r = panel.getBoundingClientRect();
        resizeState = {
          dir: dir,
          lastX: t.clientX,
          lastY: t.clientY,
          w: r.width,
          h: r.height,
        };
        panel.classList.add('agri-asst-panel--resizing');
      },
      { passive: false }
    );
  }

  function createResizeHandles() {
    if (!panel || panel.querySelector('.agri-asst-resize')) return;
    var dirs = ['n', 's', 'e', 'w', 'nw', 'ne', 'sw', 'se'];
    dirs.forEach(function (d) {
      var el = document.createElement('div');
      el.className = 'agri-asst-resize agri-asst-resize--' + d;
      el.setAttribute('data-dir', d);
      el.setAttribute('aria-hidden', 'true');
      el.title = '拖动调整窗口大小';
      bindResizeHandle(el);
      panel.appendChild(el);
    });
  }

  createResizeHandles();

  if (head) {
    head.addEventListener('mousedown', function (e) {
      if (e.button !== 0) return;
      onDragStart(e.clientX, e.clientY, e.target);
      e.preventDefault();
    });
  }

  document.addEventListener('mousemove', function (e) {
    if (resizeState) onResizeMove(e.clientX, e.clientY);
    if (dragState) onDragMove(e.clientX, e.clientY);
    if (fabPointer) {
      var dx = e.clientX - fabPointer.x;
      var dy = e.clientY - fabPointer.y;
      if (Math.abs(dx) + Math.abs(dy) > 6) fabPointer.moved = true;
      if (fabPointer.moved) {
        tx += e.clientX - fabPointer.lastX;
        ty += e.clientY - fabPointer.lastY;
        fabPointer.lastX = e.clientX;
        fabPointer.lastY = e.clientY;
        clampToViewport();
      }
    }
  });

  document.addEventListener('mouseup', function () {
    onResizeEnd();
    onDragEnd();
    if (fabPointer) {
      var shouldOpen = !fabPointer.moved;
      fabPointer = null;
      if (shouldOpen && fab && !root.classList.contains('agri-asst--open')) {
        setOpen(true);
      }
    }
  });

  head &&
    head.addEventListener(
      'touchstart',
      function (e) {
        if (e.touches.length !== 1) return;
        var t = e.target;
        if (t.closest && t.closest('.agri-asst-close')) return;
        if (t.closest && t.closest('.agri-asst-resize')) return;
        var c = e.touches[0];
        onDragStart(c.clientX, c.clientY, t);
      },
      { passive: true }
    );

  document.addEventListener(
    'touchmove',
    function (e) {
      if (resizeState && e.touches.length === 1) {
        var cr = e.touches[0];
        onResizeMove(cr.clientX, cr.clientY);
        e.preventDefault();
        return;
      }
      if (!dragState || e.touches.length !== 1) return;
      var c = e.touches[0];
      onDragMove(c.clientX, c.clientY);
    },
    { passive: false }
  );

  document.addEventListener('touchend', function () {
    onResizeEnd();
    onDragEnd();
  });

  if (fab) {
    fab.addEventListener('mousedown', function (e) {
      if (e.button !== 0) return;
      if (root.classList.contains('agri-asst--open')) return;
      fabPointer = { x: e.clientX, y: e.clientY, lastX: e.clientX, lastY: e.clientY, moved: false };
      e.preventDefault();
    });
    fab.addEventListener(
      'touchstart',
      function (e) {
        if (root.classList.contains('agri-asst--open')) return;
        if (e.touches.length !== 1) return;
        var c = e.touches[0];
        fabPointer = { x: c.clientX, y: c.clientY, lastX: c.clientX, lastY: c.clientY, moved: false };
      },
      { passive: true }
    );
    fab.addEventListener(
      'touchmove',
      function (e) {
        if (!fabPointer || root.classList.contains('agri-asst--open')) return;
        if (e.touches.length !== 1) return;
        var c = e.touches[0];
        var dx = c.clientX - fabPointer.x;
        var dy = c.clientY - fabPointer.y;
        if (Math.abs(dx) + Math.abs(dy) > 6) fabPointer.moved = true;
        if (fabPointer.moved) {
          tx += c.clientX - fabPointer.lastX;
          ty += c.clientY - fabPointer.lastY;
          fabPointer.lastX = c.clientX;
          fabPointer.lastY = c.clientY;
          clampToViewport();
        }
      },
      { passive: true }
    );
    fab.addEventListener('touchend', function () {
      if (!fabPointer) return;
      var shouldOpen = !fabPointer.moved;
      fabPointer = null;
      if (shouldOpen) setOpen(true);
    });
  }

  if (closeBtn) {
    closeBtn.addEventListener('mousedown', function (e) {
      e.stopPropagation();
    });
    closeBtn.addEventListener('touchstart', function (e) {
      e.stopPropagation();
    });
    closeBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      e.preventDefault();
      if (listening) stopListen();
      setOpen(false);
    });
  }

  window.addEventListener('resize', function () {
    if (panel && panel.style.width && panel.style.height) {
      applyPanelSize(parseFloat(panel.style.width) || RESIZE_MIN_W, parseFloat(panel.style.height) || RESIZE_MIN_H);
    }
    clampToViewport();
  });

  function appendBubble(role, text, extraClass) {
    var div = document.createElement('div');
    div.className = 'agri-asst-msg agri-asst-msg--' + role + (extraClass ? ' ' + extraClass : '');
    div.textContent = text;
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return div;
  }

  function appendUserBubbleWithImage(text, dataUrl) {
    var div = document.createElement('div');
    div.className = 'agri-asst-msg agri-asst-msg--user';
    if (text) {
      var t = document.createElement('div');
      t.textContent = text;
      div.appendChild(t);
    }
    if (dataUrl) {
      var im = document.createElement('img');
      im.className = 'agri-asst-msg__img';
      im.src = dataUrl;
      im.alt = '上传配图';
      div.appendChild(im);
    }
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return div;
  }

  function clearPendingImage() {
    pendingImage = null;
    if (previewWrap) previewWrap.classList.remove('agri-asst-preview--on');
    if (previewImg) previewImg.removeAttribute('src');
    if (fileInput) fileInput.value = '';
  }

  function setPendingFromDataUrl(dataUrl, mime) {
    pendingImage = { dataUrl: dataUrl, mime: mime || 'image/jpeg' };
    if (previewImg) previewImg.src = dataUrl;
    if (previewWrap) previewWrap.classList.add('agri-asst-preview--on');
  }

  function compressImageToJpeg(file, callback) {
    var url = URL.createObjectURL(file);
    var img = new Image();
    img.onload = function () {
      URL.revokeObjectURL(url);
      var maxSide = 1280;
      var w = img.naturalWidth;
      var h = img.naturalHeight;
      if (!w || !h) {
        callback(null);
        return;
      }
      var scale = Math.min(1, maxSide / Math.max(w, h));
      var cw = Math.round(w * scale);
      var ch = Math.round(h * scale);
      var canvas = document.createElement('canvas');
      canvas.width = cw;
      canvas.height = ch;
      var ctx = canvas.getContext('2d');
      if (!ctx) {
        callback(null);
        return;
      }
      ctx.drawImage(img, 0, 0, cw, ch);
      try {
        var jpeg = canvas.toDataURL('image/jpeg', 0.82);
        callback(jpeg);
      } catch (_e) {
        callback(null);
      }
    };
    img.onerror = function () {
      URL.revokeObjectURL(url);
      callback(null);
    };
    img.src = url;
  }

  if (imgBtn && fileInput) {
    imgBtn.addEventListener('click', function () {
      fileInput.click();
    });
    fileInput.addEventListener('change', function () {
      var f = fileInput.files && fileInput.files[0];
      if (!f || !f.type.indexOf || f.type.indexOf('image') !== 0) return;
      compressImageToJpeg(f, function (dataUrl) {
        if (!dataUrl) {
          appendBubble('bot', '无法读取图片，请换一张试试。');
          return;
        }
        setPendingFromDataUrl(dataUrl, 'image/jpeg');
      });
    });
  }

  if (previewRemove) {
    previewRemove.addEventListener('click', function () {
      clearPendingImage();
    });
  }

  function getSpeechRecognition() {
    return window.SpeechRecognition || window.webkitSpeechRecognition;
  }

  function stopListen() {
    listening = false;
    if (micBtn) micBtn.classList.remove('agri-asst-tool--active');
    try {
      if (recognition) recognition.stop();
    } catch (_e) { }
  }

  if (micBtn) {
    micBtn.addEventListener('click', function () {
      var SR = getSpeechRecognition();
      if (!SR) {
        appendBubble('bot', '当前浏览器不支持语音识别，请使用 Chrome / Edge 桌面版，并允许麦克风权限。');
        return;
      }
      if (listening) {
        stopListen();
        return;
      }
      recognition = new SR();
      recognition.lang = 'zh-CN';
      recognition.interimResults = false;
      recognition.maxAlternatives = 1;
      recognition.continuous = false;
      listening = true;
      micBtn.classList.add('agri-asst-tool--active');
      recognition.onresult = function (ev) {
        var t = '';
        if (ev.results && ev.results[0] && ev.results[0][0]) {
          t = ev.results[0][0].transcript || '';
        }
        if (t && input) {
          input.value = (input.value ? input.value + ' ' : '') + t.trim();
        }
        stopListen();
      };
      recognition.onerror = function () {
        stopListen();
        appendBubble('bot', '语音识别失败，请检查麦克风权限或稍后重试。');
      };
      recognition.onend = function () {
        stopListen();
      };
      try {
        recognition.start();
      } catch (_e2) {
        stopListen();
        appendBubble('bot', '无法启动语音识别。');
      }
    });
  }

  function dataUrlToPayload(dataUrl) {
    if (!dataUrl || dataUrl.indexOf(',') < 0) return { base64: null, mime: 'image/jpeg' };
    var head = dataUrl.split(',')[0];
    var rest = dataUrl.split(',')[1];
    var mime = 'image/jpeg';
    var m = head.match(/data:([^;]+)/);
    if (m) mime = m[1].trim();
    return { base64: rest, mime: mime };
  }

  function setLoading(on) {
    sendBtn.disabled = on;
    input.disabled = on;
    if (imgBtn) imgBtn.disabled = on;
    if (micBtn) micBtn.disabled = on;
  }

  function send() {
    var text = (input.value || '').trim();
    if (!text && !pendingImage) return;

    var displayText = text || (pendingImage ? '（见配图）请从农业角度分析。' : '');
    var payloadImg = null;
    var payloadMime = 'image/jpeg';

    if (pendingImage) {
      var parts = dataUrlToPayload(pendingImage.dataUrl);
      payloadImg = parts.base64;
      payloadMime = pendingImage.mime || parts.mime;
      appendUserBubbleWithImage(text || '请结合配图简要分析（长势、水肥或病虫害线索）。', pendingImage.dataUrl);
      clearPendingImage();
    } else {
      appendBubble('user', text);
    }

    input.value = '';
    history.push({ role: 'user', content: displayText });

    var loadingEl = appendBubble('bot', '正在思考…', 'agri-asst-msg--loading');
    setLoading(true);

    var body = { messages: history };
    if (payloadImg) {
      body.image_base64 = payloadImg;
      body.image_mime = payloadMime;
    }

    fetch('/api/agri_assistant', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
      .then(function (r) {
        return r.json().then(function (j) {
          return { ok: r.ok, json: j };
        });
      })
      .then(function (_ref) {
        loadingEl.remove();
        var j = _ref.json;
        if (_ref.ok && j.ok && j.reply) {
          appendBubble('bot', j.reply);
          history.push({ role: 'assistant', content: j.reply });
        } else {
          var err = j && j.error ? j.error : '请求失败';
          appendBubble('bot', '抱歉，' + err + '。请稍后重试或检查服务端 API 密钥配置。');
        }
      })
      .catch(function () {
        loadingEl.remove();
        appendBubble('bot', '网络异常，请检查连接后重试。');
      })
      .finally(function () {
        setLoading(false);
        if (input) input.focus();
      });
  }

  sendBtn.addEventListener('click', send);
  input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && root.classList.contains('agri-asst--open')) {
      if (listening) stopListen();
      setOpen(false);
    }
  });
})();
