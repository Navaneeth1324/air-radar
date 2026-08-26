/**
 * AirRadar Canvas Engine & WebSocket Client
 * Real-time 60FPS polar radar visualizer with sweep line, glow shaders, and sound effects.
 */

// State
let devices = {};
let selectedDeviceId = null;
let currentFilter = 'ALL';
let searchQuery = '';
let soundEnabled = false;
let audioCtx = null;

// Canvas & Animation
const canvas = document.getElementById('radarCanvas');
const ctx = canvas.getContext('2d');
let sweepAngle = 0.0;
const SWEEP_SPEED = 0.035; // radians per frame (~1.5s per rotation)

// Resize Canvas
function resizeCanvas() {
  const rect = canvas.parentElement.getBoundingClientRect();
  const size = Math.min(rect.width, rect.height, 520);
  const dpr = window.devicePixelRatio || 1;
  canvas.width = size * dpr;
  canvas.height = size * dpr;
  ctx.scale(dpr, dpr);
}
window.addEventListener('resize', resizeCanvas);
resizeCanvas();

// Web Audio API Synth Ping
function playRadarPing(freq = 880) {
  if (!soundEnabled) return;
  try {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    if (audioCtx.state === 'suspended') audioCtx.resume();

    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();

    osc.type = 'sine';
    osc.frequency.setValueAtTime(freq, audioCtx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(freq * 0.5, audioCtx.currentTime + 0.15);

    gain.gain.setValueAtTime(0.06, audioCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.15);

    osc.connect(gain);
    gain.connect(audioCtx.destination);

    osc.start();
    osc.stop(audioCtx.currentTime + 0.15);
  } catch (e) {
    console.debug('Audio error:', e);
  }
}

// Blip Color Helper
function getBlipColor(device) {
  if (device.threats && device.threats.some(t => t.level === 'ALERT')) {
    return '#ef4444'; // Red
  }
  if (device.threats && device.threats.some(t => t.level === 'WARN')) {
    return '#f59e0b'; // Amber
  }
  switch (device.category) {
    case 'tracker': return '#ef4444';
    case 'audio': return '#00f0ff';
    case 'tv_media': return '#a855f7';
    case 'smart_home': return '#10b981';
    case 'wearable': return '#3b82f6';
    default: return '#22d3ee';
  }
}

// Render Loop
function drawRadar() {
  const rect = canvas.getBoundingClientRect();
  const width = rect.width;
  const height = rect.height;
  const cx = width / 2;
  const cy = height / 2;
  const maxR = (width / 2) - 16;

  ctx.clearRect(0, 0, width, height);

  // 1. Draw Radar Background
  ctx.fillStyle = '#060a12';
  ctx.beginPath();
  ctx.arc(cx, cy, maxR, 0, Math.PI * 2);
  ctx.fill();

  // 2. Draw Concentric Rings
  const rings = [0.2, 0.4, 0.6, 0.8, 1.0];
  const ringDistLabels = ['1m', '3m', '5m', '10m', '20m+'];

  rings.forEach((rRatio, idx) => {
    const r = maxR * rRatio;
    ctx.strokeStyle = 'rgba(34, 211, 238, 0.15)';
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.stroke();

    // Distance Label
    ctx.setLineDash([]);
    ctx.fillStyle = 'rgba(34, 211, 238, 0.4)';
    ctx.font = '9px monospace';
    ctx.fillText(ringDistLabels[idx], cx + 4, cy - r + 10);
  });

  // 3. Draw Crosshairs & Degree Ticks
  ctx.strokeStyle = 'rgba(34, 211, 238, 0.2)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(cx - maxR, cy);
  ctx.lineTo(cx + maxR, cy);
  ctx.moveTo(cx, cy - maxR);
  ctx.lineTo(cx, cy + maxR);
  ctx.stroke();

  // 4. Draw Phosphor Sweep Arc (Trailing Gradient)
  sweepAngle = (sweepAngle + SWEEP_SPEED) % (Math.PI * 2);
  const trailSegments = 30;
  const trailAngle = Math.PI / 4; // 45 degree tail

  for (let i = 0; i < trailSegments; i++) {
    const startA = sweepAngle - (trailAngle * (i + 1) / trailSegments);
    const endA = sweepAngle - (trailAngle * i / trailSegments);
    const alpha = 0.25 * (1 - (i / trailSegments));

    ctx.fillStyle = `rgba(0, 240, 255, ${alpha})`;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.arc(cx, cy, maxR, startA, endA);
    ctx.closePath();
    ctx.fill();
  }

  // Active Sweep Line
  ctx.strokeStyle = '#00f0ff';
  ctx.lineWidth = 2;
  ctx.shadowColor = '#00f0ff';
  ctx.shadowBlur = 8;
  ctx.beginPath();
  ctx.moveTo(cx, cy);
  ctx.lineTo(cx + Math.cos(sweepAngle) * maxR, cy + Math.sin(sweepAngle) * maxR);
  ctx.stroke();
  ctx.shadowBlur = 0; // Reset shadow

  // 5. Draw Device Blips
  const devList = Object.values(devices);
  devList.forEach(dev => {
    const angle = dev.radar_angle || 0;
    // Map distance to radius ratio (clamped 0.15 to 0.95)
    const dist = dev.estimated_distance_m || 5.0;
    const normR = Math.min(0.95, Math.max(0.15, dist / 22.0));
    const bx = cx + Math.cos(angle) * (maxR * normR);
    const by = cy + Math.sin(angle) * (maxR * normR);

    // Calculate angle difference relative to sweep
    let diff = (sweepAngle - angle) % (Math.PI * 2);
    if (diff < 0) diff += Math.PI * 2;

    // Flash intensity when sweep passes
    const isLit = diff < 0.15;
    const isSelected = selectedDeviceId === dev.id;
    const color = getBlipColor(dev);

    if (isLit && !dev._wasLit) {
      playRadarPing(dev.category === 'tracker' ? 1200 : 750);
      dev._wasLit = true;
    } else if (!isLit) {
      dev._wasLit = false;
    }

    // Outer Glow Ring
    ctx.beginPath();
    ctx.arc(bx, by, isLit || isSelected ? 10 : 5, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.shadowColor = color;
    ctx.shadowBlur = isLit || isSelected ? 16 : 6;
    ctx.fill();
    ctx.shadowBlur = 0;

    // Center Dot
    ctx.beginPath();
    ctx.arc(bx, by, isSelected ? 4 : 2.5, 0, Math.PI * 2);
    ctx.fillStyle = '#ffffff';
    ctx.fill();

    // Device Label
    if (isSelected || isLit) {
      ctx.fillStyle = '#ffffff';
      ctx.font = '10px monospace';
      ctx.fillText(dev.name.slice(0, 16), bx + 8, by - 6);
    }
  });

  requestAnimationFrame(drawRadar);
}

// Canvas Click Hit Detection
canvas.addEventListener('click', (e) => {
  const rect = canvas.getBoundingClientRect();
  const cx = rect.width / 2;
  const cy = rect.height / 2;
  const maxR = (rect.width / 2) - 16;
  const clickX = e.clientX - rect.left;
  const clickY = e.clientY - rect.top;

  let closestDev = null;
  let minDist = 25; // 25px hit target

  Object.values(devices).forEach(dev => {
    const angle = dev.radar_angle || 0;
    const dist = dev.estimated_distance_m || 5.0;
    const normR = Math.min(0.95, Math.max(0.15, dist / 22.0));
    const bx = cx + Math.cos(angle) * (maxR * normR);
    const by = cy + Math.sin(angle) * (maxR * normR);

    const d = Math.hypot(clickX - bx, clickY - by);
    if (d < minDist) {
      minDist = d;
      closestDev = dev;
    }
  });

  if (closestDev) {
    selectDevice(closestDev.id);
  }
});

// UI Rendering
function renderDeviceList() {
  const listEl = document.getElementById('deviceList');
  const filtered = Object.values(devices).filter(d => {
    if (currentFilter !== 'ALL' && d.protocol !== currentFilter) return false;
    if (searchQuery && !d.name.toLowerCase().includes(searchQuery) && !d.vendor.toLowerCase().includes(searchQuery)) return false;
    return true;
  });

  listEl.innerHTML = filtered.map(d => {
    const isSelected = selectedDeviceId === d.id;
    const hasAlert = d.threats && d.threats.some(t => t.level === 'ALERT');
    const hasWarn = d.threats && d.threats.some(t => t.level === 'WARN');
    const threatClass = hasAlert ? 'threat-alert' : hasWarn ? 'threat-warn' : '';

    return `
      <div class="device-card ${threatClass} ${isSelected ? 'selected' : ''}" onclick="selectDevice('${d.id}')">
        <div class="device-row-top">
          <span class="device-name">
            ${d.name}
          </span>
          <span class="protocol-badge ${d.protocol}">${d.protocol}</span>
        </div>
        <div class="device-row-mid">
          <span>Vendor: ${d.vendor}</span>
          <span>${d.rssi ? d.rssi + ' dBm' : (d.estimated_distance_m ? '~' + d.estimated_distance_m + 'm' : 'LAN')}</span>
        </div>
        ${hasAlert ? `<div class="device-threat-tag">⚠️ ${d.threats[0].title}</div>` : ''}
      </div>
    `;
  }).join('');
}

function updatePosture(posture) {
  if (!posture) return;
  document.getElementById('statScore').textContent = `${posture.score}/100`;
  document.getElementById('statTotal').textContent = posture.total_devices;
  document.getElementById('statTrackers').textContent = posture.tracker_count;
  document.getElementById('statAlerts').textContent = posture.alert_count + posture.warn_count;

  const scoreEl = document.getElementById('statScore');
  scoreEl.className = 'stat-value ' + (posture.score > 75 ? 'green' : posture.score > 50 ? 'cyan' : 'red');
}

function selectDevice(id) {
  selectedDeviceId = id;
  const dev = devices[id];
  if (!dev) return;

  renderDeviceList();
  openDeviceModal(dev);
}

function openDeviceModal(dev) {
  const modal = document.getElementById('deviceModal');
  document.getElementById('modalTitle').textContent = dev.name;
  document.getElementById('modalProtocol').textContent = dev.protocol;
  document.getElementById('modalVendor').textContent = dev.vendor;
  document.getElementById('modalCategory').textContent = dev.category;
  document.getElementById('modalRssi').textContent = dev.rssi ? `${dev.rssi} dBm (~${dev.estimated_distance_m}m)` : 'N/A';
  document.getElementById('modalIp').textContent = dev.ip_address ? `${dev.ip_address}:${dev.port || ''}` : 'N/A (Direct Wireless)';
  document.getElementById('modalPackets').textContent = dev.packet_count;

  const threatsEl = document.getElementById('modalThreats');
  if (dev.threats && dev.threats.length > 0) {
    threatsEl.innerHTML = dev.threats.map(t => `
      <div style="background: rgba(239, 68, 68, 0.1); border-left: 3px solid #ef4444; padding: 8px 12px; border-radius: 4px; margin-top: 8px;">
        <strong style="color: #ef4444;">${t.title}</strong>
        <p style="font-size: 0.78rem; color: #f3f4f6; margin-top: 4px;">${t.description}</p>
        ${t.remediation ? `<p style="font-size: 0.72rem; color: #22d3ee; margin-top: 4px;">💡 Action: ${t.remediation}</p>` : ''}
      </div>
    `).join('');
  } else {
    threatsEl.innerHTML = `<p style="color: #10b981; font-size: 0.8rem; margin-top: 8px;">✓ No privacy risks or unencrypted exposures identified.</p>`;
  }

  modal.classList.add('open');
}

function closeModal() {
  document.getElementById('deviceModal').classList.remove('open');
}

// WebSocket Connection
function connectWS() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws`;
  const ws = new WebSocket(wsUrl);

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'DEVICE_UPDATE') {
      devices[data.device.id] = data.device;
      renderDeviceList();
    } else if (data.type === 'SYNC_ALL') {
      data.devices.forEach(d => devices[d.id] = d);
      renderDeviceList();
      updatePosture(data.posture);
    } else if (data.type === 'POSTURE_UPDATE') {
      updatePosture(data.posture);
    }
  };

  ws.onclose = () => {
    setTimeout(connectWS, 2000); // Auto reconnect
  };
}

// Event Listeners
document.getElementById('searchInput').addEventListener('input', (e) => {
  searchQuery = e.target.value.toLowerCase();
  renderDeviceList();
});

document.querySelectorAll('.filter-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentFilter = btn.dataset.filter;
    renderDeviceList();
  });
});

document.getElementById('audioToggle').addEventListener('click', (e) => {
  soundEnabled = !soundEnabled;
  e.target.classList.toggle('active', soundEnabled);
  e.target.textContent = soundEnabled ? '🔊 Sound: ON' : '🔈 Sound: OFF';
  if (soundEnabled) playRadarPing(880);
});

// Start Engine
connectWS();
drawRadar();
