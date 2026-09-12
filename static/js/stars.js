(function () {
    const canvas = document.getElementById('starfield');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    let W = 0, H = 0, DPR = Math.min(window.devicePixelRatio || 1, 2);
    let layers = [];
    let shootingStars = [];
    let particles = [];
    let mouse = { x: 0.5, y: 0.5, tx: 0.5, ty: 0.5 };
    let rafId = null;

    const SPARKLE_HUES = [20, 50, 160, 190, 220, 260, 300, 330];

    function rand(min, max) { return Math.random() * (max - min) + min; }

    function resize() {
        W = window.innerWidth;
        H = window.innerHeight;
        canvas.width = W * DPR;
        canvas.height = H * DPR;
        canvas.style.width = W + 'px';
        canvas.style.height = H + 'px';
        ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
        buildStars();
    }

    function buildStars() {
        layers = [
            { density: 0.18, size: [0.3, 0.8], speed: 0.04, twinkle: 0.6, stars: [] },
            { density: 0.09, size: [0.6, 1.4], speed: 0.12, twinkle: 1.0, stars: [] },
            { density: 0.04, size: [1.0, 2.2], speed: 0.28, twinkle: 1.6, stars: [] },
        ];
        const total = Math.floor(W * H / 1000);
        layers.forEach((layer, li) => {
            const count = Math.floor(total * layer.density);
            layer.stars = new Array(count);
            for (let i = 0; i < count; i++) {
                layer.stars[i] = {
                    x: Math.random() * W,
                    y: Math.random() * H,
                    r: rand(layer.size[0], layer.size[1]),
                    phase: Math.random() * Math.PI * 2,
                    speed: layer.speed * rand(0.7, 1.3),
                    drift: { x: rand(-0.15, 0.15), y: rand(-0.05, 0.05) },
                    hue: li === 2 ? rand(200, 320) : rand(210, 270),
                };
            }
        });
    }

    function spawnShootingStar() {
        const fromLeft = Math.random() > 0.5;
        shootingStars.push({
            x: fromLeft ? -20 : W + 20,
            y: rand(0, H * 0.6),
            vx: (fromLeft ? 1 : -1) * rand(8, 14),
            vy: rand(2, 5),
            len: rand(80, 160),
            life: 1,
            decay: rand(0.012, 0.022),
            hue: rand(190, 320),
        });
    }

    let lastShoot = 0;
    function maybeShoot(now) {
        if (now - lastShoot > rand(3500, 8000)) {
            spawnShootingStar();
            lastShoot = now;
        }
    }

    function drawStar(s, t, parallaxX, parallaxY) {
        const tw = 0.5 + 0.5 * Math.sin(t * 0.002 * s.speed * 10 + s.phase);
        const alpha = 0.35 + tw * 0.65;
        const x = s.x + parallaxX * s.speed * 40;
        const y = s.y + parallaxY * s.speed * 40;

        ctx.beginPath();
        ctx.fillStyle = `hsla(${s.hue}, 70%, 85%, ${alpha})`;
        ctx.arc(x, y, s.r, 0, Math.PI * 2);
        ctx.fill();

        if (s.r > 1.2) {
            const glow = ctx.createRadialGradient(x, y, 0, x, y, s.r * 5);
            glow.addColorStop(0, `hsla(${s.hue}, 80%, 75%, ${alpha * 0.4})`);
            glow.addColorStop(1, `hsla(${s.hue}, 80%, 75%, 0)`);
            ctx.fillStyle = glow;
            ctx.beginPath();
            ctx.arc(x, y, s.r * 5, 0, Math.PI * 2);
            ctx.fill();
        }
    }

    function drawShootingStar(s) {
        const tailX = s.x - s.vx * 12;
        const tailY = s.y - s.vy * 12;
        const grad = ctx.createLinearGradient(s.x, s.y, tailX, tailY);
        grad.addColorStop(0, `hsla(${s.hue}, 90%, 85%, ${s.life})`);
        grad.addColorStop(1, `hsla(${s.hue}, 90%, 75%, 0)`);
        ctx.strokeStyle = grad;
        ctx.lineWidth = 1.6;
        ctx.lineCap = 'round';
        ctx.beginPath();
        ctx.moveTo(s.x, s.y);
        ctx.lineTo(tailX, tailY);
        ctx.stroke();

        ctx.fillStyle = `hsla(${s.hue}, 90%, 90%, ${s.life})`;
        ctx.beginPath();
        ctx.arc(s.x, s.y, 1.8, 0, Math.PI * 2);
        ctx.fill();
    }

    function spawnParticles(x, y) {
        const count = Math.floor(rand(18, 32));
        for (let i = 0; i < count; i++) {
            const angle = Math.random() * Math.PI * 2;
            const speed = rand(1.2, 5.2);
            const hue = SPARKLE_HUES[Math.floor(Math.random() * SPARKLE_HUES.length)] + rand(-15, 15);
            particles.push({
                x: x,
                y: y,
                vx: Math.cos(angle) * speed,
                vy: Math.sin(angle) * speed,
                r: rand(1.2, 3.2),
                hue: hue,
                life: 1,
                decay: rand(0.012, 0.028),
                gravity: rand(0.02, 0.06),
                drag: rand(0.96, 0.99),
                spark: Math.random() > 0.55,
            });
        }
        if (particles.length > 500) {
            particles.splice(0, particles.length - 500);
        }
    }

    function updateAndDrawParticles() {
        for (let i = particles.length - 1; i >= 0; i--) {
            const p = particles[i];
            p.vx *= p.drag;
            p.vy *= p.drag;
            p.vy += p.gravity;
            p.x += p.vx;
            p.y += p.vy;
            p.life -= p.decay;

            if (p.life <= 0) { particles.splice(i, 1); continue; }

            const size = p.r * p.life;
            const alpha = Math.max(0, p.life);

            if (p.spark) {
                const glow = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, size * 6);
                glow.addColorStop(0, `hsla(${p.hue}, 100%, 85%, ${alpha * 0.9})`);
                glow.addColorStop(0.3, `hsla(${p.hue}, 100%, 65%, ${alpha * 0.4})`);
                glow.addColorStop(1, `hsla(${p.hue}, 100%, 65%, 0)`);
                ctx.fillStyle = glow;
                ctx.beginPath();
                ctx.arc(p.x, p.y, size * 6, 0, Math.PI * 2);
                ctx.fill();
            } else {
                ctx.fillStyle = `hsla(${p.hue}, 100%, 80%, ${alpha})`;
                ctx.beginPath();
                ctx.arc(p.x, p.y, size, 0, Math.PI * 2);
                ctx.fill();

                const glow = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, size * 3);
                glow.addColorStop(0, `hsla(${p.hue}, 100%, 70%, ${alpha * 0.35})`);
                glow.addColorStop(1, `hsla(${p.hue}, 100%, 70%, 0)`);
                ctx.fillStyle = glow;
                ctx.beginPath();
                ctx.arc(p.x, p.y, size * 3, 0, Math.PI * 2);
                ctx.fill();
            }
        }
    }

    function step(t) {
        ctx.clearRect(0, 0, W, H);

        mouse.x += (mouse.tx - mouse.x) * 0.05;
        mouse.y += (mouse.ty - mouse.y) * 0.05;
        const px = (mouse.x - 0.5) * 2;
        const py = (mouse.y - 0.5) * 2;

        layers.forEach(layer => {
            layer.stars.forEach(s => {
                s.x += s.drift.x * 0.3;
                s.y += s.drift.y * 0.3;
                if (s.x < -5) s.x = W + 5;
                if (s.x > W + 5) s.x = -5;
                if (s.y < -5) s.y = H + 5;
                if (s.y > H + 5) s.y = -5;
                drawStar(s, t, px, py);
            });
        });

        maybeShoot(t);
        for (let i = shootingStars.length - 1; i >= 0; i--) {
            const s = shootingStars[i];
            s.x += s.vx;
            s.y += s.vy;
            s.life -= s.decay;
            drawShootingStar(s);
            if (s.life <= 0 || s.x < -50 || s.x > W + 50 || s.y > H + 50) {
                shootingStars.splice(i, 1);
            }
        }

        updateAndDrawParticles();

        rafId = requestAnimationFrame(step);
    }

    function onMouseMove(e) {
        mouse.tx = e.clientX / W;
        mouse.ty = e.clientY / H;
    }
    function onTouchMove(e) {
        if (e.touches[0]) {
            mouse.tx = e.touches[0].clientX / W;
            mouse.ty = e.touches[0].clientY / H;
        }
    }

    window.addEventListener('resize', resize);
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('touchmove', onTouchMove, { passive: true });

    function onClick(e) {
        const x = (e.clientX !== undefined ? e.clientX : (e.touches && e.touches[0] ? e.touches[0].clientX : 0));
        const y = (e.clientY !== undefined ? e.clientY : (e.touches && e.touches[0] ? e.touches[0].clientY : 0));
        spawnParticles(x, y);
    }
    window.addEventListener('click', onClick);
    window.addEventListener('touchstart', (e) => { if (e.touches[0]) onClick(e); }, { passive: true });

    resize();
    rafId = requestAnimationFrame(step);
})();