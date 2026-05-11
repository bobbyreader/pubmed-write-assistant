# Neon Pinball — Implementation Plan

**Goal:** 单文件弹珠台游戏，Canvas 2D，霓虹赛博朋克风格，5关关卡制

**Architecture:** 单 HTML 文件，Canvas 2D 渲染，requestAnimationFrame 游戏循环，状态机管理游戏流程

**Tech Stack:** 纯 HTML + CSS + JavaScript，零依赖，Canvas 2D API

---

## Task 1: 项目初始化与基础框架

**文件:** 创建 `index.html`

- [ ] **Step 1: 创建 HTML 基础结构**

```html
<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Neon Pinball</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    background: #050508;
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 100vh;
    font-family: 'Courier New', monospace;
    overflow: hidden;
  }
  #container {
    position: relative;
  }
  canvas {
    display: block;
    border: 2px solid rgba(139, 92, 246, 0.4);
    box-shadow: 0 0 40px rgba(139, 92, 246, 0.2), inset 0 0 60px rgba(0,0,0,0.5);
    border-radius: 4px;
  }
</style>
</head>
<body>
<div id="container">
  <canvas id="game"></canvas>
</div>
<script>
// === CONSTANTS ===
const W = 480, H = 700;
const GRAVITY = 0.25;
const BALL_RADIUS = 8;
const PADDLE_W = 120, PADDLE_H = 14;
const BRICK_ROWS = 5, BRICK_COLS = 6;
const BRICK_W = 70, BRICK_H = 25, BRICK_GAP = 4;
const LEVEL_TARGETS = [500, 1200, 2500, 5000, 10000];
const BRICK_COLORS = ['#F472B6', '#FB923C', '#FACC15', '#4ADE80', '#38BDF8'];
const TRAIL_LENGTH = 8;

const canvas = document.getElementById('game');
const ctx = canvas.getContext('2d');
canvas.width = W;
canvas.height = H;

// === GAME STATE ===
let state = 'menu'; // menu | playing | levelComplete | gameOver | win
let score = 0;
let lives = 3;
let level = 1;
let combo = 0;
let mouseX = W / 2;

// Ball
let ball = { x: W/2, y: H - 100, vx: 0, vy: 0, trail: [] };

// Paddle
let paddle = { x: W/2 - PADDLE_W/2, y: H - 40 };

// Bricks
let bricks = [];

// Particles
let particles = [];

// Level complete timer
let levelTimer = 0;
let menuPulse = 0;

function initBricks() {
  bricks = [];
  const totalW = BRICK_COLS * BRICK_W + (BRICK_COLS - 1) * BRICK_GAP;
  const startX = (W - totalW) / 2;
  for (let r = 0; r < BRICK_ROWS; r++) {
    for (let c = 0; c < BRICK_COLS; c++) {
      // Level 3: random gaps
      if (level === 3 && Math.random() < 0.2) continue;
      bricks.push({
        x: startX + c * (BRICK_W + BRICK_GAP),
        y: 80 + r * (BRICK_H + BRICK_GAP),
        w: BRICK_W, h: BRICK_H,
        color: BRICK_COLORS[r],
        alive: true
      });
    }
  }
}

function resetBall() {
  ball.x = W / 2;
  ball.y = H - 100;
  ball.vx = (Math.random() - 0.5) * 4;
  ball.vy = -6;
  ball.trail = [];
}

function startGame() {
  score = 0;
  lives = 3;
  level = 1;
  combo = 0;
  initBricks();
  resetBall();
  state = 'playing';
}

function spawnParticles(x, y, color, count = 10) {
  for (let i = 0; i < count; i++) {
    const angle = Math.random() * Math.PI * 2;
    const speed = 2 + Math.random() * 3;
    particles.push({
      x, y,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed,
      life: 30,
      maxLife: 30,
      color,
      size: 3 + Math.random() * 3
    });
  }
}

function circleRect(cx, cy, r, rx, ry, rw, rh) {
  const closestX = Math.max(rx, Math.min(cx, rx + rw));
  const closestY = Math.max(ry, Math.min(cy, ry + rh));
  const dx = cx - closestX;
  const dy = cy - closestY;
  return dx * dx + dy * dy < r * r;
}

function update() {
  if (state === 'menu') { menuPulse += 0.05; return; }
  if (state === 'levelComplete') { levelTimer--; if (levelTimer <= 0) { level++; initBricks(); resetBall(); state = 'playing'; } return; }
  if (state === 'gameOver' || state === 'win') return;

  // Paddle follows mouse
  paddle.x = Math.max(0, Math.min(W - PADDLE_W, mouseX - PADDLE_W / 2));

  // Ball trail
  ball.trail.push({ x: ball.x, y: ball.y });
  if (ball.trail.length > TRAIL_LENGTH) ball.trail.shift();

  // Gravity
  ball.vy += GRAVITY;

  // Move
  ball.x += ball.vx;
  ball.y += ball.vy;

  // Wall collisions
  if (ball.x - BALL_RADIUS < 0) { ball.x = BALL_RADIUS; ball.vx = Math.abs(ball.vx) * 0.8; }
  if (ball.x + BALL_RADIUS > W) { ball.x = W - BALL_RADIUS; ball.vx = -Math.abs(ball.vx) * 0.8; }
  if (ball.y - BALL_RADIUS < 0) { ball.y = BALL_RADIUS; ball.vy = Math.abs(ball.vy) * 0.8; }

  // Paddle collision
  if (circleRect(ball.x, ball.y, BALL_RADIUS, paddle.x, paddle.y, PADDLE_W, PADDLE_H)) {
    const hitPos = (ball.x - paddle.x) / PADDLE_W; // 0..1
    const angle = (hitPos - 0.5) * Math.PI * 0.7; // -63° to +63°
    const speed = Math.sqrt(ball.vx * ball.vx + ball.vy * ball.vy);
    const newSpeed = Math.max(speed, 8);
    ball.vx = Math.sin(angle) * newSpeed;
    ball.vy = -Math.abs(Math.cos(angle) * newSpeed);
    ball.y = paddle.y - BALL_RADIUS;
    spawnParticles(ball.x, ball.y, '#8B5CF6', 4);
  }

  // Brick collisions
  for (let b of bricks) {
    if (!b.alive) continue;
    if (circleRect(ball.x, ball.y, BALL_RADIUS, b.x, b.y, b.w, b.h)) {
      b.alive = false;
      // Determine bounce direction
      const bCenterX = b.x + b.w / 2;
      const bCenterY = b.y + b.h / 2;
      const dx = ball.x - bCenterX;
      const dy = ball.y - bCenterY;
      if (Math.abs(dx / b.w) > Math.abs(dy / b.h)) {
        ball.vx = dx > 0 ? Math.abs(ball.vx) : -Math.abs(ball.vx);
      } else {
        ball.vy = dy > 0 ? Math.abs(ball.vy) : -Math.abs(ball.vy);
      }
      ball.vx *= 0.5;
      ball.vy *= 0.5;
      if (ball.vy > -2) ball.vy = -2;

      combo++;
      const points = 10 * level + (combo > 1 ? (combo - 1) * 5 : 0);
      score += points;
      spawnParticles(b.x + b.w/2, b.y + b.h/2, b.color, 10);

      // Level complete check
      if (bricks.every(b => !b.alive)) {
        state = 'levelComplete';
        levelTimer = 120;
      }
      break;
    }
  }

  // Ball falls
  if (ball.y > H + BALL_RADIUS) {
    lives--;
    combo = 0;
    if (lives <= 0) {
      state = 'gameOver';
    } else {
      resetBall();
    }
  }

  // Particles update
  particles = particles.filter(p => {
    p.x += p.vx;
    p.y += p.vy;
    p.vy += 0.1;
    p.life--;
    return p.life > 0;
  });

  // Win check
  if (level === 5 && bricks.every(b => !b.alive) && state === 'playing') {
    state = 'win';
  }
}

function draw() {
  // Background
  ctx.fillStyle = '#0a0a0f';
  ctx.fillRect(0, 0, W, H);

  // Scanlines
  ctx.fillStyle = 'rgba(255,255,255,0.03)';
  for (let y = 0; y < H; y += 3) {
    ctx.fillRect(0, y, W, 1);
  }

  if (state === 'menu') {
    // Title
    const glow = Math.sin(menuPulse) * 10 + 20;
    ctx.save();
    ctx.shadowColor = '#4ADE80';
    ctx.shadowBlur = glow;
    ctx.fillStyle = '#4ADE80';
    ctx.font = 'bold 48px Courier New';
    ctx.textAlign = 'center';
    ctx.fillText('NEON', W/2, H/2 - 40);
    ctx.fillStyle = '#F472B6';
    ctx.shadowColor = '#F472B6';
    ctx.fillText('PINBALL', W/2, H/2 + 20);
    ctx.restore();
    ctx.fillStyle = 'rgba(255,255,255,0.5)';
    ctx.font = '16px Courier New';
    ctx.textAlign = 'center';
    ctx.fillText('Click to Start', W/2, H/2 + 80);
    ctx.fillText('Move mouse to control paddle', W/2, H/2 + 105);
    return;
  }

  // UI
  ctx.fillStyle = '#4ADE80';
  ctx.font = 'bold 18px Courier New';
  ctx.textAlign = 'left';
  ctx.shadowColor = '#4ADE80';
  ctx.shadowBlur = 10;
  ctx.fillText(`SCORE: ${score.toString().padStart(5, '0')}`, 15, 30);
  ctx.textAlign = 'right';
  ctx.fillText(`LV:${level}`, W - 15, 30);
  ctx.shadowBlur = 0;

  // Lives
  for (let i = 0; i < lives; i++) {
    ctx.beginPath();
    ctx.arc(20 + i * 20, 55, 6, 0, Math.PI * 2);
    ctx.fillStyle = '#06B6D4';
    ctx.shadowColor = '#06B6D4';
    ctx.shadowBlur = 8;
    ctx.fill();
    ctx.shadowBlur = 0;
  }

  // Target
  ctx.fillStyle = 'rgba(255,255,255,0.3)';
  ctx.font = '12px Courier New';
  ctx.textAlign = 'left';
  ctx.fillText(`TARGET: ${LEVEL_TARGETS[level-1]}`, 15, 72);

  // Bricks
  for (let b of bricks) {
    if (!b.alive) continue;
    ctx.save();
    ctx.shadowColor = b.color;
    ctx.shadowBlur = 8;
    const grad = ctx.createLinearGradient(b.x, b.y, b.x, b.y + b.h);
    grad.addColorStop(0, b.color);
    grad.addColorStop(1, shadeColor(b.color, -30));
    ctx.fillStyle = grad;
    roundRect(ctx, b.x, b.y, b.w, b.h, 4);
    ctx.fill();
    // Inner glow
    ctx.shadowBlur = 0;
    ctx.strokeStyle = 'rgba(255,255,255,0.2)';
    ctx.lineWidth = 1;
    roundRect(ctx, b.x + 2, b.y + 2, b.w - 4, b.h - 4, 3);
    ctx.stroke();
    ctx.restore();
  }

  // Ball trail
  for (let i = 0; i < ball.trail.length; i++) {
    const t = ball.trail[i];
    const alpha = (i / ball.trail.length) * 0.4;
    const radius = BALL_RADIUS * (i / ball.trail.length) * 0.7;
    ctx.beginPath();
    ctx.arc(t.x, t.y, radius, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(6, 182, 212, ${alpha})`;
    ctx.fill();
  }

  // Ball
  ctx.save();
  ctx.shadowColor = '#06B6D4';
  ctx.shadowBlur = 15;
  ctx.beginPath();
  ctx.arc(ball.x, ball.y, BALL_RADIUS, 0, Math.PI * 2);
  ctx.fillStyle = '#ffffff';
  ctx.fill();
  // Inner shine
  ctx.beginPath();
  ctx.arc(ball.x - 2, ball.y - 2, BALL_RADIUS * 0.4, 0, Math.PI * 2);
  ctx.fillStyle = 'rgba(255,255,255,0.8)';
  ctx.fill();
  ctx.restore();

  // Paddle
  ctx.save();
  ctx.shadowColor = '#8B5CF6';
  ctx.shadowBlur = 15;
  const pGrad = ctx.createLinearGradient(paddle.x, paddle.y, paddle.x + PADDLE_W, paddle.y);
  pGrad.addColorStop(0, '#6366F1');
  pGrad.addColorStop(0.5, '#8B5CF6');
  pGrad.addColorStop(1, '#6366F1');
  ctx.fillStyle = pGrad;
  roundRect(ctx, paddle.x, paddle.y, PADDLE_W, PADDLE_H, 7);
  ctx.fill();
  ctx.restore();

  // Particles
  for (let p of particles) {
    const alpha = p.life / p.maxLife;
    ctx.beginPath();
    ctx.arc(p.x, p.y, p.size * alpha, 0, Math.PI * 2);
    ctx.fillStyle = hexToRgba(p.color, alpha);
    ctx.fill();
  }

  // Overlays
  if (state === 'levelComplete') {
    ctx.fillStyle = 'rgba(0,0,0,0.6)';
    ctx.fillRect(0, 0, W, H);
    ctx.save();
    ctx.shadowColor = '#4ADE80';
    ctx.shadowBlur = 20;
    ctx.fillStyle = '#4ADE80';
    ctx.font = 'bold 36px Courier New';
    ctx.textAlign = 'center';
    ctx.fillText(`LEVEL ${level} CLEAR!`, W/2, H/2);
    ctx.restore();
  }

  if (state === 'gameOver') {
    ctx.fillStyle = 'rgba(0,0,0,0.8)';
    ctx.fillRect(0, 0, W, H);
    ctx.save();
    ctx.shadowColor = '#EF4444';
    ctx.shadowBlur = 20;
    ctx.fillStyle = '#EF4444';
    ctx.font = 'bold 40px Courier New';
    ctx.textAlign = 'center';
    ctx.fillText('GAME OVER', W/2, H/2 - 20);
    ctx.shadowBlur = 0;
    ctx.fillStyle = 'rgba(255,255,255,0.7)';
    ctx.font = '20px Courier New';
    ctx.fillText(`Score: ${score}`, W/2, H/2 + 25);
    ctx.fillStyle = 'rgba(255,255,255,0.4)';
    ctx.font = '14px Courier New';
    ctx.fillText('Click to restart', W/2, H/2 + 60);
    ctx.restore();
  }

  if (state === 'win') {
    ctx.fillStyle = 'rgba(0,0,0,0.8)';
    ctx.fillRect(0, 0, W, H);
    ctx.save();
    ctx.shadowColor = '#FACC15';
    ctx.shadowBlur = 30;
    ctx.fillStyle = '#FACC15';
    ctx.font = 'bold 48px Courier New';
    ctx.textAlign = 'center';
    ctx.fillText('YOU WIN!', W/2, H/2 - 30);
    ctx.shadowBlur = 0;
    ctx.fillStyle = 'rgba(255,255,255,0.7)';
    ctx.font = '20px Courier New';
    ctx.fillText(`Final Score: ${score}`, W/2, H/2 + 20);
    ctx.fillStyle = 'rgba(255,255,255,0.4)';
    ctx.font = '14px Courier New';
    ctx.fillText('Click to play again', W/2, H/2 + 55);
    ctx.restore();
  }
}

function shadeColor(color, percent) {
  const num = parseInt(color.replace('#',''), 16);
  const amt = Math.round(2.55 * percent);
  const R = Math.min(255, Math.max(0, (num >> 16) + amt));
  const G = Math.min(255, Math.max(0, ((num >> 8) & 0x00FF) + amt));
  const B = Math.min(255, Math.max(0, (num & 0x0000FF) + amt));
  return `#${(0x1000000 + R * 0x10000 + G * 0x100 + B).toString(16).slice(1)}`;
}

function hexToRgba(hex, alpha) {
  const num = parseInt(hex.replace('#',''), 16);
  return `rgba(${(num>>16)&255},${(num>>8)&255},${num&255},${alpha})`;
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

function gameLoop() {
  update();
  draw();
  requestAnimationFrame(gameLoop);
}

// === INPUT ===
canvas.addEventListener('mousemove', e => {
  const rect = canvas.getBoundingClientRect();
  mouseX = e.clientX - rect.left;
});

canvas.addEventListener('click', () => {
  if (state === 'menu') startGame();
  else if (state === 'gameOver' || state === 'win') state = 'menu';
});

// Touch support
canvas.addEventListener('touchmove', e => {
  e.preventDefault();
  const rect = canvas.getBoundingClientRect();
  mouseX = e.touches[0].clientX - rect.left;
}, { passive: false });

canvas.addEventListener('touchstart', e => {
  e.preventDefault();
  if (state === 'menu') startGame();
  else if (state === 'gameOver' || state === 'win') state = 'menu';
}, { passive: false });

// Start
gameLoop();
</script>
</body>
</html>
```

- [ ] **Step 2: 在浏览器验证**
  - 打开 `index.html`，确认 Canvas 正常渲染
  - 确认鼠标跟随、弹珠下落、碰撞反弹工作正常

---

## Task 2: 视觉增强与调优

- [ ] **Step 1: 优化砖块行间距和数量**
  - 确认 5 行 6 列对齐，居中无偏移

- [ ] **Step 2: 验证关卡递进**
  - Level 3 随机空缺逻辑确认
  - Level 5 更稀疏布局确认

- [ ] **Step 3: 调整物理参数**
  - 弹珠速度下限保证不卡死
  - 挡板弹性系数调优

---

## Task 3: 最终测试与交付

- [ ] **Step 1: 完整游戏流程测试**
  - menu → playing → levelComplete → next level → win
  - Game Over 流程
  - 重玩流程

- [ ] **Step 2: 在浏览器打开验证**
