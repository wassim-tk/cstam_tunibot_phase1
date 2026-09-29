/**
 * CSTAM Waiter Robot Dashboard Controller - Gazebo restaurant.world Adaptation
 * 2D Canvas Map Renderer & Real-Time Telemetry Client for BellaBot
 */

document.addEventListener('DOMContentLoaded', () => {
  const canvas = document.getElementById('map-canvas');
  const ctx = canvas.getContext('2d');

  // Map Coordinates Setup (Full bounds of Gazebo restaurant.world)
  const WORLD_MIN_X = -17.0;
  const WORLD_MAX_X = 9.0;   // 26m width
  const WORLD_MIN_Y = -19.0;
  const WORLD_MAX_Y = 6.0;   // 25m height

  let telemetryData = null;
  let ws = null;
  let dynamicObstacleActive = false;
  let restaurantLayout = { walls: [], tables: [] };
  let hoveredTable = null;

  // Viewport Pan, Zoom & Camera Follow State
  let zoomLevel = 1.0;
  let panOffsetX = 0.0;
  let panOffsetY = 0.0;
  let isFollowingRobot = true;
  let isDragging = false;
  let dragStartX = 0;
  let dragStartY = 0;

  // Set high-DPI canvas
  function adjustCanvasSize() {
    canvas.width = 650;
    canvas.height = 625;
  }
  adjustCanvasSize();

  // Raw World to Unscaled Canvas Pixel Transform
  function worldToCanvasRaw(x, y) {
    const px = ((x - WORLD_MIN_X) / (WORLD_MAX_X - WORLD_MIN_X)) * canvas.width;
    const py = ((WORLD_MAX_Y - y) / (WORLD_MAX_Y - WORLD_MIN_Y)) * canvas.height;
    return { x: px, y: py };
  }

  // Transform World (x, y) to Viewport Canvas Pixel (px, py) with Pan & Zoom
  function worldToCanvas(x, y) {
    const raw = worldToCanvasRaw(x, y);
    const cx = canvas.width / 2;
    const cy = canvas.height / 2;
    const px = cx + (raw.x - cx) * zoomLevel + panOffsetX;
    const py = cy + (raw.y - cy) * zoomLevel + panOffsetY;
    return { x: px, y: py };
  }

  // Transform Viewport Canvas Pixel to World (x, y)
  function canvasToWorld(px, py) {
    const cx = canvas.width / 2;
    const cy = canvas.height / 2;
    const rawX = (px - panOffsetX - cx) / zoomLevel + cx;
    const rawY = (py - panOffsetY - cy) / zoomLevel + cy;
    const x = WORLD_MIN_X + (rawX / canvas.width) * (WORLD_MAX_X - WORLD_MIN_X);
    const y = WORLD_MAX_Y - (rawY / canvas.height) * (WORLD_MAX_Y - WORLD_MIN_Y);
    return { x, y };
  }

  // Fetch restaurant geometric layout
  async function loadRestaurantLayout() {
    try {
      const res = await fetch('/api/map/layout');
      if (res.ok) {
        restaurantLayout = await res.json();
      }
    } catch (e) {
      console.warn("Could not load /api/map/layout, using embedded fallback:", e);
    }
  }
  loadRestaurantLayout();

  // Interactive Mouse Wheel Zooming (Zoom towards cursor position)
  canvas.addEventListener('wheel', (e) => {
    e.preventDefault();
    const zoomFactor = e.deltaY < 0 ? 1.15 : 0.87;
    const newZoom = Math.max(0.5, Math.min(4.5, zoomLevel * zoomFactor));

    const rect = canvas.getBoundingClientRect();
    const mouseX = (e.clientX - rect.left) * (canvas.width / rect.width);
    const mouseY = (e.clientY - rect.top) * (canvas.height / rect.height);

    panOffsetX = mouseX - (mouseX - panOffsetX) * (newZoom / zoomLevel);
    panOffsetY = mouseY - (mouseY - panOffsetY) * (newZoom / zoomLevel);
    zoomLevel = newZoom;
  }, { passive: false });

  // Interactive Drag-to-Pan & Table Selection Listeners
  canvas.addEventListener('mousedown', (e) => {
    if (e.button === 0 && !hoveredTable) {
      isDragging = true;
      dragStartX = e.clientX - panOffsetX;
      dragStartY = e.clientY - panOffsetY;
      canvas.style.cursor = 'grabbing';
    }
  });

  canvas.addEventListener('mousemove', (e) => {
    if (isDragging) {
      panOffsetX = e.clientX - dragStartX;
      panOffsetY = e.clientY - dragStartY;
      return;
    }

    const rect = canvas.getBoundingClientRect();
    const mx = (e.clientX - rect.left) * (canvas.width / rect.width);
    const my = (e.clientY - rect.top) * (canvas.height / rect.height);
    const worldPos = canvasToWorld(mx, my);

    hoveredTable = null;
    if (restaurantLayout.tables) {
      for (const t of restaurantLayout.tables) {
        const dx = worldPos.x - t.x;
        const dy = worldPos.y - t.y;
        const dist = Math.hypot(dx, dy);
        if (dist < 1.3) {
          hoveredTable = t;
          break;
        }
      }
    }
    canvas.style.cursor = hoveredTable ? 'pointer' : (isDragging ? 'grabbing' : 'crosshair');
  });

  canvas.addEventListener('mouseup', () => {
    if (isDragging) {
      isDragging = false;
      canvas.style.cursor = hoveredTable ? 'pointer' : 'crosshair';
    }
  });

  canvas.addEventListener('mouseleave', () => {
    isDragging = false;
  });

  canvas.addEventListener('click', (e) => {
    if (hoveredTable) {
      const formattedName = formatTableName(hoveredTable.model);
      const targetSelect = document.getElementById('target-select');
      
      let found = false;
      for (let opt of targetSelect.options) {
        if (opt.value === formattedName || opt.text.includes(formattedName)) {
          targetSelect.value = opt.value;
          found = true;
          break;
        }
      }
      if (!found) {
        const newOpt = document.createElement('option');
        newOpt.value = formattedName;
        newOpt.text = `${formattedName} (Selected on Map)`;
        targetSelect.appendChild(newOpt);
        targetSelect.value = formattedName;
      }
      logSystem(`📍 Selected ${formattedName} from map click. Ready to dispatch.`, 'info');
    }
  });

  function formatTableName(rawName) {
    if (rawName === "table") return "Table 0";
    return rawName.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase());
  }

  // Render 2D Indoor Gazebo Restaurant Map
  function renderMap() {
    // 0. Auto-Follow Camera Lerp Tracking
    if (isFollowingRobot && telemetryData && telemetryData.robot_pose) {
      const rawRobot = worldToCanvasRaw(telemetryData.robot_pose.x, telemetryData.robot_pose.y);
      const targetPanX = (canvas.width / 2) - (rawRobot.x * zoomLevel);
      const targetPanY = (canvas.height / 2) - (rawRobot.y * zoomLevel);
      panOffsetX += (targetPanX - panOffsetX) * 0.12;
      panOffsetY += (targetPanY - panOffsetY) * 0.12;
    }

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // 1. Sleek Background Floor Grid
    ctx.fillStyle = '#0a0e17';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Grid lines (every 2 meters)
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.03)';
    ctx.lineWidth = 1;
    for (let gx = Math.ceil(WORLD_MIN_X); gx <= WORLD_MAX_X; gx += 2) {
      const p1 = worldToCanvas(gx, WORLD_MIN_Y);
      const p2 = worldToCanvas(gx, WORLD_MAX_Y);
      ctx.beginPath();
      ctx.moveTo(p1.x, p1.y);
      ctx.lineTo(p2.x, p2.y);
      ctx.stroke();
    }
    for (let gy = Math.ceil(WORLD_MIN_Y); gy <= WORLD_MAX_Y; gy += 2) {
      const p1 = worldToCanvas(WORLD_MIN_X, gy);
      const p2 = worldToCanvas(WORLD_MAX_X, gy);
      ctx.beginPath();
      ctx.moveTo(p1.x, p1.y);
      ctx.lineTo(p2.x, p2.y);
      ctx.stroke();
    }

    // 2. Zone Floor Background Markings
    const zoneMain = worldToCanvas(-9.0, 1.0);
    ctx.fillStyle = 'rgba(255, 255, 255, 0.02)';
    ctx.font = `${Math.round(13 * Math.min(1.5, Math.max(0.8, zoomLevel)))}px Inter`;
    ctx.fillText("DINING TERRACE (NORTH)", zoneMain.x - 40, zoneMain.y);

    const zoneSouth = worldToCanvas(-10.5, -15.0);
    ctx.fillText("PATIO DINING (SOUTH WING)", zoneSouth.x - 50, zoneSouth.y);

    const zoneEast = worldToCanvas(1.5, -2.0);
    ctx.fillText("MAIN LOUNGE & SALON", zoneEast.x - 45, zoneEast.y);

    const zoneDock = worldToCanvas(-14.2, -6.5);
    ctx.fillStyle = 'rgba(16, 185, 129, 0.07)';
    ctx.fillText("WEST SERVICE & DOCK CORRIDOR", zoneDock.x - 30, zoneDock.y);

    // 3. Draw Interior & Exterior Walls
    if (restaurantLayout.walls && restaurantLayout.walls.length > 0) {
      restaurantLayout.walls.forEach(w => {
        ctx.save();
        const pt = worldToCanvas(w.x, w.y);
        ctx.translate(pt.x, pt.y);
        ctx.rotate(-w.yaw);

        const pw = (w.sx / (WORLD_MAX_X - WORLD_MIN_X)) * canvas.width * zoomLevel;
        const ph = (w.sy / (WORLD_MAX_Y - WORLD_MIN_Y)) * canvas.height * zoomLevel;

        ctx.fillStyle = '#263345';
        ctx.strokeStyle = '#475569';
        ctx.lineWidth = 1.5 * zoomLevel;
        ctx.fillRect(-pw / 2, -ph / 2, pw, ph);
        ctx.strokeRect(-pw / 2, -ph / 2, pw, ph);
        ctx.restore();
      });
    }

    // 4. Draw Dining Tables (Scaled 0.65 for spacious aisles & wide navigation corridors)
    if (restaurantLayout.tables && restaurantLayout.tables.length > 0) {
      restaurantLayout.tables.forEach(t => {
        ctx.save();
        const pt = worldToCanvas(t.x, t.y);
        ctx.translate(pt.x, pt.y);
        ctx.rotate(-t.yaw);

        // Render table slightly sleek (0.65 scale) for wide, spacious distant table appearance
        const pw = (t.sx / (WORLD_MAX_X - WORLD_MIN_X)) * canvas.width * zoomLevel * 0.65;
        const ph = (t.sy / (WORLD_MAX_Y - WORLD_MIN_Y)) * canvas.height * zoomLevel * 0.65;

        const isHovered = (hoveredTable && hoveredTable.model === t.model);
        const isCurrentTarget = telemetryData && telemetryData.current_task &&
          (telemetryData.current_task.target.toLowerCase() === formatTableName(t.model).toLowerCase());

        // Table Shadow / Ambient Glow
        if (isCurrentTarget) {
          ctx.shadowColor = '#06b6d4';
          ctx.shadowBlur = 12 * zoomLevel;
        } else if (isHovered) {
          ctx.shadowColor = '#f59e0b';
          ctx.shadowBlur = 8 * zoomLevel;
        }

        // Table Surface
        ctx.beginPath();
        const radius = Math.max(2, 4 * zoomLevel);
        ctx.roundRect(-pw / 2, -ph / 2, pw, ph, radius);
        ctx.fillStyle = isCurrentTarget ? 'rgba(6, 182, 212, 0.40)' : (isHovered ? 'rgba(245, 158, 11, 0.40)' : 'rgba(245, 158, 11, 0.16)');
        ctx.fill();
        ctx.strokeStyle = isCurrentTarget ? '#06b6d4' : (isHovered ? '#fbbf24' : '#d97706');
        ctx.lineWidth = (isCurrentTarget || isHovered ? 2 : 1.2) * Math.max(0.7, zoomLevel);
        ctx.stroke();

        // Subtle Dining Chairs (top & bottom dots)
        ctx.fillStyle = '#64748b';
        ctx.fillRect(-pw * 0.3, -ph / 2 - 3 * zoomLevel, pw * 0.6, 2 * zoomLevel);
        ctx.fillRect(-pw * 0.3, ph / 2 + 1 * zoomLevel, pw * 0.6, 2 * zoomLevel);

        ctx.restore();

        // Table Label
        if (zoomLevel > 0.6) {
          ctx.fillStyle = isCurrentTarget ? '#22d3ee' : '#f59e0b';
          ctx.font = `bold ${Math.round(9 * Math.min(1.4, Math.max(0.8, zoomLevel)))}px Inter`;
          ctx.textAlign = 'center';
          const label = t.model.replace('table_', 'T').replace('table', 'T0');
          ctx.fillText(label, pt.x, pt.y + 3 * zoomLevel);
          ctx.textAlign = 'start';
        }
      });
    }

    // 5. Draw Key Service Waypoints (Dock Station & Kitchen Pickup)
    if (telemetryData && telemetryData.waypoints) {
      Object.entries(telemetryData.waypoints).forEach(([name, wp]) => {
        const pt = worldToCanvas(wp.x, wp.y);

        if (name === "Dock") {
          // Charging Dock Station
          const size = 36 * zoomLevel;
          ctx.fillStyle = 'rgba(16, 185, 129, 0.2)';
          ctx.strokeStyle = '#10b981';
          ctx.lineWidth = 2 * zoomLevel;
          ctx.fillRect(pt.x - size / 2, pt.y - size / 2, size, size);
          ctx.strokeRect(pt.x - size / 2, pt.y - size / 2, size, size);

          ctx.fillStyle = '#10b981';
          ctx.font = `bold ${Math.round(11 * Math.min(1.4, zoomLevel))}px Inter`;
          ctx.fillText("⚡ DOCK", pt.x - size / 2, pt.y - size / 2 - 4);
        } else if (name.includes("Kitchen")) {
          // Kitchen Order Pickup Counter
          const size = 40 * zoomLevel;
          ctx.fillStyle = 'rgba(59, 130, 246, 0.25)';
          ctx.strokeStyle = '#3b82f6';
          ctx.lineWidth = 2 * zoomLevel;
          ctx.fillRect(pt.x - size / 2, pt.y - size / 2, size, size);
          ctx.strokeRect(pt.x - size / 2, pt.y - size / 2, size, size);

          ctx.fillStyle = '#3b82f6';
          ctx.font = `bold ${Math.round(11 * Math.min(1.4, zoomLevel))}px Inter`;
          ctx.fillText("🍳 KITCHEN", pt.x - size / 2, pt.y - size / 2 - 4);
        }
      });
    }

    // 6. Draw Planned A* Navigation Route (Glowing Cyan Dashed Line)
    if (telemetryData && telemetryData.planned_path && telemetryData.planned_path.length > 0) {
      ctx.beginPath();
      const startPt = worldToCanvas(telemetryData.robot_pose.x, telemetryData.robot_pose.y);
      ctx.moveTo(startPt.x, startPt.y);

      telemetryData.planned_path.forEach(wp => {
        const p = worldToCanvas(wp.x, wp.y);
        ctx.lineTo(p.x, p.y);
      });

      ctx.strokeStyle = 'rgba(6, 182, 212, 0.85)';
      ctx.lineWidth = 2.5 * zoomLevel;
      ctx.setLineDash([6 * zoomLevel, 6 * zoomLevel]);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // 7. Draw Dynamic Pedestrian Obstacle with Safety Halo
    if (telemetryData && telemetryData.dynamic_obstacle && telemetryData.dynamic_obstacle.active) {
      const obsPt = worldToCanvas(telemetryData.dynamic_obstacle.pose.x, telemetryData.dynamic_obstacle.pose.y);

      // Avoidance Safety Margin Zone (1.3m radius)
      const safetyRadius = (1.3 / (WORLD_MAX_X - WORLD_MIN_X)) * canvas.width * zoomLevel;
      ctx.beginPath();
      ctx.arc(obsPt.x, obsPt.y, safetyRadius, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(239, 68, 68, 0.12)';
      ctx.fill();
      ctx.strokeStyle = 'rgba(239, 68, 68, 0.45)';
      ctx.lineWidth = 1.5 * zoomLevel;
      ctx.setLineDash([4 * zoomLevel, 4 * zoomLevel]);
      ctx.stroke();
      ctx.setLineDash([]);

      // Pedestrian Body
      ctx.beginPath();
      const bodyR = Math.max(6, 11 * zoomLevel);
      ctx.arc(obsPt.x, obsPt.y, bodyR, 0, Math.PI * 2);
      ctx.fillStyle = '#ef4444';
      ctx.fill();
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 2 * zoomLevel;
      ctx.stroke();

      ctx.fillStyle = '#ef4444';
      ctx.font = `bold ${Math.round(10 * Math.min(1.4, zoomLevel))}px Inter`;
      ctx.fillText("🚶 Human Obstacle", obsPt.x - 38 * zoomLevel, obsPt.y - 16 * zoomLevel);
    }

    // 8. Draw BellaBot Service Robot (Accurate Orientation, Cat Ears, Halo, Trays)
    if (telemetryData && telemetryData.robot_pose) {
      const rPt = worldToCanvas(telemetryData.robot_pose.x, telemetryData.robot_pose.y);
      const isAvoiding = telemetryData.avoidance_active ||
        telemetryData.robot_state === "avoiding_obstacle" ||
        telemetryData.robot_state === "yielding";

      // Charging Pulse Halo when in dock
      if (telemetryData.charging_active || telemetryData.robot_state === "charging") {
        ctx.beginPath();
        const pulse = (Math.sin(Date.now() / 250) + 1) * 3;
        ctx.arc(rPt.x, rPt.y, (24 + pulse) * zoomLevel, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(16, 185, 129, 0.22)';
        ctx.fill();
        ctx.strokeStyle = '#10b981';
        ctx.lineWidth = 2 * zoomLevel;
        ctx.stroke();
      }

      // Collision Evasive Ring
      if (isAvoiding) {
        ctx.beginPath();
        ctx.arc(rPt.x, rPt.y, 28 * zoomLevel, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(239, 68, 68, 0.2)';
        ctx.fill();
        ctx.strokeStyle = '#ef4444';
        ctx.lineWidth = 2 * zoomLevel;
        ctx.stroke();
      }

      ctx.save();
      ctx.translate(rPt.x, rPt.y);
      ctx.rotate(-telemetryData.robot_pose.yaw);
      ctx.scale(zoomLevel, zoomLevel);

      // BellaBot Rounded Base Chassis
      ctx.beginPath();
      ctx.ellipse(0, 0, 16, 14, 0, 0, Math.PI * 2);
      ctx.fillStyle = '#0f172a';
      ctx.fill();
      ctx.strokeStyle = isAvoiding ? '#ef4444' : '#06b6d4';
      ctx.lineWidth = 2.5;
      ctx.stroke();

      // BellaBot 3-Tier Shelf Indicators
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.5)';
      ctx.lineWidth = 1.2;
      ctx.strokeRect(-7, -8, 11, 4);
      ctx.strokeRect(-7, -2, 11, 4);
      ctx.strokeRect(-7, 4, 11, 4);

      // BellaBot Signature Cat Ears on Head (Facing Forward +X)
      ctx.fillStyle = isAvoiding ? '#ef4444' : '#06b6d4';
      // Left Ear
      ctx.beginPath();
      ctx.moveTo(10, -8);
      ctx.lineTo(16, -11);
      ctx.lineTo(13, -5);
      ctx.closePath();
      ctx.fill();
      // Right Ear
      ctx.beginPath();
      ctx.moveTo(10, 8);
      ctx.lineTo(16, 11);
      ctx.lineTo(13, 5);
      ctx.closePath();
      ctx.fill();

      // BellaBot Front Touchscreen Display Face
      ctx.fillStyle = '#1e293b';
      ctx.strokeStyle = '#38bdf8';
      ctx.lineWidth = 1.5;
      ctx.fillRect(8, -6, 4, 12);
      ctx.strokeRect(8, -6, 4, 12);

      // Forward Heading Glow Indicator
      ctx.beginPath();
      ctx.moveTo(13, 0);
      ctx.lineTo(22, 0);
      ctx.strokeStyle = '#38bdf8';
      ctx.lineWidth = 3;
      ctx.stroke();

      ctx.restore();

      // Robot Label Badge
      ctx.fillStyle = '#ffffff';
      ctx.font = `bold ${Math.round(10 * Math.min(1.4, zoomLevel))}px Inter`;
      const labelText = isAvoiding ? "⚠️ AVOIDING" : "🐱 BELLABOT";
      ctx.fillText(labelText, rPt.x - 28 * zoomLevel, rPt.y + 24 * zoomLevel);
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
      logSystem("WebSocket live telemetry connected to BellaBot.", 'info');
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
    const isCharging = data.charging_active || data.robot_state === "charging";

    if (isCharging) {
      document.getElementById('battery-pct-text').innerHTML = `⚡ ${batPct.toFixed(1)}% <span style="font-size:10px;color:#10b981;font-weight:600;">(Charging)</span>`;
      document.getElementById('battery-fill').style.background = '#10b981';
      document.getElementById('battery-fill').style.boxShadow = '0 0 10px rgba(16, 185, 129, 0.8)';
    } else {
      document.getElementById('battery-pct-text').textContent = `${batPct.toFixed(1)}%`;
      document.getElementById('battery-fill').style.boxShadow = 'none';
      if (batPct < 20) {
        document.getElementById('battery-fill').style.background = '#ef4444';
      } else if (batPct < 50) {
        document.getElementById('battery-fill').style.background = '#f59e0b';
      } else {
        document.getElementById('battery-fill').style.background = '#10b981';
      }
    }

    document.getElementById('battery-fill').style.width = `${batPct}%`;
    document.getElementById('battery-voltage-text').textContent = `${data.voltage.toFixed(2)} V`;
    document.getElementById('battery-current-text').textContent = `${(data.current_amps || 0).toFixed(2)} A${isCharging ? ' (Charging)' : ''}`;
    document.getElementById('battery-power-text').textContent = `${(data.power_watts || 0).toFixed(1)} W`;
    document.getElementById('battery-temp-text').textContent = `${(data.temperature_c || 24.5).toFixed(1)} °C`;

    // 2. Robot State & Avoidance Badge
    let stateText = (data.robot_state || "IDLE").toUpperCase();
    if (isCharging) {
      stateText = "⚡ CHARGING (DOCKED)";
    }
    document.getElementById('robot-state-text').textContent = stateText;
    const dot = document.querySelector('#robot-state-badge .dot');
    dot.className = isCharging ? 'dot charging' : `dot ${data.robot_state || 'idle'}`;

    // Sync Auto-Charge toggle switch if not actively focused
    const autoChargeToggle = document.getElementById('auto-charge-toggle');
    if (autoChargeToggle && data.auto_charge_at_dock !== undefined && document.activeElement !== autoChargeToggle) {
      autoChargeToggle.checked = Boolean(data.auto_charge_at_dock);
    }

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
      document.getElementById('current-task-text').textContent = 'None (Stationary / Idle)';
    }

    // 5. BellaBot 3-Tier Shelves Status
    if (data.shelves) {
      const s3 = data.shelves.shelf_3;
      const s2 = data.shelves.shelf_2;
      const s1 = data.shelves.shelf_1;

      document.getElementById('shelf-3-item').textContent = s3.item ? `Loaded: ${s3.item}` : 'Empty / Available';
      document.getElementById('shelf-2-item').textContent = s2.item ? `Loaded: ${s2.item}` : 'Empty / Available';
      document.getElementById('shelf-1-item').textContent = s1.item ? `Loaded: ${s1.item}` : 'Empty / Available';
    }

    // 6. Queue List UI
    const queueList = document.getElementById('queue-list');
    if (!data.queue || data.queue.length === 0) {
      queueList.innerHTML = '<div class="empty-state">No pending deliveries in queue.</div>';
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
        logSystem(`Delivery dispatched: ${data.task.id} to ${target} (${item})`, 'info');
        document.getElementById('item-input').value = '';
      } else {
        logSystem(`Error: ${data.detail}`, 'warn');
      }
    } catch (err) {
      logSystem(`Network error submitting delivery`, 'warn');
    }
  });

  // Auto-Charge at Dock Switch Listener
  const autoChargeToggleEl = document.getElementById('auto-charge-toggle');
  if (autoChargeToggleEl) {
    autoChargeToggleEl.addEventListener('change', async (e) => {
      try {
        const res = await fetch('/api/dock/charge_option', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ auto_charge: e.target.checked })
        });
        const data = await res.json();
        logSystem(`Auto-Charge at Dock option: ${data.auto_charge_at_dock ? 'ENABLED (robot automatically charges when in dock)' : 'DISABLED'}`, 'info');
      } catch (err) {
        logSystem("Failed to update auto-charge setting.", 'warn');
      }
    });
  }

  // Start Charging at Dock Button Listener
  const startChargeBtn = document.getElementById('start-charge-btn');
  if (startChargeBtn) {
    startChargeBtn.addEventListener('click', async () => {
      try {
        const res = await fetch('/api/dock/start_charge', { method: 'POST' });
        const data = await res.json();
        logSystem(data.message, 'info');
      } catch (err) {
        logSystem("Failed to command charging at dock.", 'warn');
      }
    });
  }

  // Admin Manual Dock Button
  document.getElementById('manual-dock-btn').addEventListener('click', async () => {
    try {
      await fetch('/api/dock', { method: 'POST' });
      logSystem("Admin commanded BellaBot to return to Dock station.", 'info');
    } catch (err) {
      logSystem("Failed to send dock command.", 'warn');
    }
  });

  // Low Battery Trigger Button
  const lowBatBtn = document.getElementById('low-battery-btn');
  if (lowBatBtn) {
    lowBatBtn.addEventListener('click', async () => {
      try {
        const res = await fetch('/api/battery/low', { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
          logSystem("🪫 Low battery (15%) triggered! Auto-docking preemption initiated.", 'warn');
        }
      } catch (err) {
        logSystem("Failed to trigger low battery state.", 'warn');
      }
    });
  }

  // Toggle Dynamic Obstacle Button
  document.getElementById('toggle-obstacle-btn').addEventListener('click', async () => {
    dynamicObstacleActive = !dynamicObstacleActive;
    try {
      await fetch('/api/obstacle/trigger', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active: dynamicObstacleActive })
      });
      logSystem(`Dynamic pedestrian obstacle: ${dynamicObstacleActive ? 'ACTIVATED (2D Random Roaming)' : 'DEACTIVATED'}`, 'info');
    } catch (err) {
      logSystem("Failed to toggle dynamic obstacle.", 'warn');
    }
  });

  // Clear Queue Button
  document.getElementById('clear-queue-btn').addEventListener('click', async () => {
    try {
      await fetch('/api/queue', { method: 'DELETE' });
      logSystem("Task queue and trays cleared by admin.", 'info');
    } catch (err) {
      logSystem("Failed to clear task queue.", 'warn');
    }
  });

  // Map Controls Buttons: Zoom In, Zoom Out, Reset, Toggle Follow
  const zoomInBtn = document.getElementById('zoom-in-btn');
  if (zoomInBtn) {
    zoomInBtn.addEventListener('click', () => {
      zoomLevel = Math.min(4.5, zoomLevel * 1.25);
      logSystem(`Map Zoom: ${Math.round(zoomLevel * 100)}%`, 'info');
    });
  }

  const zoomOutBtn = document.getElementById('zoom-out-btn');
  if (zoomOutBtn) {
    zoomOutBtn.addEventListener('click', () => {
      zoomLevel = Math.max(0.5, zoomLevel * 0.8);
      logSystem(`Map Zoom: ${Math.round(zoomLevel * 100)}%`, 'info');
    });
  }

  const resetBtn = document.getElementById('reset-view-btn');
  if (resetBtn) {
    resetBtn.addEventListener('click', () => {
      zoomLevel = 1.0;
      panOffsetX = 0.0;
      panOffsetY = 0.0;
      isFollowingRobot = true;
      const followBtn = document.getElementById('toggle-follow-btn');
      if (followBtn) {
        followBtn.textContent = '🎥 Follow Cam: ON';
        followBtn.className = 'btn btn-sm btn-primary';
      }
      adjustCanvasSize();
      logSystem("Map view reset to default 100%.", 'info');
    });
  }

  const toggleFollowBtn = document.getElementById('toggle-follow-btn');
  if (toggleFollowBtn) {
    toggleFollowBtn.addEventListener('click', () => {
      isFollowingRobot = !isFollowingRobot;
      toggleFollowBtn.textContent = isFollowingRobot ? '🎥 Follow Cam: ON' : '🎥 Follow Cam: OFF';
      toggleFollowBtn.className = isFollowingRobot ? 'btn btn-sm btn-primary' : 'btn btn-sm btn-outline';
      logSystem(`Auto-Follow Camera: ${isFollowingRobot ? 'ENABLED' : 'DISABLED'}`, 'info');
    });
  }

  function logSystem(msg, type = 'system') {
    const logBox = document.getElementById('sys-log');
    const entry = document.createElement('div');
    entry.className = `log-entry ${type}`;
    const timeStr = new Date().toLocaleTimeString();
    entry.textContent = `[${timeStr}] ${msg}`;
    logBox.appendChild(entry);
    logBox.scrollTop = logBox.scrollHeight;
  }

  // Start Animation Loop & Connect WebSocket
  renderMap();
  connectWebSocket();
});

