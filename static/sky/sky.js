/*
 * 星空馆 —— 基于真实星表的可拖拽天球背景
 * ----------------------------------------
 * 数据：static/sky/sky.json（HYG + d3-celestial，mag <= 6，88 星座连线）
 * 渲染：球极投影（stereographic），静态层只在视角变化时重绘；
 *       流星雨画在独立的 #sky-fx 图层，不触碰星点。
 * 交互：拖拽平移、Ctrl/⌘ + 滚轮缩放、双击复位、单击召唤流星雨；
 *       触屏双指拖动/缩放，单指轻点召唤流星雨。
 */
(function () {
    'use strict';

    var canvas = document.getElementById('starfield');
    var fxCanvas = document.getElementById('sky-fx');
    if (!canvas || !fxCanvas) return;

    var ctx = canvas.getContext('2d', { alpha: false });
    var fctx = fxCanvas.getContext('2d');

    var RAD = Math.PI / 180;
    var DEG = 180 / Math.PI;
    var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var lowEnd = (navigator.deviceMemory || 8) <= 4 || (navigator.hardwareConcurrency || 8) <= 4;

    var W = 0, H = 0, DPR = 1;
    var fov = 110;                     // 垂直视场角（度）
    var center = { ra: 90, dec: 8 };   // 初始看向猎户座一带
    var basis = { f: [0, 0, 1], e: [0, 1, 0], n: [1, 0, 0], R: 1 };
    var bgGradient = null;

    var stars = [];                    // {v:[x,y,z], m:mag, c:color}
    var constellations = [];           // {id, zh, rank, v:[x,y,z], segments:[[v,v],...]}
    var projectedSegments = [];
    var hoverId = null;
    var hoverPoint = null;
    var ready = false;

    var drag = null;
    var touchGesture = null;
    var touchStart = null;
    var lastHoverCheck = 0;

    var meteors = [];
    var sparks = [];
    var fxRunning = false;
    var ambientTimer = null;

    /* 待机自转与随机流星雨的档位 */
    var ROTATE_STEPS = [
        { label: '自转 关', speed: 0 },
        { label: '自转 慢', speed: 0.4 },
        { label: '自转 中', speed: 1.5 },
        { label: '自转 快', speed: 4 },
    ];
    var SHOWER_STEPS = [
        { label: '流星 关', min: 0, max: 0, count: 0 },
        { label: '流星 低', min: 70, max: 150, count: 8 },
        { label: '流星 中', min: 30, max: 70, count: 14 },
        { label: '流星 高', min: 12, max: 30, count: 24 },
    ];
    var settings = { rotate: 1, shower: 2 };
    var lastInteraction = 0;
    var lastRotateTick = 0;
    var lastRotateRender = 0;
    var rotateRunning = false;
    var skyOnly = false;

    var hud = document.getElementById('sky-hud');
    var readout = document.getElementById('sky-readout');
    var rotateBtn = document.querySelector('[data-sky-rotate]');
    var showerBtn = document.querySelector('[data-sky-shower]');
    var pureBtn = document.querySelector('[data-sky-pure]');
    var exitBtn = document.getElementById('sky-exit');
    var infoPanel = document.getElementById('sky-info');
    var infoClose = document.getElementById('sky-info-close');
    var infoTitle = document.getElementById('sky-info-title');
    var infoEyebrow = document.getElementById('sky-info-eyebrow');
    var infoMeta = document.getElementById('sky-info-meta');
    var infoStar = document.getElementById('sky-info-star');
    var infoDesc = document.getElementById('sky-info-desc');
    var selectedId = null;

    function applyViewFromQuery() {
        // 调试用：?sky=ra,dec,fov（例如 ?sky=83,0,45 看向猎户座）
        if (!window.URLSearchParams) return;
        var params = new URLSearchParams(window.location.search);
        var value = params.get('sky');
        if (!value) return;
        var parts = value.split(',').map(Number);
        if (parts.length >= 2 && isFinite(parts[0]) && isFinite(parts[1])) {
            center = { ra: ((parts[0] % 360) + 360) % 360, dec: clamp(parts[1], -89, 89) };
        }
        if (parts.length >= 3 && isFinite(parts[2])) {
            fov = clamp(parts[2], 20, 140);
        }
    }

    function loadSettings() {
        try {
            var raw = window.localStorage.getItem('club.sky.settings');
            if (!raw) return;
            var parsed = JSON.parse(raw);
            if (typeof parsed.rotate === 'number') {
                settings.rotate = Math.max(0, Math.min(ROTATE_STEPS.length - 1, Math.round(parsed.rotate)));
            }
            if (typeof parsed.shower === 'number') {
                settings.shower = Math.max(0, Math.min(SHOWER_STEPS.length - 1, Math.round(parsed.shower)));
            }
        } catch (error) {
            /* 隐私模式或无 localStorage 时忽略 */
        }
    }

    function saveSettings() {
        try {
            window.localStorage.setItem('club.sky.settings', JSON.stringify(settings));
        } catch (error) {
            /* ignore */
        }
    }

    function updateModeButtons() {
        if (rotateBtn) rotateBtn.textContent = ROTATE_STEPS[settings.rotate].label;
        if (showerBtn) showerBtn.textContent = SHOWER_STEPS[settings.shower].label;
        if (pureBtn) pureBtn.textContent = skyOnly ? '✕ 退出' : '⛶ 纯净';
    }

    function markInteraction() {
        lastInteraction = performance.now();
    }

    function setSkyOnly(value) {
        skyOnly = value;
        document.body.classList.toggle('sky-only', value);
        if (exitBtn) exitBtn.hidden = !value;
        updateModeButtons();
        requestRender();
    }

    /* ---------------- 星座信息卡 ---------------- */
    function findConstellation(id) {
        for (var i = 0; i < constellations.length; i++) {
            if (constellations[i].id === id) return constellations[i];
        }
        return null;
    }

    function formatRa(deg) {
        var hours = (((deg % 360) + 360) % 360) / 15;
        var hh = Math.floor(hours);
        var mm = Math.round((hours - hh) * 60);
        if (mm === 60) { hh += 1; mm = 0; }
        return (hh < 10 ? '0' : '') + hh + 'h' + (mm < 10 ? '0' : '') + mm + 'm';
    }

    function formatDec(deg) {
        return (deg >= 0 ? '+' : '−') + Math.abs(deg).toFixed(1) + '°';
    }

    /* 由赤经推算“午夜中天”的月份（春分点约在 3 月下旬） */
    function bestMonth(raDeg) {
        var hours = raDeg / 15;
        var month = 3.6 + (((hours + 12) % 24) / 2);
        month = ((((month - 1) % 12) + 12) % 12) + 1;
        return Math.round(month);
    }

    function showInfo(id) {
        var constellation = findConstellation(id);
        if (!constellation || !infoPanel) return;
        selectedId = id;

        if (infoEyebrow) {
            infoEyebrow.textContent = [constellation.en, constellation.abbr]
                .filter(Boolean).join(' · ');
        }
        if (infoTitle) infoTitle.textContent = constellation.zh;
        if (infoMeta) {
            infoMeta.textContent = 'RA ' + formatRa(constellation.label[0])
                + ' · Dec ' + formatDec(constellation.label[1])
                + ' · 午夜中天约 ' + bestMonth(constellation.label[0]) + ' 月';
        }
        if (infoStar) {
            infoStar.textContent = constellation.star ? '主要亮星：' + constellation.star : '';
            infoStar.hidden = !constellation.star;
        }
        if (infoDesc) {
            infoDesc.textContent = constellation.desc || '暂无简介。';
        }
        infoPanel.hidden = false;
        requestRender();
    }

    function hideInfo() {
        selectedId = null;
        if (infoPanel) infoPanel.hidden = true;
        requestRender();
    }

    function clamp(value, min, max) {
        return Math.max(min, Math.min(max, value));
    }

    function toVector(raDeg, decDeg) {
        var ra = raDeg * RAD;
        var dec = decDeg * RAD;
        var cd = Math.cos(dec);
        return [cd * Math.cos(ra), cd * Math.sin(ra), Math.sin(dec)];
    }

    function updateBasis() {
        var ra = center.ra * RAD;
        var dec = center.dec * RAD;
        var cd = Math.cos(dec);
        var sd = Math.sin(dec);
        var ca = Math.cos(ra);
        var sa = Math.sin(ra);

        basis.f = [cd * ca, cd * sa, sd];
        basis.e = [-sa, ca, 0];
        basis.n = [-sd * ca, -sd * sa, cd];
        basis.R = H / (4 * Math.tan((fov * RAD) / 4));
    }

    /* 球极投影：返回 [x, y, cosTheta] 或 null（超出可见范围） */
    function project(v) {
        var cosc = v[0] * basis.f[0] + v[1] * basis.f[1] + v[2] * basis.f[2];
        if (cosc <= 0.2) return null;
        var k = (2 * basis.R) / (1 + cosc);
        var ex = v[0] * basis.e[0] + v[1] * basis.e[1] + v[2] * basis.e[2];
        var ny = v[0] * basis.n[0] + v[1] * basis.n[1] + v[2] * basis.n[2];
        return [W / 2 + k * ex, H / 2 - k * ny, cosc];
    }

    function starColor(bv) {
        if (bv < 0) return '190,212,255';
        if (bv < 0.5) return '219,231,255';
        if (bv < 1.0) return '244,246,255';
        if (bv < 1.5) return '255,238,210';
        return '255,214,168';
    }

    function drawBackground() {
        if (!bgGradient) {
            bgGradient = ctx.createRadialGradient(W * 0.5, H * 0.42, 0, W * 0.5, H * 0.42, Math.max(W, H) * 0.78);
            bgGradient.addColorStop(0, '#0b1024');
            bgGradient.addColorStop(0.45, '#080a18');
            bgGradient.addColorStop(1, '#04050c');
        }
        ctx.fillStyle = bgGradient;
        ctx.fillRect(0, 0, W, H);
    }

    function render() {
        if (!ready) return;
        updateBasis();
        drawBackground();
        drawStars();
        drawConstellations();
        updateReadout();
    }

    function drawStars() {
        var count = stars.length;
        var sizeScale = lowEnd ? 0.8 : 1;
        var glowBudget = lowEnd ? 12 : 30;

        for (var i = 0; i < count; i++) {
            var star = stars[i];
            var point = project(star.v);
            if (!point) continue;

            var mag = star.m;
            var brightness = clamp((6.4 - mag) / 7.4, 0.05, 1);
            var radius = (0.5 + brightness * 1.7) * sizeScale;
            var alpha = 0.26 + brightness * 0.74;
            var x = point[0];
            var y = point[1];
            if (x < -8 || y < -8 || x > W + 8 || y > H + 8) continue;

            var color = star.c;
            if (radius <= 1.05) {
                ctx.fillStyle = 'rgba(' + color + ',' + alpha.toFixed(3) + ')';
                ctx.fillRect(x - radius / 2, y - radius / 2, radius, radius);
            } else {
                ctx.beginPath();
                ctx.fillStyle = 'rgba(' + color + ',' + alpha.toFixed(3) + ')';
                ctx.arc(x, y, radius, 0, Math.PI * 2);
                ctx.fill();

                if (mag < 1.4 && glowBudget > 0) {
                    glowBudget -= 1;
                    var glow = ctx.createRadialGradient(x, y, 0, x, y, radius * 4.5);
                    glow.addColorStop(0, 'rgba(' + color + ',0.28)');
                    glow.addColorStop(1, 'rgba(' + color + ',0)');
                    ctx.fillStyle = glow;
                    ctx.beginPath();
                    ctx.arc(x, y, radius * 4.5, 0, Math.PI * 2);
                    ctx.fill();
                }
            }
        }
    }

    function drawConstellations() {
        projectedSegments = [];
        var lineAlpha = fov < 60 ? 0.4 : 0.24;
        var lineWidth = fov < 60 ? 1 : 0.8;

        ctx.lineWidth = lineWidth;
        ctx.strokeStyle = 'rgba(126,160,255,' + lineAlpha + ')';
        ctx.beginPath();

        for (var i = 0; i < constellations.length; i++) {
            var constellation = constellations[i];
            for (var j = 0; j < constellation.segments.length; j++) {
                var segment = constellation.segments[j];
                var a = project(segment[0]);
                var b = project(segment[1]);
                if (!a || !b) continue;
                ctx.moveTo(a[0], a[1]);
                ctx.lineTo(b[0], b[1]);
                projectedSegments.push({
                    x1: a[0], y1: a[1], x2: b[0], y2: b[1], id: constellation.id,
                });
            }
        }
        ctx.stroke();

        if (hoverId) {
            ctx.lineWidth = 1.4;
            ctx.strokeStyle = 'rgba(255,150,215,0.75)';
            ctx.beginPath();
            for (var m = 0; m < projectedSegments.length; m++) {
                var item = projectedSegments[m];
                if (item.id !== hoverId) continue;
                ctx.moveTo(item.x1, item.y1);
                ctx.lineTo(item.x2, item.y2);
            }
            ctx.stroke();
        }

        if (selectedId) {
            ctx.lineWidth = 1.7;
            ctx.strokeStyle = 'rgba(255,196,120,0.9)';
            ctx.beginPath();
            for (var n = 0; n < projectedSegments.length; n++) {
                var chosen = projectedSegments[n];
                if (chosen.id !== selectedId) continue;
                ctx.moveTo(chosen.x1, chosen.y1);
                ctx.lineTo(chosen.x2, chosen.y2);
            }
            ctx.stroke();
        }

        drawLabels();
    }

    function drawLabels() {
        var zoomedIn = fov <= 85;
        var threshold = fov < 45 ? 3 : 2;
        ctx.font = '11px "Segoe UI", "Microsoft YaHei", sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';

        for (var i = 0; i < constellations.length; i++) {
            var constellation = constellations[i];
            var isHover = constellation.id === hoverId;
            var isSelected = constellation.id === selectedId;
            if (!isHover && !isSelected) {
                if (!zoomedIn || constellation.rank > threshold) continue;
            }
            var point = project(constellation.v);
            if (!point) continue;
            if (point[0] < -40 || point[1] < -20 || point[0] > W + 40 || point[1] > H + 20) continue;
            ctx.fillStyle = isSelected
                ? 'rgba(255,210,150,0.98)'
                : (isHover ? 'rgba(255,190,230,0.95)' : 'rgba(178,198,255,0.55)');
            ctx.fillText(constellation.zh, point[0], point[1]);
        }

        ctx.textAlign = 'start';
        ctx.textBaseline = 'alphabetic';

        if (hoverId && hoverPoint && hoverId !== selectedId) {
            var name = hoverName(hoverId);
            ctx.font = '12px "Segoe UI", "Microsoft YaHei", sans-serif';
            ctx.fillStyle = 'rgba(255,190,230,0.95)';
            ctx.fillText(name, hoverPoint[0] + 14, hoverPoint[1] + 4);
        }
    }

    function hoverName(id) {
        for (var i = 0; i < constellations.length; i++) {
            if (constellations[i].id === id) return constellations[i].zh;
        }
        return id;
    }

    function updateReadout() {
        if (!readout) return;
        var ra = center.ra / 15;
        var hours = Math.floor(ra);
        var minutes = Math.round((ra - hours) * 60);
        if (minutes === 60) { hours += 1; minutes = 0; }
        var dec = center.dec;
        var sign = dec >= 0 ? '+' : '−';
        readout.textContent = 'RA ' + (hours < 10 ? '0' : '') + hours
            + 'h' + (minutes < 10 ? '0' : '') + minutes
            + 'm · Dec ' + sign + Math.abs(dec).toFixed(1) + '° · FOV ' + Math.round(fov) + '°';
    }

    /* ------------------------------------------------------------------ */
    /* 命中测试                                                            */
    /* ------------------------------------------------------------------ */
    function distanceToSegment(px, py, x1, y1, x2, y2) {
        var dx = x2 - x1;
        var dy = y2 - y1;
        var lengthSq = dx * dx + dy * dy;
        var t = lengthSq ? ((px - x1) * dx + (py - y1) * dy) / lengthSq : 0;
        t = clamp(t, 0, 1);
        var cx = x1 + t * dx;
        var cy = y1 + t * dy;
        return Math.hypot(px - cx, py - cy);
    }

    function hitTest(x, y, tolerance) {
        var best = null;
        var bestDistance = tolerance || 12;
        for (var i = 0; i < projectedSegments.length; i++) {
            var item = projectedSegments[i];
            var distance = distanceToSegment(x, y, item.x1, item.y1, item.x2, item.y2);
            if (distance < bestDistance) {
                bestDistance = distance;
                best = item.id;
            }
        }
        return best;
    }

    /* ------------------------------------------------------------------ */
    /* 交互：拖拽 / 缩放 / 点击流星雨                                       */
    /* ------------------------------------------------------------------ */
    var INTERACTIVE = 'a,button,input,textarea,select,label,form,.topbar,.sky-info,.sky-hud,.chat-layout,.draft-card';
    var renderQueued = false;

    function requestRender() {
        if (renderQueued) return;
        renderQueued = true;
        window.requestAnimationFrame(function () {
            renderQueued = false;
            render();
        });
    }

    function canStartDrag(target) {
        if (!target || !target.closest) return true;
        return !target.closest(INTERACTIVE);
    }

    function panBy(dx, dy) {
        markInteraction();
        var degPerPx = fov / H;
        center.ra -= (dx * degPerPx) / Math.max(0.18, Math.cos(center.dec * RAD));
        center.dec += dy * degPerPx;
        center.ra = ((center.ra % 360) + 360) % 360;
        center.dec = clamp(center.dec, -89, 89);
        requestRender();
    }

    function setFov(value) {
        fov = clamp(value, 20, 140);
        bgGradient = null;
        requestRender();
        updateReadout();
    }

    /* 待机自转：用户停手 3.5 秒后开始按档位速度转动赤经 */
    function rotationStep(now) {
        if (!rotateRunning) return;
        var speed = ROTATE_STEPS[settings.rotate].speed;
        if (!speed) {
            rotateRunning = false;
            return;
        }

        var dt = Math.min(0.1, (now - lastRotateTick) / 1000);
        lastRotateTick = now;

        if (now - lastInteraction > 3500 && !document.hidden) {
            center.ra = (center.ra + speed * dt) % 360;
            var frameGap = lowEnd ? 50 : 33;
            if (now - lastRotateRender > frameGap) {
                lastRotateRender = now;
                render();
            }
        }
        window.requestAnimationFrame(rotationStep);
    }

    function startRotation() {
        if (rotateRunning) return;
        if (!ROTATE_STEPS[settings.rotate].speed || reduceMotion) return;
        rotateRunning = true;
        lastRotateTick = performance.now();
        window.requestAnimationFrame(rotationStep);
    }

    function onPointerDown(event) {
        if (event.pointerType === 'touch') return;
        if (event.button !== 0 || !canStartDrag(event.target)) return;
        drag = { x: event.clientX, y: event.clientY, moved: 0, id: event.pointerId };
        document.body.classList.add('sky-dragging');
    }

    function onPointerMove(event) {
        if (event.pointerType === 'touch') return;
        if (drag && event.pointerId === drag.id) {
            var dx = event.clientX - drag.x;
            var dy = event.clientY - drag.y;
            drag.x = event.clientX;
            drag.y = event.clientY;
            drag.moved += Math.abs(dx) + Math.abs(dy);
            if (drag.moved > 4) panBy(dx, dy);
            return;
        }

        var now = performance.now();
        if (now - lastHoverCheck < 60) return;
        lastHoverCheck = now;

        var hit = hitTest(event.clientX, event.clientY);
        if (hit !== hoverId) {
            hoverId = hit;
            hoverPoint = hit ? [event.clientX, event.clientY] : null;
            requestRender();
        } else if (hit) {
            hoverPoint = [event.clientX, event.clientY];
            requestRender();
        }
    }

    function endDrag(event) {
        if (event.pointerType === 'touch') return;
        if (!drag) return;
        var wasDrag = drag.moved > 8;
        drag = null;
        document.body.classList.remove('sky-dragging');
        if (!wasDrag && canStartDrag(event.target)) {
            var hit = hitTest(event.clientX, event.clientY, 16);
            if (hit) {
                showInfo(hit);
            } else {
                hideInfo();
                spawnMeteorShower(event.clientX, event.clientY);
            }
        }
    }

    function onWheel(event) {
        if (!event.ctrlKey && !event.metaKey) return;
        event.preventDefault();
        markInteraction();
        setFov(fov * (1 + event.deltaY * 0.0012));
    }

    function onDoubleClick(event) {
        if (!canStartDrag(event.target)) return;
        center = { ra: 90, dec: 8 };
        fov = 110;
        bgGradient = null;
        requestRender();
    }

    function onTouchStart(event) {
        markInteraction();
        if (event.touches.length === 1) {
            var touch = event.touches[0];
            touchStart = { x: touch.clientX, y: touch.clientY, time: Date.now() };
        }
        if (event.touches.length === 2) {
            touchStart = null;
            var a = event.touches[0];
            var b = event.touches[1];
            touchGesture = {
                distance: Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY),
                x: (a.clientX + b.clientX) / 2,
                y: (a.clientY + b.clientY) / 2,
                fov: fov,
            };
        }
    }

    function onTouchMove(event) {
        if (!touchGesture || event.touches.length !== 2) return;
        event.preventDefault();
        var a = event.touches[0];
        var b = event.touches[1];
        var distance = Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
        var x = (a.clientX + b.clientX) / 2;
        var y = (a.clientY + b.clientY) / 2;
        panBy(x - touchGesture.x, y - touchGesture.y);
        touchGesture.x = x;
        touchGesture.y = y;
        if (touchGesture.distance > 0) {
            fov = clamp(touchGesture.fov * (touchGesture.distance / distance), 20, 140);
            bgGradient = null;
            requestRender();
        }
    }

    function onTouchEnd(event) {
        if (event.touches.length > 0) return;
        touchGesture = null;
        if (touchStart && Date.now() - touchStart.time < 320) {
            var hit = hitTest(touchStart.x, touchStart.y, 20);
            if (hit) {
                showInfo(hit);
            } else {
                hideInfo();
                spawnMeteorShower(touchStart.x, touchStart.y);
            }
        }
        touchStart = null;
    }

    /* ------------------------------------------------------------------ */
    /* 流星雨（独立图层，不影响星点重绘）                                    */
    /* ------------------------------------------------------------------ */
    function createMeteor(x, y, angle, speed, life) {
        return {
            x: x,
            y: y,
            vx: Math.cos(angle) * speed,
            vy: Math.sin(angle) * speed,
            life: 1,
            decay: 1 / (life * 60),
            length: 0.055 + Math.random() * 0.05,
            width: 0.8 + Math.random() * 1.6,
            hue: 195 + Math.random() * 45,
        };
    }

    function spawnBurst(x, y, count) {
        for (var i = 0; i < count; i++) {
            var angle = Math.random() * Math.PI * 2;
            var speed = 240 + Math.random() * 460;
            var meteor = createMeteor(
                x + (Math.random() - 0.5) * 120,
                y + (Math.random() - 0.5) * 120,
                angle,
                speed,
                1.4 + Math.random() * 0.9
            );
            meteor.decay = 1 / (60 * (1.2 + Math.random() * 0.9));
            meteors.push(meteor);
        }
        var sparkCount = Math.min(18, count + 4);
        for (var s = 0; s < sparkCount; s++) {
            var sparkAngle = Math.random() * Math.PI * 2;
            var sparkSpeed = 60 + Math.random() * 220;
            sparks.push({
                x: x, y: y,
                vx: Math.cos(sparkAngle) * sparkSpeed,
                vy: Math.sin(sparkAngle) * sparkSpeed,
                life: 0.6 + Math.random() * 0.5,
            });
        }
        startFxLoop();
    }

    function spawnMeteorShower(x, y) {
        spawnBurst(x, y, lowEnd ? 12 : 22);
    }

    /* 待机时随机出现的流星雨：位置、规模都随机 */
    function spawnAmbientShower() {
        var conf = SHOWER_STEPS[settings.shower];
        if (!conf || !conf.count) return;
        var x = W * (0.15 + Math.random() * 0.7);
        var y = H * (0.12 + Math.random() * 0.5);
        spawnBurst(x, y, Math.max(6, Math.round(conf.count * 0.75)));
    }

    function scheduleAmbient() {
        if (ambientTimer) {
            clearTimeout(ambientTimer);
            ambientTimer = null;
        }
        var conf = SHOWER_STEPS[settings.shower];
        if (reduceMotion || !conf || !conf.count) return;
        var delay = conf.min + Math.random() * (conf.max - conf.min);
        ambientTimer = setTimeout(function () {
            ambientTimer = null;
            if (!document.hidden) spawnAmbientShower();
            scheduleAmbient();
        }, delay * 1000);
    }

    function startFxLoop() {
        if (fxRunning) return;
        fxRunning = true;
        window.requestAnimationFrame(fxStep);
    }

    function fxStep() {
        fctx.clearRect(0, 0, W, H);
        var alive = false;

        for (var i = meteors.length - 1; i >= 0; i--) {
            var meteor = meteors[i];
            meteor.x += meteor.vx / 60;
            meteor.y += meteor.vy / 60;
            meteor.life -= meteor.decay;
            if (meteor.life <= 0) {
                meteors.splice(i, 1);
                continue;
            }
            alive = true;

            var tailX = meteor.x - meteor.vx * meteor.length;
            var tailY = meteor.y - meteor.vy * meteor.length;
            var gradient = fctx.createLinearGradient(meteor.x, meteor.y, tailX, tailY);
            gradient.addColorStop(0, 'hsla(' + meteor.hue + ',100%,88%,' + (meteor.life * 0.95) + ')');
            gradient.addColorStop(1, 'hsla(' + meteor.hue + ',100%,75%,0)');
            fctx.strokeStyle = gradient;
            fctx.lineWidth = meteor.width;
            fctx.lineCap = 'round';
            fctx.beginPath();
            fctx.moveTo(meteor.x, meteor.y);
            fctx.lineTo(tailX, tailY);
            fctx.stroke();

            fctx.fillStyle = 'hsla(' + meteor.hue + ',100%,92%,' + meteor.life + ')';
            fctx.beginPath();
            fctx.arc(meteor.x, meteor.y, meteor.width * 1.1, 0, Math.PI * 2);
            fctx.fill();
        }

        for (var j = sparks.length - 1; j >= 0; j--) {
            var spark = sparks[j];
            spark.x += spark.vx / 60;
            spark.y += spark.vy / 60;
            spark.vx *= 0.96;
            spark.vy *= 0.96;
            spark.life -= 0.02;
            if (spark.life <= 0) {
                sparks.splice(j, 1);
                continue;
            }
            alive = true;
            fctx.fillStyle = 'rgba(200,220,255,' + (spark.life * 0.8) + ')';
            fctx.fillRect(spark.x, spark.y, 1.6, 1.6);
        }

        if (alive) {
            window.requestAnimationFrame(fxStep);
        } else {
            fctx.clearRect(0, 0, W, H);
            fxRunning = false;
        }
    }

    /* ------------------------------------------------------------------ */
    /* 数据加载与初始化                                                     */
    /* ------------------------------------------------------------------ */
    function buildScene(data) {
        var rawStars = data.stars || [];
        var limit = lowEnd ? 5.2 : 6.0;
        for (var i = 0; i < rawStars.length; i++) {
            var item = rawStars[i];
            if (item[2] > limit) continue;
            stars.push({
                v: toVector(item[0], item[1]),
                m: item[2],
                c: starColor(item[3]),
            });
        }

        var rawConstellations = data.constellations || [];
        for (var c = 0; c < rawConstellations.length; c++) {
            var raw = rawConstellations[c];
            var segments = [];
            for (var s = 0; s < raw.segments.length; s++) {
                var seg = raw.segments[s];
                segments.push([toVector(seg[0], seg[1]), toVector(seg[2], seg[3])]);
            }
            constellations.push({
                id: raw.id,
                zh: raw.zh,
                en: raw.en || '',
                abbr: raw.abbr || raw.id,
                rank: raw.rank,
                desc: raw.desc || '',
                star: raw.star || '',
                label: raw.label,
                v: toVector(raw.label[0], raw.label[1]),
                segments: segments,
            });
        }
    }

    function drawFallback() {
        ctx.fillStyle = '#05060f';
        ctx.fillRect(0, 0, W, H);
        ctx.fillStyle = 'rgba(220,230,255,0.8)';
        for (var i = 0; i < 500; i++) {
            var size = Math.random() < 0.92 ? 1 : 1.8;
            ctx.fillRect(Math.random() * W, Math.random() * H, size, size);
        }
    }

    function resize() {
        DPR = Math.min(window.devicePixelRatio || 1, lowEnd ? 1.25 : 2);
        W = window.innerWidth;
        H = window.innerHeight;

        canvas.width = Math.round(W * DPR);
        canvas.height = Math.round(H * DPR);
        canvas.style.width = W + 'px';
        canvas.style.height = H + 'px';
        ctx.setTransform(DPR, 0, 0, DPR, 0, 0);

        fxCanvas.width = Math.round(W * DPR);
        fxCanvas.height = Math.round(H * DPR);
        fxCanvas.style.width = W + 'px';
        fxCanvas.style.height = H + 'px';
        fctx.setTransform(DPR, 0, 0, DPR, 0, 0);

        bgGradient = null;
        if (ready) {
            requestRender();
        } else {
            drawFallback();
        }
    }

    function loadData() {
        var source = canvas.getAttribute('data-sky-src') || '/static/sky/sky.json';
        if (!window.fetch) {
            drawFallback();
            return;
        }
        fetch(source, { credentials: 'same-origin' })
            .then(function (response) {
                if (!response.ok) throw new Error('sky data ' + response.status);
                return response.json();
            })
            .then(function (data) {
                buildScene(data);
                ready = true;
                if (hud) hud.hidden = false;
                render();
                scheduleAmbient();
                startRotation();
            })
            .catch(function () {
                drawFallback();
            });
    }

    document.addEventListener('pointerdown', onPointerDown);
    document.addEventListener('pointermove', onPointerMove);
    document.addEventListener('pointerup', endDrag);
    document.addEventListener('pointercancel', function () {
        drag = null;
        document.body.classList.remove('sky-dragging');
    });
    document.addEventListener('wheel', onWheel, { passive: false });
    document.addEventListener('dblclick', onDoubleClick);
    document.addEventListener('touchstart', onTouchStart, { passive: true });
    document.addEventListener('touchmove', onTouchMove, { passive: false });
    document.addEventListener('touchend', onTouchEnd, { passive: true });
    document.addEventListener('selectstart', function (event) {
        if (drag && drag.moved > 4) event.preventDefault();
    });

    var zoomButtons = document.querySelectorAll('[data-sky-zoom]');
    for (var i = 0; i < zoomButtons.length; i++) {
        zoomButtons[i].addEventListener('click', function (event) {
            var direction = event.currentTarget.getAttribute('data-sky-zoom');
            setFov(direction === 'in' ? fov * 0.8 : fov * 1.25);
        });
    }

    var hudToggle = document.getElementById('sky-toggle');
    if (hudToggle) {
        hudToggle.addEventListener('click', function () {
            if (hud) hud.classList.toggle('is-open');
        });
    }
    if (rotateBtn) {
        rotateBtn.addEventListener('click', function () {
            settings.rotate = (settings.rotate + 1) % ROTATE_STEPS.length;
            saveSettings();
            updateModeButtons();
            if (ROTATE_STEPS[settings.rotate].speed) startRotation();
        });
    }
    if (showerBtn) {
        showerBtn.addEventListener('click', function () {
            settings.shower = (settings.shower + 1) % SHOWER_STEPS.length;
            saveSettings();
            updateModeButtons();
            scheduleAmbient();
        });
    }
    if (pureBtn) {
        pureBtn.addEventListener('click', function () { setSkyOnly(!skyOnly); });
    }
    if (exitBtn) {
        exitBtn.addEventListener('click', function () { setSkyOnly(false); });
    }
    if (infoClose) {
        infoClose.addEventListener('click', hideInfo);
    }

    document.addEventListener('keydown', function (event) {
        if (event.ctrlKey || event.metaKey || event.altKey) return;
        var target = event.target;
        if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA'
            || target.tagName === 'SELECT' || target.isContentEditable)) return;
        if (event.key === 's' || event.key === 'S') {
            event.preventDefault();
            markInteraction();
            setSkyOnly(!skyOnly);
        } else if (event.key === 'Escape') {
            if (selectedId) {
                hideInfo();
            } else if (skyOnly) {
                setSkyOnly(false);
            }
        }
    });
    if (hud) {
        if (window.innerWidth > 700) {
            // 桌面端首次展示 9 秒后自动收起，不挡内容
            window.setTimeout(function () { hud.classList.remove('is-open'); }, 9000);
        } else {
            // 小屏默认收起，只留一个 ✦ 按钮
            hud.classList.remove('is-open');
        }
    }

    window.addEventListener('resize', resize);
    document.addEventListener('visibilitychange', function () {
        if (document.hidden && ambientTimer) {
            clearTimeout(ambientTimer);
            ambientTimer = null;
        } else if (!document.hidden && ready) {
            scheduleAmbient();
        }
    });

    applyViewFromQuery();
    loadSettings();
    updateModeButtons();
    resize();
    loadData();
})();
