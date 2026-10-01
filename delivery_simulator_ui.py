#!/usr/bin/env python3
from __future__ import annotations
"""
CSTAM: Delivery Process Simulator Interface & Mission Control Dashboard
Native graphical and interactive interface to simulate placing food/beverage orders,
monitoring the delivery queue, and testing autonomous docking behavior across worlds:
- Dar Tunibot (resto_arbi.world: Table 1 to Table 10, Kitchen/Pickup, Dock)
- Restaurant Lounge (restaurant.world: Table 0 to Table 23, Kitchen/Pickup, Dock)
"""

import sys
import os
import time
import json
import threading

# ROS 2 imports with graceful fallback
try:
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import String, Bool
    HAVE_ROS2 = True
except ImportError:
    HAVE_ROS2 = False

# Tkinter imports with CLI fallback
try:
    import tkinter as tk
    from tkinter import ttk, messagebox
    HAVE_TKINTER = True
except ImportError:
    HAVE_TKINTER = False


WORLDS_CONFIG = {
    "Dar Tunibot (resto_arbi.world)": {
        "short_name": "resto_arbi",
        "title": "Dar Tunibot · Mediterranean Heritage Restaurant",
        "tables": [f"Table {i}" for i in range(1, 11)] + ["Kitchen/Pickup", "Dock"],
        "presets": [
            "☕ Café Direct & Bambalouni",
            "🍲 Traditional Brik à l'Oeuf",
            "🥗 Salade Tunisienne",
            "🥘 Couscous Royal & Lamb",
            "🥤 Citronnade aux Amandes",
            "🍰 Makroudh au Miel"
        ],
        "default_table": "Table 1",
        "default_item": "☕ Café Direct & Bambalouni"
    },
    "Restaurant Lounge (restaurant.world)": {
        "short_name": "restaurant",
        "title": "Modern Restaurant Lounge & Grand Promenade",
        "tables": [f"Table {i}" for i in range(24)] + ["Kitchen/Pickup", "Dock"],
        "presets": [
            "☕ Espresso & Croissant",
            "🍔 Bella Burger & Fries",
            "🍝 Chef's Pasta Carbonara",
            "🥗 Mediterranean Salad",
            "🥤 Sparkling Lemonade",
            "🍰 Tiramisu Dessert"
        ],
        "default_table": "Table 1",
        "default_item": "☕ Espresso & Croissant"
    }
}


def detect_initial_world() -> str:
    # 1. Check command line args
    for idx, arg in enumerate(sys.argv):
        if arg in ["--world", "-w"] and idx + 1 < len(sys.argv):
            val = sys.argv[idx + 1].lower()
            if "resto" in val or "arbi" in val or "dar" in val:
                return "Dar Tunibot (resto_arbi.world)"
            return "Restaurant Lounge (restaurant.world)"
        if "world:=resto" in arg.lower() or "world:=arbi" in arg.lower():
            return "Dar Tunibot (resto_arbi.world)"
        if "world:=rest" in arg.lower():
            return "Restaurant Lounge (restaurant.world)"

    # 2. Check environment variable
    env_world = os.environ.get("CSTAM_WORLD", "").lower()
    if "resto" in env_world or "arbi" in env_world:
        return "Dar Tunibot (resto_arbi.world)"

    # 3. Default to Dar Tunibot if resto_arbi map is present
    if os.path.exists("ros2_ws/src/cstam_navigation/maps/resto_arbi_map.yaml"):
        return "Dar Tunibot (resto_arbi.world)"

    return "Restaurant Lounge (restaurant.world)"


class Ros2DeliveryBridge:
    def __init__(self):
        self.node = None
        self.req_pub = None
        self.dock_pub = None
        self.action_pub = None

        self.latest_status = {
            "robot_state": "idle",
            "current_task": None,
            "queue_length": 0,
            "pending_tasks": [],
            "completed_count": 0
        }
        self.is_docked = False
        self._mock_task_id = 1

        if HAVE_ROS2:
            try:
                if not rclpy.ok():
                    rclpy.init()
                self.node = rclpy.create_node('cstam_delivery_simulator_ui')
                
                # Publishers
                self.req_pub = self.node.create_publisher(String, '/delivery_request', 10)
                self.dock_pub = self.node.create_publisher(String, '/dock_command', 10)
                self.action_pub = self.node.create_publisher(String, '/delivery_task_action', 10)

                # Subscribers
                self.node.create_subscription(String, '/delivery_queue_status', self._status_cb, 10)
                self.node.create_subscription(String, '/robot_system_state', self._state_cb, 10)
                self.node.create_subscription(Bool, '/dock_state', self._dock_cb, 10)

                # Spin thread
                threading.Thread(target=self._spin_worker, daemon=True).start()
            except Exception as e:
                print(f"[Simulator] Warning: Could not initialize ROS 2 node ({e}). Using mock mode.")

    def _spin_worker(self):
        try:
            rclpy.spin(self.node)
        except Exception:
            pass

    def _status_cb(self, msg: String):
        try:
            data = json.loads(msg.data)
            self.latest_status.update(data)
        except Exception:
            pass

    def _state_cb(self, msg: String):
        self.latest_status["robot_state"] = msg.data

    def _dock_cb(self, msg: Bool):
        self.is_docked = msg.data
        if msg.data:
            self.latest_status["robot_state"] = "docked"

    def dispatch_order(self, target: str, item: str):
        payload = json.dumps({"target": target, "item": item})
        if self.req_pub:
            msg = String()
            msg.data = payload
            self.req_pub.publish(msg)
            return True
        else:
            # Standalone mock fallback
            tid = f"TASK-{self._mock_task_id:04d}"
            self._mock_task_id += 1
            self.latest_status["queue_length"] += 1
            self.latest_status["pending_tasks"].append({
                "id": tid,
                "target": target,
                "item": item
            })
            return True

    def delete_task(self, task_id: str):
        payload = json.dumps({"action": "delete", "task_id": task_id})
        if self.action_pub:
            msg = String()
            msg.data = payload
            self.action_pub.publish(msg)
        # Update mock cache
        self.latest_status["pending_tasks"] = [
            t for t in self.latest_status["pending_tasks"] if t.get("id") != task_id
        ]
        self.latest_status["queue_length"] = len(self.latest_status["pending_tasks"])
        return True

    def modify_task(self, task_id: str, new_target: str, new_item: str):
        payload = json.dumps({"action": "modify", "task_id": task_id, "target": new_target, "item": new_item})
        if self.action_pub:
            msg = String()
            msg.data = payload
            self.action_pub.publish(msg)
        # Update mock cache
        for t in self.latest_status["pending_tasks"]:
            if t.get("id") == task_id:
                if new_target: t["target"] = new_target
                if new_item: t["item"] = new_item
        return True

    def trigger_dock(self, reason="manual"):
        if self.dock_pub:
            msg = String()
            msg.data = f"DOCK_NOW:{reason}"
            self.dock_pub.publish(msg)
        else:
            self.latest_status["robot_state"] = "docking"

    def stop_docking(self):
        if self.dock_pub:
            msg = String()
            msg.data = "STOP_DOCK"
            self.dock_pub.publish(msg)
        if self.action_pub:
            msg2 = String()
            msg2.data = json.dumps({"action": "stop_dock"})
            self.action_pub.publish(msg2)
        if self.latest_status["robot_state"] == "docking":
            self.latest_status["robot_state"] = "idle"


class DeliverySimulatorGUI:
    def __init__(self, root, bridge: Ros2DeliveryBridge, initial_world: str):
        self.root = root
        self.bridge = bridge
        self.current_world = initial_world
        self.root.title("CSTAM - Autonomous Waiter Robot Control Dashboard")
        self.root.geometry("920x720")
        self.root.configure(bg="#1e1e24")

        self.selected_task_id = None
        self._cached_queue_sig = None
        self.preset_buttons = []

        self._setup_styles()
        self._build_ui()
        self._update_loop()

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure(".", background="#1e1e24", foreground="#ffffff", font=("DejaVu Sans", 10))
        style.configure("TLabel", background="#1e1e24", foreground="#e0e0e0")
        style.configure("TFrame", background="#1e1e24")
        style.configure("TLabelframe", background="#1e1e24", foreground="#00adb5", bordercolor="#393e46")
        style.configure("TLabelframe.Label", background="#1e1e24", foreground="#00adb5", font=("DejaVu Sans", 11, "bold"))
        style.configure("TButton", background="#00adb5", foreground="#ffffff", font=("DejaVu Sans", 10, "bold"), borderwidth=0)
        style.map("TButton", background=[("active", "#00838f"), ("pressed", "#006064")])
        style.configure("Danger.TButton", background="#e63946", foreground="#ffffff")
        style.map("Danger.TButton", background=[("active", "#d62828"), ("pressed", "#ba181b")])
        style.configure("Success.TButton", background="#2a9d8f", foreground="#ffffff")
        style.map("Success.TButton", background=[("active", "#21867a")])

        # Entry styling
        style.configure("TEntry", fieldbackground="#2b2d42", foreground="#ffffff", insertcolor="#ffffff", bordercolor="#4b5563")
        style.map("TEntry", fieldbackground=[("focus", "#334155")])

        # Combobox styling
        style.configure("TCombobox", fieldbackground="#2b2d42", background="#393e46", foreground="#ffffff",
                        selectbackground="#00adb5", selectforeground="#ffffff", arrowcolor="#ffffff")
        style.map("TCombobox",
                  fieldbackground=[("readonly", "#2b2d42"), ("focus", "#334155")],
                  foreground=[("readonly", "#ffffff"), ("focus", "#ffffff")])
        self.root.option_add('*TCombobox*Listbox.background', '#2b2d42')
        self.root.option_add('*TCombobox*Listbox.foreground', '#ffffff')
        self.root.option_add('*TCombobox*Listbox.selectBackground', '#00adb5')
        self.root.option_add('*TCombobox*Listbox.selectForeground', '#ffffff')

    def _build_ui(self):
        # 1. Header & Live Robot Status Card
        header_frame = tk.Frame(self.root, bg="#2b2d42", padx=16, pady=10)
        header_frame.pack(fill="x", padx=12, pady=(10, 6))

        top_row = tk.Frame(header_frame, bg="#2b2d42")
        top_row.pack(fill="x")

        self.title_lbl = tk.Label(
            top_row,
            text=f"🤖 CSTAM Control Dashboard: {WORLDS_CONFIG[self.current_world]['title']}",
            font=("DejaVu Sans", 13, "bold"), fg="#ffffff", bg="#2b2d42"
        )
        self.title_lbl.pack(side="left")

        status_bar = tk.Frame(header_frame, bg="#2b2d42", pady=6)
        status_bar.pack(fill="x")

        tk.Label(status_bar, text="Robot State: ", font=("DejaVu Sans", 10, "bold"), fg="#a0aab2", bg="#2b2d42").pack(side="left")
        self.state_badge = tk.Label(status_bar, text="IDLE", font=("DejaVu Sans", 10, "bold"),
                                    fg="#ffffff", bg="#457b9d", padx=10, pady=2)
        self.state_badge.pack(side="left", padx=6)

        self.dock_badge = tk.Label(status_bar, text="UNDOCKED", font=("DejaVu Sans", 10, "bold"),
                                   fg="#ffffff", bg="#6c757d", padx=8, pady=2)
        self.dock_badge.pack(side="right")

        # 2. Main Content Layout (Left: Order Dispatcher, Right: Live Task Queue)
        content_frame = tk.Frame(self.root, bg="#1e1e24")
        content_frame.pack(fill="both", expand=True, padx=12, pady=4)

        # Left Column: Order Dispatcher
        left_col = ttk.LabelFrame(content_frame, text=" 🍽️ Order Dispatcher & Environment ", padding=12)
        left_col.pack(side="left", fill="both", expand=True, padx=(0, 6))

        # World / Environment Selector
        ttk.Label(left_col, text="Active Floor Plan / World:", font=("DejaVu Sans", 10, "bold")).pack(anchor="w", pady=(0, 2))
        self.world_combo = ttk.Combobox(left_col, values=list(WORLDS_CONFIG.keys()), state="readonly", font=("DejaVu Sans", 10))
        self.world_combo.set(self.current_world)
        self.world_combo.pack(fill="x", pady=(0, 10))
        self.world_combo.bind("<<ComboboxSelected>>", self._on_world_change)

        # Destination Table
        ttk.Label(left_col, text="Destination Table:", font=("DejaVu Sans", 10, "bold")).pack(anchor="w", pady=(4, 2))
        cfg = WORLDS_CONFIG[self.current_world]
        self.table_combo = ttk.Combobox(left_col, values=cfg["tables"], state="readonly", font=("DejaVu Sans", 11))
        self.table_combo.set(cfg["default_table"])
        self.table_combo.pack(fill="x", pady=(0, 10))

        # Order Item Entry
        ttk.Label(left_col, text="Order Item / Specialty:", font=("DejaVu Sans", 10, "bold")).pack(anchor="w", pady=(4, 2))
        self.item_entry = tk.Entry(left_col, font=("DejaVu Sans", 11), bg="#2b2d42", fg="#ffffff",
                                   insertbackground="#00adb5", relief="flat", highlightthickness=1,
                                   highlightbackground="#4b5563", highlightcolor="#00adb5")
        self.item_entry.insert(0, cfg["default_item"])
        self.item_entry.pack(fill="x", ipady=4, pady=(0, 8))

        # Quick preset buttons
        ttk.Label(left_col, text="Menu Recommendations:", font=("DejaVu Sans", 9, "bold"), foreground="#94a3b8").pack(anchor="w", pady=(0, 2))
        self.preset_frame = tk.Frame(left_col, bg="#1e1e24")
        self.preset_frame.pack(fill="x", pady=2)
        self.preset_frame.columnconfigure(0, weight=1)
        self.preset_frame.columnconfigure(1, weight=1)
        self._build_preset_buttons()

        # Dispatch Button
        dispatch_btn = ttk.Button(left_col, text="🚀 Dispatch Order to Robot", command=self._on_dispatch)
        dispatch_btn.pack(fill="x", pady=(14, 8))

        # Bottom Left: Auto-Docking Controls
        dock_box = ttk.LabelFrame(left_col, text=" ⚓ Auto-Docking & Resting Station ", padding=10)
        dock_box.pack(fill="x", side="bottom", pady=(8, 0))

        dock_btn_frame = tk.Frame(dock_box, bg="#1e1e24")
        dock_btn_frame.pack(fill="x", pady=(2, 2))

        manual_dock_btn = tk.Button(
            dock_btn_frame, text="⚓ Return-To-Dock", bg="#e76f51", fg="#ffffff",
            activebackground="#d45d3e", activeforeground="#ffffff",
            font=("DejaVu Sans", 10, "bold"), relief="flat", pady=8,
            command=lambda: self.bridge.trigger_dock("manual_ui")
        )
        manual_dock_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))

        stop_dock_btn = tk.Button(
            dock_btn_frame, text="🛑 Stop Docking", bg="#e63946", fg="#ffffff",
            activebackground="#ba181b", activeforeground="#ffffff",
            font=("DejaVu Sans", 10, "bold"), relief="flat", pady=8,
            command=self._on_stop_dock
        )
        stop_dock_btn.pack(side="right", fill="x", expand=True, padx=(4, 0))

        # Right Column: Live Task Queue & Monitoring
        right_col = ttk.LabelFrame(content_frame, text=" 📋 Live Delivery Queue & Monitoring ", padding=12)
        right_col.pack(side="right", fill="both", expand=True, padx=(6, 0))

        # Current Task Display Box
        tk.Label(right_col, text="Current Active Delivery:", font=("DejaVu Sans", 10, "bold"), fg="#00adb5", bg="#1e1e24").pack(anchor="w")
        self.active_task_card = tk.Label(
            right_col, text="No active task (Robot Idle)", font=("DejaVu Sans", 10),
            fg="#f1faee", bg="#2b2d42", relief="groove", padx=10, pady=10, justify="left", anchor="w"
        )
        self.active_task_card.pack(fill="x", pady=(4, 12))

        # Pending Queue Title
        tk.Label(right_col, text="Pending Tasks (FIFO Dispatch):", font=("DejaVu Sans", 10, "bold"),
                 fg="#e0e0e0", bg="#1e1e24").pack(anchor="w", pady=(0, 2))

        # Queue Listbox with Scrollbar
        list_frame = tk.Frame(right_col, bg="#1e1e24")
        list_frame.pack(fill="both", expand=True, pady=(0, 8))

        self.queue_listbox = tk.Listbox(
            list_frame, font=("DejaVu Sans Mono", 10), bg="#2b2d42", fg="#ffffff",
            selectbackground="#00adb5", selectforeground="#ffffff",
            relief="flat", highlightthickness=1, highlightbackground="#393e46",
            highlightcolor="#00adb5", activestyle="none"
        )
        self.queue_listbox.pack(side="left", fill="both", expand=True)
        self.queue_listbox.bind('<<ListboxSelect>>', self._on_queue_select)

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.queue_listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.queue_listbox.config(yscrollcommand=scrollbar.set)

        # Selected Task Operations Box
        edit_box = ttk.LabelFrame(right_col, text=" ✏️ Modify / Delete Selected Task ", padding=8)
        edit_box.pack(fill="x", pady=(0, 10))

        self.selected_task_lbl = tk.Label(
            edit_box, text="Click a queued task above to Edit or Delete",
            font=("DejaVu Sans", 9, "italic"), fg="#94a3b8", bg="#1e1e24"
        )
        self.selected_task_lbl.pack(anchor="w", pady=(0, 6))

        action_btn_frame = tk.Frame(edit_box, bg="#1e1e24")
        action_btn_frame.pack(fill="x")

        self.modify_btn = tk.Button(
            action_btn_frame, text="💾 Save Edit", bg="#4b5563", fg="#ffffff",
            font=("DejaVu Sans", 9, "bold"), relief="flat", state="disabled",
            padx=10, pady=6, command=self._on_modify_selected
        )
        self.modify_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.delete_btn = tk.Button(
            action_btn_frame, text="🗑️ Delete Task", bg="#4b5563", fg="#ffffff",
            font=("DejaVu Sans", 9, "bold"), relief="flat", state="disabled",
            padx=10, pady=6, command=self._on_delete_selected
        )
        self.delete_btn.pack(side="left", fill="x", expand=True, padx=4)

        self.clear_sel_btn = tk.Button(
            action_btn_frame, text="✖ Cancel", bg="#374151", fg="#ffffff",
            font=("DejaVu Sans", 9), relief="flat", state="disabled",
            padx=8, pady=6, command=self._on_clear_selection
        )
        self.clear_sel_btn.pack(side="right", fill="x", expand=True, padx=(4, 0))

        # Bottom Statistics Bar
        stats_frame = tk.Frame(right_col, bg="#1e1e24")
        stats_frame.pack(fill="x")
        self.completed_lbl = tk.Label(stats_frame, text="Completed Deliveries: 0", font=("DejaVu Sans", 10, "bold"),
                                      fg="#4ade80", bg="#1e1e24")
        self.completed_lbl.pack(side="left")

        self.queue_len_lbl = tk.Label(stats_frame, text="Queued: 0", font=("DejaVu Sans", 10, "bold"),
                                      fg="#f4a261", bg="#1e1e24")
        self.queue_len_lbl.pack(side="right")

    def _build_preset_buttons(self):
        for btn in self.preset_buttons:
            btn.destroy()
        self.preset_buttons.clear()

        presets = WORLDS_CONFIG[self.current_world]["presets"]
        for i, item in enumerate(presets):
            r, c = divmod(i, 2)
            btn = tk.Button(
                self.preset_frame, text=item, bg="#2b2d42", fg="#e0e0e0",
                activebackground="#3d405b", activeforeground="#ffffff",
                font=("DejaVu Sans", 9), relief="flat", padx=6, pady=4,
                command=lambda it=item: self._select_preset(it)
            )
            btn.grid(row=r, column=c, sticky="ew", padx=2, pady=2)
            self.preset_buttons.append(btn)

    def _on_world_change(self, event=None):
        selected_world = self.world_combo.get()
        if selected_world in WORLDS_CONFIG:
            self.current_world = selected_world
            cfg = WORLDS_CONFIG[selected_world]
            self.title_lbl.config(text=f"🤖 CSTAM Control Dashboard: {cfg['title']}")
            self.table_combo.config(values=cfg["tables"])
            self.table_combo.set(cfg["default_table"])
            self.item_entry.delete(0, tk.END)
            self.item_entry.insert(0, cfg["default_item"])
            self._build_preset_buttons()
            self._on_clear_selection()

    def _select_preset(self, item_name: str):
        self.item_entry.delete(0, tk.END)
        self.item_entry.insert(0, item_name)

    def _on_dispatch(self):
        target = self.table_combo.get().strip()
        item = self.item_entry.get().strip()
        if not target:
            messagebox.showwarning("Input Required", "Please select a target table.")
            return
        if not item:
            item = "Standard Meal Delivery"

        self.bridge.dispatch_order(target, item)

    def _on_queue_select(self, event=None):
        selection = self.queue_listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        queue = self.bridge.latest_status.get("pending_tasks", [])
        if 0 <= idx < len(queue):
            task = queue[idx]
            self.selected_task_id = task.get("id")
            target = task.get("target", "")
            item = task.get("item", "")

            # Auto-populate input fields
            cfg_tables = WORLDS_CONFIG[self.current_world]["tables"]
            if target in cfg_tables:
                self.table_combo.set(target)
            self.item_entry.delete(0, tk.END)
            self.item_entry.insert(0, item)

            self._update_selection_ui(task)

    def _update_selection_ui(self, task=None):
        if self.selected_task_id:
            tid = self.selected_task_id
            self.selected_task_lbl.config(
                text=f"Selected: [{tid}] (Edit Table/Item on left, then click Save)",
                fg="#38bdf8"
            )
            self.modify_btn.config(state="normal", bg="#00adb5")
            self.delete_btn.config(state="normal", bg="#e63946")
            self.clear_sel_btn.config(state="normal", bg="#4b5563")
        else:
            self.selected_task_lbl.config(
                text="Click a queued task above to Edit or Delete",
                fg="#94a3b8"
            )
            self.modify_btn.config(state="disabled", bg="#4b5563")
            self.delete_btn.config(state="disabled", bg="#4b5563")
            self.clear_sel_btn.config(state="disabled", bg="#374151")

    def _on_modify_selected(self):
        if not self.selected_task_id:
            return
        new_target = self.table_combo.get().strip()
        new_item = self.item_entry.get().strip()
        if not new_target:
            messagebox.showwarning("Validation Error", "Please select a valid destination table.")
            return
        if not new_item:
            new_item = "Standard Meal Delivery"

        self.bridge.modify_task(self.selected_task_id, new_target, new_item)

    def _on_delete_selected(self):
        if not self.selected_task_id:
            return
        tid = self.selected_task_id
        self.bridge.delete_task(tid)
        self._on_clear_selection()

    def _on_clear_selection(self):
        self.selected_task_id = None
        self.queue_listbox.selection_clear(0, tk.END)
        self._update_selection_ui()

    def _on_stop_dock(self):
        self.bridge.stop_docking()

    def _update_loop(self):
        status = self.bridge.latest_status
        raw_state = status.get("robot_state", "idle")
        state = raw_state.upper()

        # Update Badge Color
        badge_colors = {
            "IDLE": ("#457b9d", "#ffffff"),
            "NAVIGATING": ("#f59e0b", "#000000"),
            "AT_TABLE": ("#10b981", "#ffffff"),
            "DOCKING": ("#ec4899", "#ffffff"),
            "DOCKED": ("#10b981", "#ffffff"),
            "RESTING": ("#06b6d4", "#ffffff")
        }
        bg_col, fg_col = badge_colors.get(state, ("#6b7280", "#ffffff"))
        self.state_badge.config(text=state, bg=bg_col, fg=fg_col)

        # Dock Badge
        if self.bridge.is_docked or state in ["DOCKED", "RESTING"]:
            self.dock_badge.config(text="DOCKED (RESTING)", bg="#10b981", fg="#ffffff")
        elif state == "DOCKING":
            self.dock_badge.config(text="RETURNING TO DOCK", bg="#ec4899", fg="#ffffff")
        else:
            self.dock_badge.config(text="UNDOCKED", bg="#6c757d", fg="#ffffff")

        # Active Task Card
        cur = status.get("current_task")
        if cur:
            tid = cur.get("id", "TASK")
            target = cur.get("target", "Destination")
            item = cur.get("item", "Item")
            st_text = cur.get("status", "in_progress")
            self.active_task_card.config(
                text=f"[{tid}] En Route to {target}\n"
                     f"Item: {item}\n"
                     f"Phase: {st_text.upper()}",
                fg="#38bdf8", bg="#1f2937"
            )
        else:
            if state in ["DOCKED", "RESTING"]:
                self.active_task_card.config(
                    text="Robot is resting at Dock Station.\nAwaiting new delivery orders.",
                    fg="#4ade80", bg="#1f2937"
                )
            elif state == "DOCKING":
                self.active_task_card.config(
                    text="Autonomous Return-To-Dock active.\nRouting through aisle to docking station.",
                    fg="#f472b6", bg="#1f2937"
                )
            else:
                self.active_task_card.config(
                    text="Robot is IDLE and awaiting orders.\nSelect a table on the left to dispatch.",
                    fg="#f1faee", bg="#2b2d42"
                )

        # Pending Queue Listbox Update
        queue = status.get("pending_tasks", [])
        completed = status.get("completed_count", 0)

        queue_sig = tuple((t.get("id"), t.get("target"), t.get("item")) for t in queue)
        if queue_sig != self._cached_queue_sig:
            self._cached_queue_sig = queue_sig
            self.queue_listbox.delete(0, tk.END)
            for idx, t in enumerate(queue):
                tid = t.get("id", f"T-{idx}")
                tgt = t.get("target", "Table")
                itm = t.get("item", "Meal")
                self.queue_listbox.insert(tk.END, f"{idx+1:02d}. [{tid}] {tgt:<14} | {itm}")

            if self.selected_task_id:
                reselected = False
                for idx, t in enumerate(queue):
                    if t.get("id") == self.selected_task_id:
                        self.queue_listbox.selection_set(idx)
                        reselected = True
                        break
                if not reselected:
                    self.selected_task_id = None
                    self._update_selection_ui()

        self.completed_lbl.config(text=f"Completed Deliveries: {completed}")
        self.queue_len_lbl.config(text=f"Queued: {len(queue)}")

        self.root.after(300, self._update_loop)


def run_cli_mode(bridge: Ros2DeliveryBridge, initial_world: str):
    current_world = initial_world
    print("=" * 68)
    print(f"  CSTAM: Interactive Waiter Robot Delivery CLI Simulator")
    print(f"  Active World: {current_world}")
    print("=" * 68)
    while True:
        try:
            cfg = WORLDS_CONFIG[current_world]
            print(f"\n[Environment: {cfg['title']}]")
            print("Options:")
            print("  1. Dispatch Delivery Order")
            print("  2. View Delivery Queue & Live Status")
            print("  3. Manual Return-to-Dock Command")
            print("  4. Stop / Cancel Docking")
            print("  5. Modify Queued Task (Table or Item)")
            print("  6. Delete Queued Task")
            print(f"  7. Switch Environment (Currently: {cfg['short_name']})")
            print("  8. Exit")
            choice = input("Select option (1-8): ").strip()

            if choice == "1":
                tables_str = ", ".join(cfg["tables"][:12])
                print(f"\nAvailable Tables: {tables_str}...")
                table = input(f"Enter target table [default: {cfg['default_table']}]: ").strip() or cfg["default_table"]
                item = input(f"Enter meal item [default: {cfg['default_item']}]: ").strip() or cfg["default_item"]
                bridge.dispatch_order(table, item)
                print(f"✔ Order dispatched for {table}: {item}")

            elif choice == "2":
                st = bridge.latest_status
                print("\n--- Live Robot Status ---")
                print(f"  State: {st.get('robot_state')}")
                print(f"  Current Task: {st.get('current_task')}")
                print(f"  Queue Length: {st.get('queue_length')}")
                print(f"  Completed: {st.get('completed_count')}")
                tasks = st.get('pending_tasks', [])
                if tasks:
                    print("  Pending Queue:")
                    for idx, t in enumerate(tasks):
                        print(f"    {idx+1}. [{t.get('id')}] {t.get('target')} - {t.get('item')}")
                else:
                    print("  Queue is empty.")

            elif choice == "3":
                bridge.trigger_dock("cli_manual")
                print("✔ Return to dock command broadcasted.")

            elif choice == "4":
                bridge.stop_docking()
                print("✔ Docking stopped / cancelled.")

            elif choice == "5":
                tasks = bridge.latest_status.get('pending_tasks', [])
                if not tasks:
                    print("Pending queue is empty.")
                    continue
                print("Pending Tasks:")
                for idx, t in enumerate(tasks):
                    print(f"  [{t.get('id')}] {t.get('target')} - {t.get('item')}")
                tid = input("Enter task ID to modify (e.g. TASK-0001): ").strip()
                new_t = input("Enter new target table (leave empty to keep current): ").strip()
                new_i = input("Enter new item description (leave empty to keep current): ").strip()
                bridge.modify_task(tid, new_t, new_i)
                print(f"✔ Modification sent for {tid}.")

            elif choice == "6":
                tasks = bridge.latest_status.get('pending_tasks', [])
                if not tasks:
                    print("Pending queue is empty.")
                    continue
                print("Pending Tasks:")
                for idx, t in enumerate(tasks):
                    print(f"  [{t.get('id')}] {t.get('target')} - {t.get('item')}")
                tid = input("Enter task ID to delete: ").strip()
                bridge.delete_task(tid)
                print(f"✔ Deletion sent for {tid}.")

            elif choice == "7":
                world_keys = list(WORLDS_CONFIG.keys())
                print("\nAvailable Worlds:")
                for i, k in enumerate(world_keys):
                    print(f"  {i+1}. {k}")
                w_choice = input(f"Select world (1-{len(world_keys)}): ").strip()
                if w_choice.isdigit() and 1 <= int(w_choice) <= len(world_keys):
                    current_world = world_keys[int(w_choice) - 1]
                    print(f"✔ Switched environment to {current_world}")

            elif choice == "8":
                print("Exiting.")
                break
        except (KeyboardInterrupt, EOFError):
            break


def main():
    initial_world = detect_initial_world()
    bridge = Ros2DeliveryBridge()

    if "--cli" in sys.argv or not HAVE_TKINTER or not os.environ.get("DISPLAY"):
        print(f"[Simulator] Launching in interactive CLI mode for {initial_world}...")
        run_cli_mode(bridge, initial_world)
    else:
        root = tk.Tk()
        app = DeliverySimulatorGUI(root, bridge, initial_world)
        root.mainloop()


if __name__ == '__main__':
    main()
