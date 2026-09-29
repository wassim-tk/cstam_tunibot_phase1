/**
 * CSTAM Restaurant Floor Operations — BellaBot #1 Web Controller
 * Human-crafted UI/UX: Tactile controls, Web Audio chimes, rich 2D floorplan artistry,
 * realistic dining ambiance, and intuitive fleet management.
 */

document.addEventListener('DOMContentLoaded', () => {
  const canvas = document.getElementById('map-canvas');
  const ctx = canvas.getContext('2d');

  // Floor Coordinates (Gazebo restaurant.world: 26m width x 20m height)
  const WORLD_MIN_X = -17.0;
  const WORLD_MAX_X = 9.0;    // 26m width (25 px/m @ 650px)
  const WORLD_MIN_Y = -14.5;
  const WORLD_MAX_Y = 5.5;    // 20m height (25 px/m @ 500px)

  let telemetryData = null;
  let ws = null;
  let dynamicObstacleActive = false;
  let restaurantLayout = { walls: [], tables: [] };
  let hoveredTable = null;
  let selectedTable = null;

  // Viewport Pan, Zoom & Camera Tracking
  let zoomLevel = 1.0;
  let panOffsetX = 0.0;
  let panOffsetY = 0.0;
  let isFollowingRobot = true;
  let isDragging = false;
  let dragStartX = 0;
  let dragStartY = 0;

  // Robot Motion History Trail
  const robotTrail = [];
  const MAX_TRAIL_LENGTH = 32;

  // Blinking eyes animation timer
  let lastBlinkTime = Date.now();
  let isBlinking = false;

  // Previous task state to detect arrivals
  let prevTaskId = null;
  let prevRobotState = null;

  // Audio Chimes System (Web Audio API)
  let soundEnabled = localStorage.getItem('bellabot_sound') !== 'false';
  let audioCtx = null;

  function initAudio() {
    if (!audioCtx) {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (AudioContext) audioCtx = new AudioContext();
    }
    if (audioCtx && audioCtx.state === 'suspended') {
      audioCtx.resume();
    }
  }

  function playChime(type) {
    if (!soundEnabled) return;
    try {
      initAudio();
      if (!audioCtx) return;

      const now = audioCtx.currentTime;

      if (type === 'order') {
        // Ascending pleasant hospitality two-tone chime
        const osc1 = audioCtx.createOscillator();
        const osc2 = audioCtx.createOscillator();
        const gain = audioCtx.createGain();

        osc1.type = 'sine';
        osc2.type = 'sine';
        osc1.frequency.setValueAtTime(523.25, now); // C5
        osc2.frequency.setValueAtTime(659.25, now + 0.12); // E5

        gain.gain.setValueAtTime(0.12, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.45);

        osc1.connect(gain);
        osc2.connect(gain);
        gain.connect(audioCtx.destination);

        osc1.start(now);
        osc1.stop(now + 0.12);
        osc2.start(now + 0.12);
        osc2.stop(now + 0.45);
      } else if (type === 'arrive') {
        // Bright metallic hotel bell ding
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();

        osc.type = 'sine';
        osc.frequency.setValueAtTime(1046.5, now); // C6
        gain.gain.setValueAtTime(0.18, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.9);

        osc.connect(gain);
        gain.connect(audioCtx.destination);

        osc.start(now);
        osc.stop(now + 0.9);
      } else if (type === 'yield') {
        // Gentle caution tone
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();

        osc.type = 'triangle';
        osc.frequency.setValueAtTime(349.23, now); // F4
        gain.gain.setValueAtTime(0.15, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);

        osc.connect(gain);
        gain.connect(audioCtx.destination);

        osc.start(now);
        osc.stop(now + 0.35);
      } else if (type === 'tap') {
        // Subtle micro UI click
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();

        osc.type = 'sine';
        osc.frequency.setValueAtTime(780, now);
        gain.gain.setValueAtTime(0.04, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.06);

        osc.connect(gain);
        gain.connect(audioCtx.destination);

        osc.start(now);
        osc.stop(now + 0.06);
      }
    } catch (e) {
      console.warn("Audio chime prevented:", e);
    }
  }

  // Audio Toggle Button Setup
  const soundToggleBtn = document.getElementById('sound-toggle-btn');
  const soundIcon = document.getElementById('sound-icon');
  const soundText = document.getElementById('sound-text');

  function updateSoundUI() {
    if (soundIcon && soundText) {
      soundIcon.textContent = soundEnabled ? '🔔' : '🔕';
      soundText.textContent = soundEnabled ? 'Chimes: ON' : 'Chimes: OFF';
    }
  }
  updateSoundUI();

  if (soundToggleBtn) {
    soundToggleBtn.addEventListener('click', () => {
      soundEnabled = !soundEnabled;
      localStorage.setItem('bellabot_sound', soundEnabled ? 'true' : 'false');
      updateSoundUI();
      if (soundEnabled) playChime('tap');
    });
  }

  // Floating Toast Notification System
  function showToast(message, icon = '🛎️') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.innerHTML = `<span style="font-size:16px;">${icon}</span><span>${message}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
      toast.classList.add('toast-fadeout');
      setTimeout(() => toast.remove(), 320);
    }, 3600);
  }

  // Set crisp canvas dimensions
  function adjustCanvasSize() {
    canvas.width = 650;
    canvas.height = 500;
  }
  adjustCanvasSize();

  // World (x, y) to Unscaled Canvas Pixel
  function worldToCanvasRaw(x, y) {
    const px = ((x - WORLD_MIN_X) / (WORLD_MAX_X - WORLD_MIN_X)) * canvas.width;
    const py = ((WORLD_MAX_Y - y) / (WORLD_MAX_Y - WORLD_MIN_Y)) * canvas.height;
    return { x: px, y: py };
  }

  // World (x, y) to Viewport Canvas Pixel with Pan & Zoom
  function worldToCanvas(x, y) {
    const raw = worldToCanvasRaw(x, y);
    const cx = canvas.width / 2;
    const cy = canvas.height / 2;
    const px = cx + (raw.x - cx) * zoomLevel + panOffsetX;
    const py = cy + (raw.y - cy) * zoomLevel + panOffsetY;
    return { x: px, y: py };
  }

  // Viewport Canvas Pixel to World (x, y)
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

  // Mouse Wheel Zooming (centered on cursor)
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

  // Mouse Drag-to-Pan & Hover Detection
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
        if (dist < 1.35) {
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
    hoveredTable = null;
  });

  // Table Selection via Map Click
  canvas.addEventListener('click', () => {
    if (hoveredTable) {
      selectedTable = hoveredTable;
      playChime('tap');
      const formattedName = formatTableName(hoveredTable.model);
      const targetSelect = document.getElementById('target-select');

      let found = false;
      for (let opt of targetSelect.options) {
        if (opt.value === formattedName || opt.text.startsWith(formattedName)) {
          targetSelect.value = opt.value;
          found = true;
          break;
        }
      }
      if (!found) {
        const newOpt = document.createElement('option');
        newOpt.value = formattedName;
        newOpt.text = `${formattedName} (Selected on Floor)`;
        targetSelect.appendChild(newOpt);
        targetSelect.value = formattedName;
      }
      logSystem(`Selected ${formattedName} directly from floorplan. Ready to dispatch.`, 'info');
      showToast(`Selected ${formattedName} on floorplan`, '📍');

      const itemInput = document.getElementById('item-input');
      if (itemInput) itemInput.focus();
    }
  });

  function formatTableName(rawName) {
    if (!rawName) return "Table 0";
    if (rawName === "table") return "Table 0";
    if (rawName.startsWith("table_")) {
      return `Table ${rawName.split('_')[1]}`;
    }
    return rawName.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase());
  }

  function getTableZone(model) {
    const num = parseInt(model.replace('table_', '').replace('table', '0'), 10) || 0;
    if (num <= 5) return "North Terrace";
    if (num <= 11) return "Mid Lounge";
    if (num <= 17) return "Dining Salon";
    return "South Wing";
  }

  // Render 2D Dining Floor Map (Artistic Human Hospitality Styling)
  function renderMap() {
    // 0. Auto-Follow Camera Lerp
    if (isFollowingRobot && telemetryData && telemetryData.robot_pose) {
      const rawRobot = worldToCanvasRaw(telemetryData.robot_pose.x, telemetryData.robot_pose.y);
      const targetPanX = (canvas.width / 2) - (rawRobot.x * zoomLevel);
      const targetPanY = (canvas.height / 2) - (rawRobot.y * zoomLevel);
      panOffsetX += (targetPanX - panOffsetX) * 0.12;
      panOffsetY += (targetPanY - panOffsetY) * 0.12;
    }

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // 1. Warm Parquetry Bistro / Slate Floor
    const centerFloor = worldToCanvas(-1.8, -4.5);
    const floorGrad = ctx.createRadialGradient(
      centerFloor.x, centerFloor.y, 80 * zoomLevel,
      centerFloor.x, centerFloor.y, 480 * zoomLevel
    );
    floorGrad.addColorStop(0, '#151b27');
    floorGrad.addColorStop(0.65, '#0e121c');
    floorGrad.addColorStop(1, '#080a10');
    ctx.fillStyle = floorGrad;
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Subtle 2m architectural floor tiles (champagne-tinted seams)
    ctx.strokeStyle = 'rgba(212, 160, 75, 0.035)';
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

    // 2. Warm Ambient Ceiling Pendant Light Pools (Cozy dining glow)
    if (restaurantLayout.tables && restaurantLayout.tables.length > 0) {
      restaurantLayout.tables.forEach(t => {
        const pt = worldToCanvas(t.x, t.y);
        const lightGrad = ctx.createRadialGradient(pt.x, pt.y, 8 * zoomLevel, pt.x, pt.y, 42 * zoomLevel);
        lightGrad.addColorStop(0, 'rgba(251, 191, 36, 0.06)');
        lightGrad.addColorStop(1, 'rgba(251, 191, 36, 0.0)');
        ctx.fillStyle = lightGrad;
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, 42 * zoomLevel, 0, Math.PI * 2);
        ctx.fill();
      });
    }

    // 3. Zone Floor Typography
    const zoneKitchen = worldToCanvas(-13.5, 1.5);
    ctx.fillStyle = 'rgba(56, 189, 248, 0.12)';
    ctx.font = `700 ${Math.round(11 * Math.min(1.4, Math.max(0.8, zoomLevel)))}px 'Plus Jakarta Sans', sans-serif`;
    ctx.fillText("CHEF EXPEDITE & KITCHEN PASS", zoneKitchen.x - 70, zoneKitchen.y);

    const zoneMain = worldToCanvas(-1.8, -4.5);
    ctx.fillStyle = 'rgba(255, 255, 255, 0.04)';
    ctx.font = `800 ${Math.round(13 * Math.min(1.4, Math.max(0.8, zoomLevel)))}px 'Plus Jakarta Sans', sans-serif`;
    ctx.fillText("MAIN DINING ROOM", zoneMain.x - 56, zoneMain.y - 12);
    ctx.font = `600 ${Math.round(10 * Math.min(1.4, Math.max(0.8, zoomLevel)))}px 'Plus Jakarta Sans', sans-serif`;
    ctx.fillStyle = 'rgba(212, 160, 75, 0.09)';
    ctx.fillText("24 SERVICE TABLES · 4 SECTIONS", zoneMain.x - 66, zoneMain.y + 4);

    const zoneHost = worldToCanvas(6.8, 0.0);
    ctx.fillStyle = 'rgba(255, 255, 255, 0.035)';
    ctx.font = `600 ${Math.round(11 * Math.min(1.4, Math.max(0.8, zoomLevel)))}px 'Plus Jakarta Sans', sans-serif`;
    ctx.fillText("HOST FOYER & RECEPTION", zoneHost.x - 55, zoneHost.y);

    const zoneDock = worldToCanvas(6.0, -11.5);
    ctx.fillStyle = 'rgba(16, 185, 129, 0.12)';
    ctx.fillText("CHARGING BAY (STATION A)", zoneDock.x - 60, zoneDock.y);

    // 4. Architectural Walls & Partitions (Blueprint outline & soft drop shadow)
    if (restaurantLayout.walls && restaurantLayout.walls.length > 0) {
      restaurantLayout.walls.forEach(w => {
        ctx.save();
        const pt = worldToCanvas(w.x, w.y);
        ctx.translate(pt.x, pt.y);
        ctx.rotate(-w.yaw);

        const pw = (w.sx / (WORLD_MAX_X - WORLD_MIN_X)) * canvas.width * zoomLevel;
        const ph = (w.sy / (WORLD_MAX_Y - WORLD_MIN_Y)) * canvas.height * zoomLevel;

        ctx.shadowColor = 'rgba(0, 0, 0, 0.55)';
        ctx.shadowBlur = 8 * zoomLevel;
        ctx.fillStyle = '#182030';
        ctx.fillRect(-pw / 2, -ph / 2, pw, ph);

        ctx.shadowBlur = 0;
        ctx.strokeStyle = '#2d3b52';
        ctx.lineWidth = Math.max(1, 1.2 * zoomLevel);
        ctx.strokeRect(-pw / 2, -ph / 2, pw, ph);

        ctx.restore();
      });
    }

    // 5. Dining Tables (Handcrafted Walnut Tops, Center Linen, Brass Rim & Curved Chairs)
    if (restaurantLayout.tables && restaurantLayout.tables.length > 0) {
      restaurantLayout.tables.forEach(t => {
        ctx.save();
        const pt = worldToCanvas(t.x, t.y);
        ctx.translate(pt.x, pt.y);
        ctx.rotate(-t.yaw);

        const pw = (t.sx / (WORLD_MAX_X - WORLD_MIN_X)) * canvas.width * zoomLevel * 0.88;
        const ph = (t.sy / (WORLD_MAX_Y - WORLD_MIN_Y)) * canvas.height * zoomLevel * 0.88;

        const isHovered = (hoveredTable && hoveredTable.model === t.model);
        const isSelected = (selectedTable && selectedTable.model === t.model);
        const isCurrentTarget = telemetryData && telemetryData.current_task &&
          (telemetryData.current_task.target.toLowerCase() === formatTableName(t.model).toLowerCase());

        // Ambient Table Glow
        if (isCurrentTarget) {
          ctx.shadowColor = '#06b6d4';
          ctx.shadowBlur = 18 * zoomLevel;
        } else if (isHovered || isSelected) {
          ctx.shadowColor = '#d4a04b';
          ctx.shadowBlur = 14 * zoomLevel;
        }

        // Dining Chairs (4 Curved Upholstered Chairs)
        ctx.fillStyle = isCurrentTarget ? '#0e7490' : (isHovered || isSelected ? '#78350f' : '#232b3b');
        // Top Chair
        ctx.beginPath();
        ctx.roundRect(-pw * 0.32, -ph / 2 - 4.5 * zoomLevel, pw * 0.64, 3.5 * zoomLevel, 2 * zoomLevel);
        ctx.fill();
        // Bottom Chair
        ctx.beginPath();
        ctx.roundRect(-pw * 0.32, ph / 2 + 1 * zoomLevel, pw * 0.64, 3.5 * zoomLevel, 2 * zoomLevel);
        ctx.fill();

        // Warm Walnut Wood Tabletop
        ctx.beginPath();
        const radius = Math.max(2, 5 * zoomLevel);
        ctx.roundRect(-pw / 2, -ph / 2, pw, ph, radius);

        const tableGrad = ctx.createLinearGradient(-pw / 2, -ph / 2, pw / 2, ph / 2);
        if (isCurrentTarget) {
          tableGrad.addColorStop(0, '#155e75');
          tableGrad.addColorStop(1, '#0e7490');
        } else if (isHovered || isSelected) {
          tableGrad.addColorStop(0, '#78350f');
          tableGrad.addColorStop(1, '#92400e');
        } else {
          tableGrad.addColorStop(0, '#261e17');
          tableGrad.addColorStop(1, '#342921');
        }
        ctx.fillStyle = tableGrad;
        ctx.fill();

        // Center Table Linen Runner
        ctx.fillStyle = isCurrentTarget ? 'rgba(34, 211, 238, 0.18)' : 'rgba(255, 255, 255, 0.05)';
        ctx.fillRect(-pw * 0.18, -ph / 2, pw * 0.36, ph);

        // Center Ambient Tea-light Candle
        ctx.beginPath();
        ctx.arc(0, 0, Math.max(1.5, 2.5 * zoomLevel), 0, Math.PI * 2);
        ctx.fillStyle = isCurrentTarget ? '#22d3ee' : '#fbbf24';
        ctx.fill();

        // Champagne Brass Rim Stroke
        ctx.strokeStyle = isCurrentTarget ? '#22d3ee' : (isHovered || isSelected ? '#fbbf24' : '#8c6b3e');
        ctx.lineWidth = (isCurrentTarget || isHovered || isSelected ? 2 : 1.2) * Math.max(0.7, zoomLevel);
        ctx.stroke();

        ctx.restore();

        // Table Label Badge
        if (zoomLevel > 0.6) {
          ctx.fillStyle = isCurrentTarget ? '#22d3ee' : (isHovered || isSelected ? '#fbbf24' : '#d4a04b');
          ctx.font = `700 ${Math.round(9 * Math.min(1.4, Math.max(0.8, zoomLevel)))}px 'Plus Jakarta Sans', sans-serif`;
          ctx.textAlign = 'center';
          const num = t.model.replace('table_', '');
          const formattedNum = num.length === 1 ? `0${num}` : num;
          ctx.fillText(`T${formattedNum}`, pt.x, pt.y + 3 * zoomLevel);
          ctx.textAlign = 'start';
        }
      });
    }

    // Floating Tooltip on Table Hover
    if (hoveredTable) {
      const hp = worldToCanvas(hoveredTable.x, hoveredTable.y);
      const tName = formatTableName(hoveredTable.model);
      const zoneName = getTableZone(hoveredTable.model);
      const tipText = `${tName} · ${zoneName} · Click to Order`;
      ctx.font = `600 11px 'Plus Jakarta Sans', sans-serif`;
      const textWidth = ctx.measureText(tipText).width;

      const tipX = hp.x - (textWidth + 20) / 2;
      const tipY = hp.y - 30 * zoomLevel;

      ctx.fillStyle = 'rgba(12, 17, 26, 0.95)';
      ctx.strokeStyle = '#d4a04b';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.roundRect(tipX, tipY, textWidth + 20, 24, 6);
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = '#fbbf24';
      ctx.fillText(tipText, tipX + 10, tipY + 16);
    }

    // 6. Service Stations: Charging Bay & Kitchen Pass with Radiant Glows
    if (telemetryData && telemetryData.waypoints) {
      Object.entries(telemetryData.waypoints).forEach(([name, wp]) => {
        const pt = worldToCanvas(wp.x, wp.y);

        if (name === "Dock") {
          const size = 38 * zoomLevel;
          // Emerald Charging Aura
          ctx.fillStyle = 'rgba(16, 185, 129, 0.16)';
          ctx.strokeStyle = '#10b981';
          ctx.lineWidth = 2 * zoomLevel;
          ctx.beginPath();
          ctx.roundRect(pt.x - size / 2, pt.y - size / 2, size, size, 8 * zoomLevel);
          ctx.fill();
          ctx.stroke();

          // Charging Plate Pins
          ctx.fillStyle = '#34d399';
          ctx.fillRect(pt.x - 6 * zoomLevel, pt.y - 3 * zoomLevel, 12 * zoomLevel, 6 * zoomLevel);

          ctx.font = `bold ${Math.round(10 * Math.min(1.4, zoomLevel))}px 'Plus Jakarta Sans', sans-serif`;
          ctx.fillText("⚡ DOCK BAY A", pt.x - size / 2, pt.y - size / 2 - 5);
        } else if (name.includes("Kitchen")) {
          const size = 44 * zoomLevel;

          // Warm radiant chef heat lamp spill
          const heatGrad = ctx.createRadialGradient(pt.x, pt.y, 4, pt.x, pt.y, size * 1.3);
          heatGrad.addColorStop(0, 'rgba(245, 158, 11, 0.28)');
          heatGrad.addColorStop(1, 'rgba(245, 158, 11, 0.0)');
          ctx.fillStyle = heatGrad;
          ctx.beginPath();
          ctx.arc(pt.x, pt.y, size * 1.3, 0, Math.PI * 2);
          ctx.fill();

          ctx.fillStyle = 'rgba(56, 189, 248, 0.22)';
          ctx.strokeStyle = '#60a5fa';
          ctx.lineWidth = 2 * zoomLevel;
          ctx.beginPath();
          ctx.roundRect(pt.x - size / 2, pt.y - size / 2, size, size, 8 * zoomLevel);
          ctx.fill();
          ctx.stroke();

          ctx.fillStyle = '#93c5fd';
          ctx.font = `bold ${Math.round(10 * Math.min(1.4, zoomLevel))}px 'Plus Jakarta Sans', sans-serif`;
          ctx.fillText("🍳 KITCHEN PASS", pt.x - size / 2 - 4, pt.y - size / 2 - 6);
        }
      });
    }

    // 7. Planned A* Navigation Path
    if (telemetryData && telemetryData.planned_path && telemetryData.planned_path.length > 0) {
      ctx.beginPath();
      const startPt = worldToCanvas(telemetryData.robot_pose.x, telemetryData.robot_pose.y);
      ctx.moveTo(startPt.x, startPt.y);

      telemetryData.planned_path.forEach(wp => {
        const p = worldToCanvas(wp.x, wp.y);
        ctx.lineTo(p.x, p.y);
      });

      ctx.strokeStyle = 'rgba(56, 189, 248, 0.85)';
      ctx.lineWidth = 2.5 * zoomLevel;
      ctx.lineCap = 'round';
      ctx.setLineDash([6 * zoomLevel, 6 * zoomLevel]);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // 8. Motion Breadcrumb Trail
    if (robotTrail.length > 1) {
      for (let i = 0; i < robotTrail.length; i++) {
        const tr = robotTrail[i];
        const p = worldToCanvas(tr.x, tr.y);
        const alpha = (i / robotTrail.length) * 0.45;
        ctx.beginPath();
        ctx.arc(p.x, p.y, Math.max(1.5, 3 * zoomLevel), 0, Math.PI * 2);
        ctx.fillStyle = `rgba(56, 189, 248, ${alpha})`;
        ctx.fill();
      }
    }

    // 9. Guest Roaming in Aisle (Gentle Step Ripples & Polite Safety Bubble)
    if (telemetryData && telemetryData.dynamic_obstacle && telemetryData.dynamic_obstacle.active) {
      const obsPt = worldToCanvas(telemetryData.dynamic_obstacle.pose.x, telemetryData.dynamic_obstacle.pose.y);

      // Walking step radar pulse
      const pulseStep = (Math.sin(Date.now() / 320) + 1) * 2.5;
      ctx.beginPath();
      ctx.arc(obsPt.x, obsPt.y, (12 + pulseStep) * zoomLevel, 0, Math.PI * 2);
      ctx.strokeStyle = 'rgba(245, 158, 11, 0.4)';
      ctx.lineWidth = 1.5 * zoomLevel;
      ctx.stroke();

      // Proximity buffer
      const safetyRadius = (1.3 / (WORLD_MAX_X - WORLD_MIN_X)) * canvas.width * zoomLevel;
      ctx.beginPath();
      ctx.arc(obsPt.x, obsPt.y, safetyRadius, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(245, 158, 11, 0.08)';
      ctx.fill();
      ctx.strokeStyle = 'rgba(245, 158, 11, 0.35)';
      ctx.lineWidth = 1.2 * zoomLevel;
      ctx.setLineDash([4 * zoomLevel, 4 * zoomLevel]);
      ctx.stroke();
      ctx.setLineDash([]);

      // Guest Silhouette
      ctx.beginPath();
      const bodyR = Math.max(7, 11 * zoomLevel);
      ctx.arc(obsPt.x, obsPt.y, bodyR, 0, Math.PI * 2);
      ctx.fillStyle = '#f59e0b';
      ctx.fill();
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 2 * zoomLevel;
      ctx.stroke();

      ctx.fillStyle = '#fbbf24';
      ctx.font = `600 ${Math.round(10 * Math.min(1.4, zoomLevel))}px 'Plus Jakarta Sans', sans-serif`;
      ctx.fillText("🚶 Guest in Aisle", obsPt.x - 36 * zoomLevel, obsPt.y - 16 * zoomLevel);
    }

    // 10. BellaBot Waiter Robot (Headlight Beam, Pearl Chassis, Dynamic Cat Face)
    if (telemetryData && telemetryData.robot_pose) {
      const rPt = worldToCanvas(telemetryData.robot_pose.x, telemetryData.robot_pose.y);
      const isAvoiding = telemetryData.avoidance_active ||
        telemetryData.robot_state === "avoiding_obstacle" ||
        telemetryData.robot_state === "yielding";

      // Blinking eye simulation
      const now = Date.now();
      if (now - lastBlinkTime > 3600) {
        isBlinking = true;
        if (now - lastBlinkTime > 3800) {
          lastBlinkTime = now;
          isBlinking = false;
        }
      }

      // Charging pulse halo
      if (telemetryData.charging_active || telemetryData.robot_state === "charging") {
        ctx.beginPath();
        const pulse = (Math.sin(now / 250) + 1) * 3;
        ctx.arc(rPt.x, rPt.y, (24 + pulse) * zoomLevel, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(16, 185, 129, 0.22)';
        ctx.fill();
        ctx.strokeStyle = '#10b981';
        ctx.lineWidth = 2 * zoomLevel;
        ctx.stroke();
      }

      // Evasive warning ring
      if (isAvoiding) {
        ctx.beginPath();
        ctx.arc(rPt.x, rPt.y, 28 * zoomLevel, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(244, 63, 94, 0.2)';
        ctx.fill();
        ctx.strokeStyle = '#f43f5e';
        ctx.lineWidth = 2 * zoomLevel;
        ctx.stroke();
      }

      ctx.save();
      ctx.translate(rPt.x, rPt.y);
      ctx.rotate(-telemetryData.robot_pose.yaw);
      ctx.scale(zoomLevel, zoomLevel);

      // Headlight Beam Cone Projected Forward
      ctx.beginPath();
      ctx.moveTo(14, -3);
      ctx.lineTo(46, -20);
      ctx.lineTo(46, 20);
      ctx.lineTo(14, 3);
      ctx.closePath();
      const beamGrad = ctx.createLinearGradient(14, 0, 46, 0);
      beamGrad.addColorStop(0, 'rgba(56, 189, 248, 0.22)');
      beamGrad.addColorStop(1, 'rgba(56, 189, 248, 0.0)');
      ctx.fillStyle = beamGrad;
      ctx.fill();

      // Outer Base Chassis
      ctx.beginPath();
      ctx.ellipse(0, 0, 16, 14, 0, 0, Math.PI * 2);
      ctx.fillStyle = '#0f172a';
      ctx.fill();
      ctx.strokeStyle = isAvoiding ? '#f43f5e' : (telemetryData.robot_state === 'charging' ? '#10b981' : '#38bdf8');
      ctx.lineWidth = 2.5;
      ctx.stroke();

      // Top Pearl Plate
      ctx.beginPath();
      ctx.ellipse(-2, 0, 12, 10, 0, 0, Math.PI * 2);
      ctx.fillStyle = '#f8fafc';
      ctx.fill();

      // 3-Tier Tray Indicators
      ctx.strokeStyle = '#334155';
      ctx.lineWidth = 1.2;
      ctx.strokeRect(-7, -7, 10, 3.5);
      ctx.strokeRect(-7, -1.75, 10, 3.5);
      ctx.strokeRect(-7, 3.5, 10, 3.5);

      // Cat Ears with soft interior
      ctx.fillStyle = isAvoiding ? '#f43f5e' : (telemetryData.robot_state === 'charging' ? '#10b981' : '#38bdf8');
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

      // Front Face Screen with Digital Cat Eyes
      ctx.fillStyle = '#1e293b';
      ctx.strokeStyle = isAvoiding ? '#f43f5e' : (telemetryData.robot_state === 'charging' ? '#10b981' : '#38bdf8');
      ctx.lineWidth = 1.2;
      ctx.fillRect(8, -7, 4, 14);
      ctx.strokeRect(8, -7, 4, 14);

      // Digital Cat Eyes Expression
      ctx.fillStyle = isAvoiding ? '#f43f5e' : (telemetryData.robot_state === 'charging' ? '#10b981' : '#38bdf8');
      ctx.font = 'bold 5px monospace';
      ctx.textAlign = 'center';

      if (isBlinking) {
        ctx.fillText('--', 10, -1);
      } else if (telemetryData.robot_state === 'charging') {
        ctx.fillText('zZ', 10, -1);
      } else if (isAvoiding) {
        ctx.fillText('!!', 10, -1);
      } else if (telemetryData.robot_state === 'navigating') {
        ctx.fillText('^ ^', 10, -1);
      } else {
        ctx.fillText('• •', 10, -1);
      }
      ctx.textAlign = 'start';

      // Heading Direction Indicator
      ctx.beginPath();
      ctx.moveTo(13, 0);
      ctx.lineTo(22, 0);
      ctx.strokeStyle = '#38bdf8';
      ctx.lineWidth = 3;
      ctx.stroke();

      ctx.restore();

      // Robot Label Badge
      ctx.fillStyle = '#ffffff';
      ctx.font = `bold ${Math.round(10 * Math.min(1.4, zoomLevel))}px 'Plus Jakarta Sans', sans-serif`;
      const labelText = isAvoiding ? "🛑 YIELDING" : "🐱 BELLABOT #1";
      ctx.fillText(labelText, rPt.x - 30 * zoomLevel, rPt.y + 24 * zoomLevel);
    }

    requestAnimationFrame(renderMap);
  }

  // WebSocket Connection Handler
  function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/telemetry`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      document.getElementById('conn-text').textContent = 'Live';
      document.querySelector('#connection-status .dot').className = 'dot online';
      logSystem("Connected to BellaBot telemetry link.", 'info');
      showToast("Fleet Link Established · System Online", '🟢');
    };

    ws.onmessage = (event) => {
      try {
        telemetryData = JSON.parse(event.data);

        // Record breadcrumb trail point
        if (telemetryData.robot_pose) {
          robotTrail.push({ x: telemetryData.robot_pose.x, y: telemetryData.robot_pose.y });
          if (robotTrail.length > MAX_TRAIL_LENGTH) robotTrail.shift();
        }

        // Detect state transitions for sound effects
        detectStateAudioCues(telemetryData);

        updateDashboardUI(telemetryData);
      } catch (err) {
        console.error("Error parsing WebSocket payload:", err);
      }
    };

    ws.onclose = () => {
      document.getElementById('conn-text').textContent = 'Reconnecting...';
      document.querySelector('#connection-status .dot').className = 'dot offline';
      setTimeout(connectWebSocket, 2000);
    };
  }

  function detectStateAudioCues(data) {
    if (!data) return;

    // Detect when robot yields to an obstacle
    if (data.robot_state === 'yielding' && prevRobotState !== 'yielding') {
      playChime('yield');
      showToast("BellaBot yielding to guest in dining aisle", '⚠️');
    }

    // Detect when robot finishes delivery task
    if (prevTaskId && (!data.current_task || data.current_task.id !== prevTaskId)) {
      playChime('arrive');
      showToast(`Arrived at destination · Trays ready for guest pickup`, '✨');
    }

    prevTaskId = data.current_task ? data.current_task.id : null;
    prevRobotState = data.robot_state;
  }

  // Humanize Location Helper
  function formatFloorLocation(x, y) {
    if (x > 5.5 && y < -11.0) return "Charging Bay (Station A)";
    if (x < -9.0 && y > -2.5) return "Kitchen Pass (Expedite Counter)";
    if (y > 0.0) return "North Terrace Wing";
    if (y <= 0.0 && y > -4.5) return "Mid Lounge Banquette Area";
    if (y <= -4.5 && y > -8.5) return "Central Dining Salon";
    if (y <= -8.5) return "South Promenade Wing";
    return "Dining Floor Corridor";
  }

  function getZoneAbbr(loc) {
    if (loc.includes("Charging")) return "Dock";
    if (loc.includes("Kitchen")) return "Kitchen";
    if (loc.includes("Terrace")) return "Terrace";
    if (loc.includes("Lounge")) return "Lounge";
    if (loc.includes("Salon")) return "Salon";
    return "Dining";
  }

  // Humanize Robot State
  function formatHumanState(rawState, isCharging) {
    if (isCharging) return { label: 'Charging at Bay', dotClass: 'charging' };
    switch (rawState) {
      case 'idle': return { label: 'Ready for Orders', dotClass: 'idle' };
      case 'navigating': return { label: 'En Route to Table', dotClass: 'navigating' };
      case 'docking': return { label: 'Returning to Bay', dotClass: 'docking' };
      case 'docked': return { label: 'Parked (Standby)', dotClass: 'docked' };
      case 'charging': return { label: 'Charging at Bay', dotClass: 'charging' };
      case 'yielding': return { label: 'Yielding to Guest', dotClass: 'yielding' };
      case 'avoiding_obstacle': return { label: 'Evasive Maneuver', dotClass: 'avoiding' };
      case 'low_battery_rerouting': return { label: 'Low Battery Return', dotClass: 'docking' };
      default: return { label: rawState || 'Ready for Orders', dotClass: 'idle' };
    }
  }

  // Update UI Elements with Live Telemetry
  function updateDashboardUI(data) {
    // 1. Battery BMS Metrics & Runtime Estimate
    const batPct = data.battery_percentage;
    const isCharging = data.charging_active || data.robot_state === "charging";

    const runtimeEstimate = isCharging ? 'Charging' : `~${(batPct * 0.055).toFixed(1)}h service`;

    const batPctEl = document.getElementById('battery-pct-text');
    const batFillEl = document.getElementById('battery-fill');

    if (isCharging) {
      batPctEl.innerHTML = `⚡ ${batPct.toFixed(1)}% <span style="font-size:10px;color:#10b981;font-weight:600;">(Charging)</span>`;
      batFillEl.style.background = '#10b981';
      batFillEl.style.boxShadow = '0 0 10px rgba(16, 185, 129, 0.8)';
    } else {
      batPctEl.textContent = `${batPct.toFixed(1)}% (${runtimeEstimate})`;
      batFillEl.style.boxShadow = 'none';
      if (batPct < 20) {
        batFillEl.style.background = '#ef4444';
      } else if (batPct < 50) {
        batFillEl.style.background = '#f59e0b';
      } else {
        batFillEl.style.background = '#10b981';
      }
    }

    batFillEl.style.width = `${batPct}%`;
    document.getElementById('battery-voltage-text').textContent = `${data.voltage.toFixed(2)} V`;
    document.getElementById('battery-current-text').textContent = `${(data.current_amps || 0).toFixed(2)} A${isCharging ? ' (In)' : ' (Out)'}`;

    const currentDirChip = document.getElementById('current-dir-chip');
    if (currentDirChip) {
      currentDirChip.textContent = isCharging ? 'Charge' : 'Load';
      currentDirChip.className = isCharging ? 'telemetry-chip chip-green' : 'telemetry-chip chip-amber';
    }

    document.getElementById('battery-power-text').textContent = `${(data.power_watts || 0).toFixed(1)} W`;
    document.getElementById('battery-temp-text').textContent = `${(data.temperature_c || 24.5).toFixed(1)} °C`;

    // 2. Robot State & Friendly Badge
    const stateObj = formatHumanState(data.robot_state, isCharging);
    document.getElementById('robot-state-text').textContent = stateObj.label;
    const dot = document.querySelector('#robot-state-badge .dot');
    dot.className = `dot ${stateObj.dotClass}`;

    // Sync Auto-Charge toggle switch if not actively focused
    const autoChargeToggle = document.getElementById('auto-charge-toggle');
    if (autoChargeToggle && data.auto_charge_at_dock !== undefined && document.activeElement !== autoChargeToggle) {
      autoChargeToggle.checked = Boolean(data.auto_charge_at_dock);
    }

    const avoidBadge = document.getElementById('avoidance-badge');
    if (avoidBadge) {
      if (data.avoidance_active || data.robot_state === "avoiding_obstacle" || data.robot_state === "yielding") {
        avoidBadge.style.display = 'inline-block';
        avoidBadge.textContent = data.robot_state === "yielding" ? "🛑 YIELDING TO GUEST" : "⚠️ AVOIDING OBSTACLE";
      } else {
        avoidBadge.style.display = 'none';
      }
    }

    // 3. Location & Coordinates
    const px = data.robot_pose.x.toFixed(2);
    const py = data.robot_pose.y.toFixed(2);
    const yawDeg = Math.round(((data.robot_pose.yaw * 180 / Math.PI) % 360 + 360) % 360);
    const locationName = formatFloorLocation(data.robot_pose.x, data.robot_pose.y);
    document.getElementById('robot-pos-text').textContent = locationName;

    const locZoneChip = document.getElementById('location-zone-chip');
    if (locZoneChip) locZoneChip.textContent = getZoneAbbr(locationName);

    const coordsSub = document.getElementById('robot-coords-sub');
    if (coordsSub) {
      coordsSub.textContent = `x: ${px}m, y: ${py}m · Heading: ${yawDeg}°`;
    }

    // 4. Current Mission Display
    const taskStateChip = document.getElementById('task-state-chip');
    const taskDetailSub = document.getElementById('task-detail-sub');

    if (data.current_task) {
      const t = data.current_task;
      if (t.target === "Dock") {
        document.getElementById('current-task-text').textContent = isCharging ? "⚡ Charging at Station A" : "🔌 Returning to Charging Bay";
        if (taskStateChip) taskStateChip.textContent = isCharging ? "Charging" : "Docking";
        if (taskDetailSub) taskDetailSub.textContent = "Autonomous battery top-up sequence";
      } else {
        document.getElementById('current-task-text').textContent = `Delivering ${t.item} to ${t.target}`;
        if (taskStateChip) taskStateChip.textContent = "Delivering";
        if (taskDetailSub) taskDetailSub.textContent = `Active delivery order #${t.id}`;
      }
    } else {
      document.getElementById('current-task-text').textContent = isCharging ? "⚡ Charging at Station A" : "Standby (Ready for orders)";
      if (taskStateChip) taskStateChip.textContent = isCharging ? "Charging" : "Standby";
      if (taskDetailSub) taskDetailSub.textContent = "Ready to receive orders from Waitstaff";
    }

    // 5. Stylized 3-Tier Robot Tray Rack
    if (data.shelves) {
      for (const [sId, sData] of Object.entries(data.shelves)) {
        const num = sId.replace('shelf_', '');
        const cardEl = document.getElementById(`shelf-${num}-card`);
        const itemEl = document.getElementById(`shelf-${num}-item`);
        const statusEl = document.getElementById(`shelf-${num}-status`);

        if (cardEl && itemEl && statusEl) {
          if (sData.status === "loaded" && sData.item) {
            itemEl.innerHTML = `<strong style="color:#f8fafc;">${sData.item}</strong>`;
            statusEl.textContent = "Loaded";
            statusEl.className = "shelf-status-pill loaded";
            cardEl.className = "tray-shelf loaded";
          } else {
            itemEl.textContent = "Empty / Ready for Loading";
            statusEl.textContent = "Ready";
            statusEl.className = "shelf-status-pill empty";
            cardEl.className = "tray-shelf";
          }
        }
      }
    }

    // 6. Delivery Queue Display
    if (data.queue) {
      renderQueue(data.queue, data.current_task);
    }
  }

  function renderQueue(queue, currentTask) {
    const queueList = document.getElementById('queue-list');
    const queueCountBadge = document.getElementById('queue-count');
    const allTasks = [];

    if (currentTask) {
      allTasks.push({ ...currentTask, isActive: true });
    }
    if (queue && queue.length > 0) {
      allTasks.push(...queue.map(q => ({ ...q, isActive: false })));
    }

    if (queueCountBadge) {
      queueCountBadge.textContent = `${allTasks.length} ${allTasks.length === 1 ? 'Order' : 'Orders'}`;
    }

    if (allTasks.length === 0) {
      queueList.innerHTML = '<div class="empty-state">No pending deliveries in queue. Ready for dining orders.</div>';
    } else {
      queueList.innerHTML = allTasks.map(item => `
        <div class="queue-item ${item.isActive ? 'active-task' : ''}">
          <div class="queue-details">
            <span class="queue-id">${item.id}</span>
            <span class="queue-target">📍 ${item.target}</span>
            <span class="queue-item-name">${item.item}</span>
          </div>
          <span class="badge ${item.isActive ? 'admin-badge' : 'user-badge'}">${item.isActive ? 'DELIVERING' : 'QUEUED'}</span>
        </div>
      `).join('');
    }
  }

  // Live Digital Clock
  function updateLiveClock() {
    const clockEl = document.getElementById('live-clock');
    if (clockEl) {
      const now = new Date();
      clockEl.textContent = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    }
  }
  setInterval(updateLiveClock, 1000);
  updateLiveClock();

  // Service Shift Presets System
  const SHIFT_MENUS = {
    dinner: {
      tag: "Dinner Menu",
      items: [
        { label: "☕ Double Espresso", desc: "Hot Espresso & Biscotti" },
        { label: "🥐 Butter Croissant", desc: "Warm Butter Croissant & Jam" },
        { label: "🍷 Pinot Noir", desc: "House Pinot Noir (Carafe)" },
        { label: "🥗 Burrata Salad", desc: "Burrata & Heirloom Tomato" },
        { label: "🍝 Truffle Pasta", desc: "Truffle Tagliatelle Pasta" },
        { label: "🍰 Tiramisu", desc: "Classic Tiramisu & Berries" }
      ]
    },
    lunch: {
      tag: "Bistro Lunch",
      items: [
        { label: "🧊 Iced Americano", desc: "Double Shot Iced Americano" },
        { label: "🥪 Club Sandwich", desc: "Artisanal Turkey & Avocado Club" },
        { label: "🥖 Croque Monsieur", desc: "Warm Gruyère Croque Monsieur" },
        { label: "🥗 Garden Salad", desc: "Crisp Greens & Champagne Vinaigrette" },
        { label: "🍋 Sparkling Soda", desc: "Craft Rosemary Lemon Soda" },
        { label: "🥧 Lemon Tart", desc: "Meyer Lemon Meringue Tart" }
      ]
    },
    lounge: {
      tag: "Lounge & Cocktails",
      items: [
        { label: "🥃 Smoked Negroni", desc: "Classic Smoked Campari Negroni" },
        { label: "🍟 Truffle Fries", desc: "Parmesan & Rosemary Truffle Fries" },
        { label: "🧀 Charcuterie", desc: "Chef Selection Artisanal Cheeses" },
        { label: "🍾 Champagne", desc: "Glass of Brut Reserve Champagne" },
        { label: "🍸 Espresso Martini", desc: "Velvet Espresso Vodka Martini" },
        { label: "🫒 Marinated Olives", desc: "Castelvetrano Herb Olives" }
      ]
    }
  };

  function updateMenuChips(shiftKey) {
    const menuData = SHIFT_MENUS[shiftKey] || SHIFT_MENUS.dinner;
    const tagEl = document.getElementById('current-menu-tag');
    if (tagEl) tagEl.textContent = menuData.tag;

    const chipsContainer = document.getElementById('quick-chips-container');
    if (chipsContainer) {
      chipsContainer.innerHTML = menuData.items.map(item => `
        <button type="button" class="quick-chip" data-item="${item.desc}">${item.label}</button>
      `).join('');

      // Re-bind click listeners
      chipsContainer.querySelectorAll('.quick-chip').forEach(chip => {
        chip.addEventListener('click', () => {
          playChime('tap');
          const input = document.getElementById('item-input');
          if (input) {
            input.value = chip.dataset.item;
            input.focus();
          }
        });
      });
    }
  }

  // Shift Buttons Listeners
  document.querySelectorAll('.shift-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.shift-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const shift = btn.dataset.shift;
      playChime('tap');
      updateMenuChips(shift);
      showToast(`Switched service shift: ${btn.textContent}`, '🍽️');
    });
  });

  // Initial Quick Chips Setup
  updateMenuChips('dinner');

  // Dining Zone Filter Chips
  document.querySelectorAll('.zone-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      document.querySelectorAll('.zone-chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      playChime('tap');

      const zone = chip.dataset.zone;
      const targetSelect = document.getElementById('target-select');
      const optgroups = targetSelect.querySelectorAll('optgroup');

      optgroups.forEach(og => {
        if (zone === 'all') {
          og.style.display = '';
        } else if (og.dataset.group === zone) {
          og.style.display = '';
          const firstOpt = og.querySelector('option');
          if (firstOpt) targetSelect.value = firstOpt.value;
        } else {
          og.style.display = 'none';
        }
      });
    });
  });

  // Order Submission
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
        playChime('order');
        logSystem(`Order dispatched: ${item} -> ${target} (${data.task.id})`, 'info');
        showToast(`Dispatched to ${target}: ${item}`, '🚀');
        document.getElementById('item-input').value = '';
      } else {
        logSystem(`Dispatch notice: ${data.detail}`, 'warn');
        showToast(data.detail, '⚠️');
      }
    } catch (err) {
      logSystem(`Network error submitting order`, 'warn');
      showToast("Network error submitting order", '❌');
    }
  });

  // Quick Recall to Kitchen Button
  const quickKitchenBtn = document.getElementById('quick-kitchen-btn');
  if (quickKitchenBtn) {
    quickKitchenBtn.addEventListener('click', async () => {
      playChime('tap');
      try {
        const res = await fetch('/api/delivery', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ target: 'Kitchen/Pickup', item: 'Order Pickup & Expedite' })
        });
        const data = await res.json();
        if (res.ok) {
          playChime('order');
          logSystem(`Recalled BellaBot to Kitchen Pass for loading`, 'info');
          showToast("Recalled BellaBot to Kitchen Pass", '🍳');
        } else {
          logSystem(`Notice: ${data.detail}`, 'warn');
          showToast(data.detail, '⚠️');
        }
      } catch (err) {
        logSystem("Failed to recall to kitchen.", 'warn');
      }
    });
  }

  // Clear Trays Action
  const clearTraysBtn = document.getElementById('clear-trays-btn');
  if (clearTraysBtn) {
    clearTraysBtn.addEventListener('click', async () => {
      playChime('tap');
      try {
        await fetch('/api/queue', { method: 'DELETE' });
        logSystem("Cleared all loaded items from robot trays.", 'info');
        showToast("Trays cleared & ready for loading", '✨');
      } catch (err) {
        logSystem("Failed to clear trays.", 'warn');
      }
    });
  }

  // Auto-Charge at Dock Switch Listener
  const autoChargeToggleEl = document.getElementById('auto-charge-toggle');
  if (autoChargeToggleEl) {
    autoChargeToggleEl.addEventListener('change', async (e) => {
      playChime('tap');
      try {
        const res = await fetch('/api/dock/charge_option', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ auto_charge: e.target.checked })
        });
        const data = await res.json();
        const stateText = data.auto_charge_at_dock ? 'ENABLED' : 'DISABLED';
        logSystem(`Auto-Recharge setting: ${stateText}`, 'info');
        showToast(`Auto-recharge at bay ${stateText}`, '⚡');
      } catch (err) {
        logSystem("Failed to update auto-charge setting.", 'warn');
      }
    });
  }

  // Start Charging at Dock Button Listener
  const startChargeBtn = document.getElementById('start-charge-btn');
  if (startChargeBtn) {
    startChargeBtn.addEventListener('click', async () => {
      playChime('tap');
      try {
        const res = await fetch('/api/dock/start_charge', { method: 'POST' });
        const data = await res.json();
        logSystem(data.message, 'info');
        showToast(data.message, '⚡');
      } catch (err) {
        logSystem("Failed to command charging at dock.", 'warn');
      }
    });
  }

  // Manual Dock Button
  document.getElementById('manual-dock-btn').addEventListener('click', async () => {
    playChime('tap');
    try {
      await fetch('/api/dock', { method: 'POST' });
      logSystem("Operator commanded BellaBot to return to Charging Bay.", 'info');
      showToast("Returning BellaBot to Charging Bay A", '🔌');
    } catch (err) {
      logSystem("Failed to send dock command.", 'warn');
    }
  });

  // Low Battery Trigger Button
  const lowBatBtn = document.getElementById('low-battery-btn');
  if (lowBatBtn) {
    lowBatBtn.addEventListener('click', async () => {
      playChime('tap');
      try {
        const res = await fetch('/api/battery/low', { method: 'POST' });
        if (res.ok) {
          logSystem("🪫 Low battery simulated (15%). Auto-docking initiated.", 'warn');
          showToast("Simulated low battery (15%) · Auto-docking", '🪫');
        }
      } catch (err) {
        logSystem("Failed to trigger low battery state.", 'warn');
      }
    });
  }

  // Toggle Guest in Aisle (Dynamic Obstacle)
  document.getElementById('toggle-obstacle-btn').addEventListener('click', async () => {
    playChime('tap');
    dynamicObstacleActive = !dynamicObstacleActive;
    try {
      await fetch('/api/obstacle/trigger', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active: dynamicObstacleActive })
      });
      const statusStr = dynamicObstacleActive ? 'ACTIVE in aisles' : 'INACTIVE';
      logSystem(`Guest roaming simulation: ${statusStr}`, 'info');
      showToast(`Guest simulation ${dynamicObstacleActive ? 'walking aisles' : 'left floor'}`, '🚶');
    } catch (err) {
      logSystem("Failed to toggle guest obstacle.", 'warn');
    }
  });

  // Clear Queue & Reset Button
  document.getElementById('clear-queue-btn').addEventListener('click', async () => {
    playChime('tap');
    try {
      await fetch('/api/queue', { method: 'DELETE' });
      logSystem("Order queue and server trays cleared.", 'info');
      showToast("Service queue cleared", '🗑️');
    } catch (err) {
      logSystem("Failed to clear queue.", 'warn');
    }
  });

  // Clear Activity Log Button
  const clearLogBtn = document.getElementById('clear-log-btn');
  if (clearLogBtn) {
    clearLogBtn.addEventListener('click', () => {
      playChime('tap');
      const logBox = document.getElementById('sys-log');
      if (logBox) {
        logBox.innerHTML = '<div class="log-entry system">[CLEARED] Activity log refreshed.</div>';
      }
    });
  }

  // Map Controls: Zoom In, Zoom Out, Reset, Follow Cam
  const zoomInBtn = document.getElementById('zoom-in-btn');
  if (zoomInBtn) {
    zoomInBtn.addEventListener('click', () => {
      playChime('tap');
      zoomLevel = Math.min(4.5, zoomLevel * 1.25);
    });
  }

  const zoomOutBtn = document.getElementById('zoom-out-btn');
  if (zoomOutBtn) {
    zoomOutBtn.addEventListener('click', () => {
      playChime('tap');
      zoomLevel = Math.max(0.5, zoomLevel * 0.8);
    });
  }

  const resetBtn = document.getElementById('reset-view-btn');
  if (resetBtn) {
    resetBtn.addEventListener('click', () => {
      playChime('tap');
      zoomLevel = 1.0;
      panOffsetX = 0.0;
      panOffsetY = 0.0;
      isFollowingRobot = true;
      const followBtn = document.getElementById('toggle-follow-btn');
      if (followBtn) {
        followBtn.textContent = '🎥 Follow: ON';
        followBtn.className = 'btn btn-sm btn-primary';
      }
      adjustCanvasSize();
      logSystem("Floorplan view centered to 100%.", 'info');
      showToast("Floorplan scale reset to 100%", '⟲');
    });
  }

  const toggleFollowBtn = document.getElementById('toggle-follow-btn');
  if (toggleFollowBtn) {
    toggleFollowBtn.addEventListener('click', () => {
      playChime('tap');
      isFollowingRobot = !isFollowingRobot;
      toggleFollowBtn.textContent = isFollowingRobot ? '🎥 Follow: ON' : '🎥 Follow: OFF';
      toggleFollowBtn.className = isFollowingRobot ? 'btn btn-sm btn-primary' : 'btn btn-sm btn-outline';
    });
  }

  function logSystem(msg, type = 'system') {
    const logBox = document.getElementById('sys-log');
    if (!logBox) return;
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
