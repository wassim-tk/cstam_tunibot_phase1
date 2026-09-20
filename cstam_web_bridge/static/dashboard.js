/**
 * CSTAM Waiter Robot Dashboard Controller
 * 2D Canvas Map Renderer & Real-Time Physical Telemetry Client
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

  // Render 2D Indoor Restaurant Map
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

    // 2. Draw Outer Walls Border
    ctx.fillStyle = '#334155';
    ctx.fillRect(0, 0, CANVAS_SIZE, 12);
    ctx.fillRect(0, CANVAS_SIZE - 12, CANVAS_SIZE, 12);
    ctx.fillRect(0, 0, 12, CANVAS_SIZE);
    ctx.fillRect(CANVAS_SIZE - 12, 0, 12, CANVAS_SIZE);

    // 3. Draw Interior Partition Walls with Central Doorway Gap (x=0.0 to x=1.0 at y=1.0)
    // Left partition wall: x = -5.0 to 0.0, y = 0.9 to 1.1
    const p1 = worldToCanvas(-5.0, 1.1);
    const p2 = worldToCanvas(0.0, 0.9);
    ctx.fillStyle = '#475569';
    ctx.fillRect(p1.x, p1.y, p2.x - p1.x, p2.y - p1.y);

    // Right partition wall: x = 1.0 to 5.0, y = 0.9 to 1.1
    const p3 = worldToCanvas(1.0, 1.1);
    const p4 = worldToCanvas(5.0, 0.9);
    ctx.fillRect(p3.x, p3.y, p4.x - p3.x, p4.y - p3.y);

    // Doorway Guide Lines (Green dashed lines at x=0.0 and x=1.0)
    const dLeft = worldToCanvas(0.0, 1.1);
    const dRight = worldToCanvas(1.0, 0.9);
    ctx.strokeStyle = 'rgba(16, 185, 129, 0.4)';
    ctx.lineWidth = 2;
    ctx.setLineDash([4, 4]);
    ctx.strokeRect(dLeft.x, dLeft.y, dRight.x - dLeft.x, dRight.y - dLeft.y);
    ctx.setLineDash([]);
    ctx.fillStyle = 'rgba(16, 185, 129, 0.7)';
    ctx.font = '9px Inter';
    ctx.fillText("DOORWAY (1.0m)", dLeft.x + 6, dLeft.y - 4);

    // 4. Draw Waypoints / Dining Tables
    if (telemetryData && telemetryData.waypoints) {
      Object.entries(telemetryData.waypoints).forEach(([name, wp]) => {
        const pt = worldToCanvas(wp.x, wp.y);

        if (name === "Dock") {
          // Green Docking Station Pad
          ctx.fillStyle = 'rgba(16, 185, 129, 0.15)';
          ctx.strokeStyle = '#10b981';
          ctx.lineWidth = 2;
          ctx.fillRect(pt.x - 22, pt.y - 22, 44, 44);
          ctx.strokeRect(pt.x - 22, pt.y - 22, 44, 44);

          ctx.fillStyle = '#10b981';
          ctx.font = 'bold 11px Inter';
          ctx.fillText("⚡ DOCK", pt.x - 20, pt.y - 26);
        } else if (name.includes("Kitchen")) {
          // Kitchen Pickup Counter
          ctx.fillStyle = 'rgba(59, 130, 246, 0.2)';
          ctx.strokeStyle = '#3b82f6';
          ctx.lineWidth = 2;
          ctx.fillRect(pt.x - 26, pt.y - 26, 52, 52);
          ctx.strokeRect(pt.x - 26, pt.y - 26, 52, 52);

          ctx.fillStyle = '#3b82f6';
          ctx.font = 'bold 11px Inter';
          ctx.fillText("🍳 KITCHEN", pt.x - 26, pt.y - 30);
        } else {
          // Dining Tables
          ctx.beginPath();
          ctx.arc(pt.x, pt.y, 16, 0, Math.PI * 2);
          ctx.fillStyle = 'rgba(245, 158, 11, 0.15)';
          ctx.fill();
          ctx.strokeStyle = '#f59e0b';
          ctx.lineWidth = 2;
          ctx.stroke();

          ctx.fillStyle = '#f59e0b';
          ctx.font = 'bold 11px Inter';
          ctx.fillText(name, pt.x - 18, pt.y - 20);
        }
      });
    }

    // 5. Draw Planned Doorway Navigation Path (Dashed Line)
    if (telemetryData && telemetryData.planned_path && telemetryData.planned_path.length > 0) {
      ctx.beginPath();
      const startPt = worldToCanvas(telemetryData.robot_pose.x, telemetryData.robot_pose.y);
      ctx.moveTo(startPt.x, startPt.y);

      telemetryData.planned_path.forEach((wp) => {
        const p = worldToCanvas(wp.x, wp.y);
        ctx.lineTo(p.x, p.y);
      });

      ctx.strokeStyle = 'rgba(6, 182, 212, 0.6)';
      ctx.lineWidth = 2;
      ctx.setLineDash([6, 6]);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // 6. Draw Dynamic Obstacle (Walking Human with Safety Zone)
    if (telemetryData && telemetryData.dynamic_obstacle && telemetryData.dynamic_obstacle.active) {
      const obsPt = worldToCanvas(telemetryData.dynamic_obstacle.pose.x, telemetryData.dynamic_obstacle.pose.y);

      // Avoidance Safety Margin Zone (1.2m radius)
      const safetyRadius = (1.2 / 10.0) * CANVAS_SIZE;
      ctx.beginPath();
      ctx.arc(obsPt.x, obsPt.y, safetyRadius, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(239, 68, 68, 0.08)';
      ctx.fill();
      ctx.strokeStyle = 'rgba(239, 68, 68, 0.35)';
      ctx.lineWidth = 1.5;
      ctx.setLineDash([4, 4]);
      ctx.stroke();
      ctx.setLineDash([]);

      // Pedestrian Body
      ctx.beginPath();
      ctx.arc(obsPt.x, obsPt.y, 14, 0, Math.PI * 2);
      ctx.fillStyle = '#ef4444';
      ctx.fill();
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 2;
      ctx.stroke();

      ctx.fillStyle = '#ef4444';
      ctx.font = 'bold 11px Inter';
      ctx.fillText("🚶 Pedestrian", obsPt.x - 32, obsPt.y - 18);
    }

    // 7. Draw 3D Waiter Robot (Chassis, 3-Tier Shelves, Heading, Halo)
    if (telemetryData && telemetryData.robot_pose) {
      const rPt = worldToCanvas(telemetryData.robot_pose.x, telemetryData.robot_pose.y);
      const isAvoiding = telemetryData.avoidance_active || telemetryData.robot_state === "avoiding_obstacle" || telemetryData.robot_state === "yielding";

      // Evasive Maneuver Alert Ring
      if (isAvoiding) {
        ctx.beginPath();
        ctx.arc(rPt.x, rPt.y, 30, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(239, 68, 68, 0.2)';
        ctx.fill();
        ctx.strokeStyle = '#ef4444';
        ctx.lineWidth = 2;
        ctx.stroke();
      }

      // Robot Base Chassis
      ctx.save();
      ctx.translate(rPt.x, rPt.y);
      ctx.rotate(-telemetryData.robot_pose.yaw);

      // Chassis body
      ctx.beginPath();
      ctx.ellipse(0, 0, 18, 16, 0, 0, Math.PI * 2);
      ctx.fillStyle = '#0f172a';
      ctx.fill();
      ctx.strokeStyle = isAvoiding ? '#ef4444' : '#06b6d4';
      ctx.lineWidth = 2.5;
      ctx.stroke();

      // Draw 3-Tier Shelf Lines (Visualizing Waiter Tray Stack)
      ctx.strokeStyle = '#94a3b8';
      ctx.lineWidth = 1.5;
      // Shelf 1
      ctx.strokeRect(-8, -10, 14, 6);
      // Shelf 2
      ctx.strokeRect(-8, -3, 14, 6);
      // Shelf 3
      ctx.strokeRect(-8, 4, 14, 6);

      // Heading indicator nose
      ctx.beginPath();
      ctx.moveTo(14, 0);
      ctx.lineTo(24, 0);
      ctx.strokeStyle = '#06b6d4';
      ctx.lineWidth = 3;
      ctx.stroke();

      ctx.restore();

      // Robot Label
      ctx.fillStyle = '#ffffff';
      ctx.font = 'bold 10px Inter';
      ctx.fillText(isAvoiding ? "⚠️ AVOIDING" : "WAITER BOT", rPt.x - 28, rPt.y + 26);
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
      logSystem("WebSocket telemetry stream connected.", 'info');
    };

    ws.onmessage = (event) => {
      try {
        telemetryData = JSON.parse(event.data);
        updateDashboardUI(telemetryData);
      } catch (err) {
        console.error("Error parsing WebSocket payload:", err);
      }
    };

    ws.onclose = () => {
      document.getElementById('conn-text').textContent = 'Disconnected';
      document.querySelector('#connection-status .dot').className = 'dot offline';
      setTimeout(connectWebSocket, 2000);
    };
  }

  // Update UI Elements with Live Physical Telemetry
  function updateDashboardUI(data) {
    // 1. Physical Battery BMS Metrics
    const batPct = data.battery_percentage;
    document.getElementById('battery-pct-text').textContent = `${batPct.toFixed(1)}%`;
    document.getElementById('battery-fill').style.width = `${batPct}%`;
    document.getElementById('battery-voltage-text').textContent = `${data.voltage.toFixed(2)} V`;
    document.getElementById('battery-current-text').textContent = `${(data.current_amps || 0).toFixed(2)} A`;
    document.getElementById('battery-power-text').textContent = `${(data.power_watts || 0).toFixed(1)} W`;
    document.getElementById('battery-temp-text').textContent = `${(data.temperature_c || 24.5).toFixed(1)} °C`;

    if (batPct < 20) {
      document.getElementById('battery-fill').style.background = '#ef4444';
    } else if (batPct < 50) {
      document.getElementById('battery-fill').style.background = '#f59e0b';
    } else {
      document.getElementById('battery-fill').style.background = '#10b981';
    }

    // 2. Robot State & Avoidance Badge
    const stateText = (data.robot_state || "IDLE").toUpperCase();
    document.getElementById('robot-state-text').textContent = stateText;
    const dot = document.querySelector('#robot-state-badge .dot');
    dot.className = `dot ${data.robot_state || 'idle'}`;

    const avoidBadge = document.getElementById('avoidance-badge');
    if (data.avoidance_active || data.robot_state === "avoiding_obstacle" || data.robot_state === "yielding") {
      avoidBadge.style.display = 'inline-block';
      avoidBadge.textContent = data.robot_state === "yielding" ? "🛑 YIELDING TO HUMAN" : "⚠️ AVOIDING OBSTACLE";
    } else {
      avoidBadge.style.display = 'none';
    }

    // 3. Pose Coordinates
    const px = data.robot_pose.x.toFixed(2);
    const py = data.robot_pose.y.toFixed(2);
    document.getElementById('robot-pos-text').textContent = `X: ${px}, Y: ${py}`;

    // 4. Current Task
    if (data.current_task) {
      document.getElementById('current-task-text').textContent = `${data.current_task.id} -> ${data.current_task.target} (${data.current_task.item})`;
    } else {
      document.getElementById('current-task-text').textContent = 'None (Idle at Station)';
    }

    // 5. Waiter 3-Tier Shelves Status
    if (data.shelves) {
      const s3 = data.shelves.shelf_3;
      const s2 = data.shelves.shelf_2;
      const s1 = data.shelves.shelf_1;

      document.getElementById('shelf-3-item').textContent = s3.item ? `Loaded: ${s3.item}` : 'Empty / Ready';
      document.getElementById('shelf-2-item').textContent = s2.item ? `Loaded: ${s2.item}` : 'Empty / Ready';
      document.getElementById('shelf-1-item').textContent = s1.item ? `Loaded: ${s1.item}` : 'Empty / Ready';
    }

    // 6. Queue List UI
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
        logSystem(`Delivery requested: ${data.task.id} to ${target} (${item})`, 'info');
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
      logSystem("Admin commanded Waiter Bot to return to Dock.", 'info');
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
      logSystem(`Dynamic pedestrian obstacle: ${dynamicObstacleActive ? 'ACTIVATED (Entering corridor)' : 'DEACTIVATED'}`, 'info');
    } catch (err) {
      logSystem("Failed to toggle dynamic obstacle.", 'warn');
    }
  });

  // Clear Queue Button
  document.getElementById('clear-queue-btn').addEventListener('click', async () => {
    try {
      await fetch('/api/queue', { method: 'DELETE' });
      logSystem("Task queue and shelves cleared by admin.", 'info');
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
