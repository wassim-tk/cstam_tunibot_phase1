/**
 * CSTAM-TUNIBOT Dashboard JavaScript Controller
 * 2D Canvas Map Renderer & Real-Time Telemetry Client
 */

document.addEventListener('DOMContentLoaded', () => {
  const canvas = document.getElementById('map-canvas');
  const ctx = canvas.getContext('2d');

  // Map Coordinates Setup (World bounds: -5.0 to +5.0)
  const WORLD_MIN = -5.0;
  const WORLD_MAX = 5.0;
  const CANVAS_SIZE = 600;

  let telemetryData = null;
  let ws = null;
  let dynamicObstacleActive = false;

  // Transform World (x, y) to Canvas Pixel (px, py)
  function worldToCanvas(x, y) {
    const px = ((x - WORLD_MIN) / (WORLD_MAX - WORLD_MIN)) * CANVAS_SIZE;
    const py = ((WORLD_MAX - y) / (WORLD_MAX - WORLD_MIN)) * CANVAS_SIZE;
    return { x: px, y: py };
  }

  // Render 2D Indoor Environment Map
  function renderMap() {
    ctx.clearRect(0, 0, CANVAS_SIZE, CANVAS_SIZE);

    // 1. Draw Grid Background
    ctx.strokeStyle = '#1e293b';
    ctx.lineWidth = 1;
    const step = CANVAS_SIZE / 10;
    for (let i = 0; i <= CANVAS_SIZE; i += step) {
      ctx.beginPath();
      ctx.moveTo(i, 0); ctx.lineTo(i, CANVAS_SIZE);
      ctx.moveTo(0, i); ctx.lineTo(CANVAS_SIZE, i);
      ctx.stroke();
    }

    // 2. Draw Walls & Layout Geometry
    ctx.fillStyle = '#334155';
    // Outer Walls border
    ctx.fillRect(0, 0, CANVAS_SIZE, 12);
    ctx.fillRect(0, CANVAS_SIZE - 12, CANVAS_SIZE, 12);
    ctx.fillRect(0, 0, 12, CANVAS_SIZE);
    ctx.fillRect(CANVAS_SIZE - 12, 0, 12, CANVAS_SIZE);

    // Interior Partition Walls at y=1.0 with Doorway Gap (x=0 to x=1)
    const p1 = worldToCanvas(-3.0, 1.1);
    const p2 = worldToCanvas(0.0, 0.9);
    ctx.fillRect(p1.x, p1.y, p2.x - p1.x, p2.y - p1.y);

    const p3 = worldToCanvas(1.0, 1.1);
    const p4 = worldToCanvas(4.0, 0.9);
    ctx.fillRect(p3.x, p3.y, p4.x - p3.x, p4.y - p3.y);

    // 3. Draw Predefined Waypoints
    if (telemetryData && telemetryData.waypoints) {
      Object.entries(telemetryData.waypoints).forEach(([name, wp]) => {
        const pt = worldToCanvas(wp.x, wp.y);

        if (name === "Dock") {
          // Green Docking Station Square
          ctx.fillStyle = 'rgba(16, 185, 129, 0.2)';
          ctx.strokeStyle = '#10b981';
          ctx.lineWidth = 2;
          ctx.fillRect(pt.x - 20, pt.y - 20, 40, 40);
          ctx.strokeRect(pt.x - 20, pt.y - 20, 40, 40);

          ctx.fillStyle = '#10b981';
          ctx.font = '11px Inter';
          ctx.fillText("⚡ DOCK", pt.x - 20, pt.y - 25);
        } else {
          // Waypoint Circle
          ctx.beginPath();
          ctx.arc(pt.x, pt.y, 14, 0, Math.PI * 2);
          ctx.fillStyle = 'rgba(245, 158, 11, 0.2)';
          ctx.fill();
          ctx.strokeStyle = '#f59e0b';
          ctx.lineWidth = 2;
          ctx.stroke();

          ctx.fillStyle = '#f59e0b';
          ctx.font = '11px Inter';
          ctx.fillText(name, pt.x - 18, pt.y - 18);
        }
      });
    }

    // 4. Draw Dynamic Obstacle if active
    if (telemetryData && telemetryData.dynamic_obstacle && telemetryData.dynamic_obstacle.active) {
      const obsPt = worldToCanvas(telemetryData.dynamic_obstacle.pose.x, telemetryData.dynamic_obstacle.pose.y);
      ctx.beginPath();
      ctx.arc(obsPt.x, obsPt.y, 16, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(239, 68, 68, 0.3)';
      ctx.fill();
      ctx.strokeStyle = '#ef4444';
      ctx.lineWidth = 2;
      ctx.stroke();

      ctx.fillStyle = '#ef4444';
      ctx.font = '11px Inter';
      ctx.fillText("🚶 Human Obstacle", obsPt.x - 30, obsPt.y - 22);
    }

    // 5. Draw Robot Model & Trajectory
    if (telemetryData && telemetryData.robot_pose) {
      const rPt = worldToCanvas(telemetryData.robot_pose.x, telemetryData.robot_pose.y);
      
      // Draw Direction Heading Line
      ctx.beginPath();
      ctx.moveTo(rPt.x, rPt.y);
      const headX = rPt.x + Math.cos(telemetryData.robot_pose.yaw) * 25;
      const headY = rPt.y - Math.sin(telemetryData.robot_pose.yaw) * 25;
      ctx.lineTo(headX, headY);
      ctx.strokeStyle = '#06b6d4';
      ctx.lineWidth = 3;
      ctx.stroke();

      // Draw Robot Circular Body
      ctx.beginPath();
      ctx.arc(rPt.x, rPt.y, 18, 0, Math.PI * 2);
      ctx.fillStyle = '#3b82f6';
      ctx.fill();
      ctx.strokeStyle = '#60a5fa';
      ctx.lineWidth = 3;
      ctx.stroke();

      // Robot Label
      ctx.fillStyle = '#ffffff';
      ctx.font = 'bold 10px Inter';
      ctx.fillText("ROBOT", rPt.x - 18, rPt.y + 4);
    }

    requestAnimationFrame(renderMap);
  }

  // WebSocket Connection Handler
  function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/telemetry`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      document.getElementById('conn-text').textContent = 'Connected (Live)';
      document.querySelector('#connection-status .dot').className = 'dot online';
      logSystem("WebSocket telemetry stream connected.");
    };

    ws.onmessage = (event) => {
      try {
        telemetryData = JSON.parse(event.data);
        updateDashboardUI(telemetryData);
      } catch (err) {
        console.error("Error parsing WebSocket JSON payload:", err);
      }
    };

    ws.onclose = () => {
      document.getElementById('conn-text').textContent = 'Disconnected';
      document.querySelector('#connection-status .dot').className = 'dot offline';
      setTimeout(connectWebSocket, 2000);
    };
  }

  // Update UI Elements with Live Telemetry
  function updateDashboardUI(data) {
    // Battery UI
    const batPct = data.battery_percentage;
    document.getElementById('battery-pct-text').textContent = `${batPct.toFixed(1)}%`;
    document.getElementById('battery-fill').style.width = `${batPct}%`;
    document.getElementById('battery-voltage-text').textContent = `${data.voltage} V`;

    if (batPct < 20) {
      document.getElementById('battery-fill').style.background = '#ef4444';
    } else if (batPct < 50) {
      document.getElementById('battery-fill').style.background = '#f59e0b';
    } else {
      document.getElementById('battery-fill').style.background = '#10b981';
    }

    // Robot State Badge
    const stateText = (data.robot_state || "IDLE").toUpperCase();
    document.getElementById('robot-state-text').textContent = stateText;
    const dot = document.querySelector('#robot-state-badge .dot');
    dot.className = `dot ${data.robot_state || 'idle'}`;

    // Pose Card
    const px = data.robot_pose.x.toFixed(2);
    const py = data.robot_pose.y.toFixed(2);
    document.getElementById('robot-pos-text').textContent = `X: ${px}, Y: ${py}`;

    // Current Task Card
    if (data.current_task) {
      document.getElementById('current-task-text').textContent = `${data.current_task.id} -> ${data.current_task.target} (${data.current_task.item})`;
    } else {
      document.getElementById('current-task-text').textContent = 'None (Idle)';
    }

    // Queue List UI
    const queueList = document.getElementById('queue-list');
    if (!data.queue || data.queue.length === 0) {
      queueList.innerHTML = '<div class="empty-state">No active pending tasks in queue.</div>';
    } else {
      queueList.innerHTML = data.queue.map(item => `
        <div class="queue-item">
          <div class="queue-item-info">
            <span class="queue-id">${item.id}</span>
            <span class="queue-target">📍 ${item.target}</span>
            <span class="queue-item-name">${item.item}</span>
          </div>
          <span class="badge user-badge">${item.status}</span>
        </div>
      `).join('');
    }
  }

  // User Form Submission
  document.getElementById('delivery-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const target = document.getElementById('target-select').value;
    const item = document.getElementById('item-input').value;

    try {
      const res = await fetch('/api/delivery', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target, item })
      });
      const data = await res.json();
      if (res.ok) {
        logSystem(`Delivery requested: ${data.task.id} to ${target}`);
        document.getElementById('item-input').value = '';
      } else {
        logSystem(`Error: ${data.detail}`, 'warn');
      }
    } catch (err) {
      logSystem(`Network error submitting delivery`, 'warn');
    }
  });

  // Admin Manual Dock Button
  document.getElementById('manual-dock-btn').addEventListener('click', async () => {
    try {
      const res = await fetch('/api/dock', { method: 'POST' });
      const data = await res.json();
      logSystem("Admin triggered manual return to dock.", 'info');
    } catch (err) {
      logSystem("Failed to send dock command.", 'warn');
    }
  });

  // Toggle Dynamic Obstacle Button
  document.getElementById('toggle-obstacle-btn').addEventListener('click', async () => {
    dynamicObstacleActive = !dynamicObstacleActive;
    try {
      const res = await fetch('/api/obstacle/trigger', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active: dynamicObstacleActive })
      });
      logSystem(`Dynamic obstacle toggled: ${dynamicObstacleActive ? 'ACTIVE' : 'INACTIVE'}`, 'info');
    } catch (err) {
      logSystem("Failed to toggle dynamic obstacle.", 'warn');
    }
  });

  // Clear Queue Button
  document.getElementById('clear-queue-btn').addEventListener('click', async () => {
    try {
      await fetch('/api/queue', { method: 'DELETE' });
      logSystem("Task queue cleared by admin.", 'info');
    } catch (err) {
      logSystem("Failed to clear task queue.", 'warn');
    }
  });

  function logSystem(msg, type = 'system') {
    const logBox = document.getElementById('sys-log');
    const entry = document.createElement('div');
    entry.className = `log-entry ${type}`;
    const timeStr = new Date().toLocaleTimeString();
    entry.textContent = `[${timeStr}] ${msg}`;
    logBox.appendChild(entry);
    logBox.scrollTop = logBox.scrollHeight;
  }

  // Start Map Animation & WebSocket Connection
  renderMap();
  connectWebSocket();
});
