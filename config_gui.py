"""Tkinter visual profile configurator with live controller feedback."""

from __future__ import annotations

import os
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Callable, Optional

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "hide"

import pygame

from config_models import (
    Action,
    AnalogScrollAction,
    AxisMapping,
    ButtonMapping,
    CapsWriterAction,
    DpadAxesMapping,
    HardwareMapping,
    HatMapping,
    KeyAction,
    ModifierAction,
    MouseClickAction,
    MouseMoveAction,
    NoAction,
    Profile,
    ScrollAction,
)
from profile_manager import load_profile, save_profile


# ---------------------------------------------------------------------------
# Layout constants for the virtual controller canvas
# ---------------------------------------------------------------------------

CANVAS_W = 600
CANVAS_H = 360
BTN_R = 22
STICK_R = 32
DPAD_W = 22
DPAD_H = 28

# GUI input key -> (center x, center y, shape, label)
BUTTON_SHAPES: dict[str, tuple[float, float, str, str]] = {
    "LT": (120, 40, "bar-v", "LT"),
    "RT": (CANVAS_W - 120, 40, "bar-v", "RT"),
    "LB": (120, 95, "pill", "LB"),
    "RB": (CANVAS_W - 120, 95, "pill", "RB"),
    "DPAD_UP": (110, 160, "rect", "↑"),
    "DPAD_DOWN": (110, 220, "rect", "↓"),
    "DPAD_LEFT": (80, 190, "rect", "←"),
    "DPAD_RIGHT": (140, 190, "rect", "→"),
    "LEFT_STICK": (180, 260, "circle", "LS"),
    "RIGHT_STICK": (CANVAS_W - 180, 260, "circle", "RS"),
    "A": (CANVAS_W - 90, 230, "circle", "A"),
    "B": (CANVAS_W - 60, 200, "circle", "B"),
    "X": (CANVAS_W - 120, 200, "circle", "X"),
    "Y": (CANVAS_W - 90, 170, "circle", "Y"),
    "MENU": (CANVAS_W / 2 - 35, 190, "pill", "MENU"),
    "HOME": (CANVAS_W / 2 + 35, 190, "pill", "HOME"),
}

# Map GUI input keys to the logical input names stored in the profile
GUI_TO_PROFILE_INPUT = {
    "DPAD_UP": "UP",
    "DPAD_DOWN": "DOWN",
    "DPAD_LEFT": "LEFT",
    "DPAD_RIGHT": "RIGHT",
}

ACTION_TYPE_LABELS = {
    "none": "无",
    "mouse_click": "鼠标点击",
    "mouse_move": "鼠标移动",
    "scroll": "滚轮",
    "analog_scroll": "模拟滚轮 (扳机)",
    "key": "键盘按键",
    "modifier": "修饰键 / 切层",
    "caps_writer": "语音对讲机",
}

MOUSE_BUTTONS = ["left", "right", "middle"]
MODIFIER_KEYS = ["cmd", "alt", "ctrl", "shift"]


# ---------------------------------------------------------------------------
# Background controller poller
# ---------------------------------------------------------------------------

class ControllerPoller(threading.Thread):
    """Reads controller state in a background thread and notifies the GUI.

    NOTE: On macOS pygame.event.pump() must run on the main thread, so we read
    joystick state directly via joy.get_*() instead of using the event queue.
    """

    def __init__(self, hardware: HardwareMapping, callback: Callable[[dict[str, Any]], None]):
        super().__init__(daemon=True)
        self.hardware = hardware
        self.callback = callback
        self.running = True
        self._lock = threading.Lock()
        self._latest_state: Optional[dict[str, Any]] = None

    def get_state(self) -> Optional[dict[str, Any]]:
        with self._lock:
            return self._latest_state

    def stop(self) -> None:
        self.running = False

    def _build_state(self, joy: pygame.joystick.Joystick) -> dict[str, Any]:
        num_buttons = joy.get_numbuttons()
        num_axes = joy.get_numaxes()
        num_hats = joy.get_numhats()

        buttons: dict[str, bool] = {}
        axes: dict[str, float] = {}

        for logical_name, hw in self.hardware.inputs.items():
            if hw is None:
                continue
            if isinstance(hw, ButtonMapping):
                if hw.index < num_buttons:
                    buttons[logical_name] = bool(joy.get_button(hw.index))
            elif isinstance(hw, AxisMapping):
                if hw.index < num_axes:
                    value = joy.get_axis(hw.index)
                    if logical_name in ("ly", "ry"):
                        value *= -1
                    axes[logical_name] = value

        # D-pad aliases
        for direction in ("UP", "DOWN", "LEFT", "RIGHT"):
            buttons[direction] = False

        dpad = self.hardware.inputs.get("dpad")
        if isinstance(dpad, DpadAxesMapping):
            if dpad.x_axis < num_axes:
                val = joy.get_axis(dpad.x_axis)
                if val < -0.5:
                    buttons["LEFT"] = True
                if val > 0.5:
                    buttons["RIGHT"] = True
            if dpad.y_axis < num_axes:
                val = joy.get_axis(dpad.y_axis)
                if val < -0.5:
                    buttons["UP"] = True
                if val > 0.5:
                    buttons["DOWN"] = True
        elif isinstance(dpad, HatMapping):
            if dpad.index < num_hats:
                hx, hy = joy.get_hat(dpad.index)
                if hy == 1:
                    buttons["UP"] = True
                if hy == -1:
                    buttons["DOWN"] = True
                if hx == -1:
                    buttons["LEFT"] = True
                if hx == 1:
                    buttons["RIGHT"] = True

        # Merge explicit DPAD_* button mappings into directional aliases
        if buttons.get("DPAD_UP"):
            buttons["UP"] = True
        if buttons.get("DPAD_DOWN"):
            buttons["DOWN"] = True
        if buttons.get("DPAD_LEFT"):
            buttons["LEFT"] = True
        if buttons.get("DPAD_RIGHT"):
            buttons["RIGHT"] = True

        lt_val = (axes.get("lt", -1.0) + 1.0) / 2.0
        rt_val = (axes.get("rt", -1.0) + 1.0) / 2.0

        return {
            "buttons": buttons,
            "lt": lt_val,
            "rt": rt_val,
            "lx": axes.get("lx", 0.0),
            "ly": axes.get("ly", 0.0),
            "rx": axes.get("rx", 0.0),
            "ry": axes.get("ry", 0.0),
        }

    def run(self) -> None:
        # Use only joystick module; full pygame.init() would set SDLApplication
        # delegate on macOS and break tkinter in the main thread.
        pygame.joystick.init()
        joy: Optional[pygame.joystick.Joystick] = None
        try:
            while self.running:
                if joy is None:
                    if pygame.joystick.get_count() == 0:
                        time.sleep(0.2)
                        continue
                    joy = pygame.joystick.Joystick(0)
                    joy.init()

                try:
                    state = self._build_state(joy)
                except pygame.error:
                    joy = None
                    continue

                with self._lock:
                    self._latest_state = state
                try:
                    self.callback(state)
                except Exception:
                    pass

                time.sleep(0.01)
        finally:
            pygame.joystick.quit()


# ---------------------------------------------------------------------------
# Main configurator application
# ---------------------------------------------------------------------------

class ConfigApp:
    def __init__(self, profile: Profile):
        self.profile = profile
        self.current_layer = "default"
        self.selected_input: Optional[str] = None
        self.latest_state: Optional[dict[str, Any]] = None

        self.root = tk.Tk()
        self.root.title(f"Controller Companion Config - {profile.name}")
        self.root.geometry("1100x720")
        self.root.minsize(900, 600)

        self._build_ui()
        self._start_poller()
        self._refresh_canvas()

    def _build_ui(self) -> None:
        # Top toolbar
        toolbar = tk.Frame(self.root)
        toolbar.pack(fill=tk.X, padx=10, pady=5)

        tk.Label(toolbar, text="层 (Layer):").pack(side=tk.LEFT)
        self.layer_frame = tk.Frame(toolbar)
        self.layer_frame.pack(side=tk.LEFT, padx=(5, 20))
        self._render_layer_tabs()

        tk.Button(toolbar, text="保存配置", command=self._save_profile).pack(side=tk.RIGHT)
        tk.Button(toolbar, text="刷新手柄", command=self._restart_poller).pack(side=tk.RIGHT, padx=5)

        # Main content
        content = tk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        content.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Left: Canvas
        left_frame = tk.Frame(content)
        self.canvas = tk.Canvas(
            left_frame, width=CANVAS_W, height=CANVAS_H, bg="#2b2b2b", highlightthickness=0
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        content.add(left_frame, minsize=500)

        # Right: Properties panel
        right_frame = tk.Frame(content, width=360)
        right_frame.pack_propagate(False)
        content.add(right_frame, minsize=360)

        tk.Label(
            right_frame, text="按键配置", font=("Helvetica", 14, "bold")
        ).pack(anchor=tk.W, pady=(10, 5))

        self.selected_label = tk.Label(right_frame, text="未选择按键", font=("Helvetica", 12))
        self.selected_label.pack(anchor=tk.W, pady=5)

        tk.Label(right_frame, text="动作类型:").pack(anchor=tk.W)
        self.action_type_var = tk.StringVar(value="none")
        self.action_type_combo = ttk.Combobox(
            right_frame,
            textvariable=self.action_type_var,
            values=list(ACTION_TYPE_LABELS.keys()),
            state="readonly",
        )
        self.action_type_combo.pack(fill=tk.X, pady=2)
        self.action_type_combo.bind("<<ComboboxSelected>>", self._on_action_type_changed)

        # Display readable labels in combobox
        self.action_type_combo["values"] = list(ACTION_TYPE_LABELS.values())

        self.props_frame = tk.Frame(right_frame)
        self.props_frame.pack(fill=tk.X, pady=10)

        self._render_controller_outline()
        self._render_props()

    def _render_layer_tabs(self) -> None:
        for widget in self.layer_frame.winfo_children():
            widget.destroy()

        layer_names = ["default"] + sorted(
            [n for n in self.profile.layers.keys() if n != "default"]
        )
        for name in layer_names:
            btn = tk.Button(
                self.layer_frame,
                text=name,
                relief=tk.SUNKEN if name == self.current_layer else tk.RAISED,
                command=lambda n=name: self._switch_layer(n),
            )
            btn.pack(side=tk.LEFT, padx=2)

    def _switch_layer(self, name: str) -> None:
        self.current_layer = name
        self.selected_input = None
        self._render_layer_tabs()
        self._update_selected_label()
        self._render_props()

    def _profile_input_name(self, gui_key: str) -> str:
        return GUI_TO_PROFILE_INPUT.get(gui_key, gui_key)

    def _gui_input_name(self, profile_input: str) -> Optional[str]:
        for gui_key, prof_key in GUI_TO_PROFILE_INPUT.items():
            if prof_key == profile_input:
                return gui_key
        return profile_input if profile_input in BUTTON_SHAPES else None

    def _render_controller_outline(self) -> None:
        # Body
        self.canvas.create_oval(
            60, 110, CANVAS_W - 60, 330, fill="#3a3a3a", outline="#555555", width=2
        )
        # Handles
        self.canvas.create_oval(40, 130, 120, 280, fill="#3a3a3a", outline="#555555", width=2)
        self.canvas.create_oval(
            CANVAS_W - 120, 130, CANVAS_W - 40, 280, fill="#3a3a3a", outline="#555555", width=2
        )

    def _draw_shape(
        self,
        gui_key: str,
        x: float,
        y: float,
        shape: str,
        label: str,
        active: bool,
        selected: bool,
    ) -> None:
        fill = "#ff5555" if active else ("#5a5a5a" if not selected else "#777777")
        outline = "#ffffff" if selected else "#888888"

        tag = f"btn_{gui_key}"
        if shape == "circle":
            self.canvas.create_oval(
                x - BTN_R,
                y - BTN_R,
                x + BTN_R,
                y + BTN_R,
                fill=fill,
                outline=outline,
                width=2 if selected else 1,
                tags=tag,
            )
        elif shape == "rect":
            self.canvas.create_rectangle(
                x - DPAD_W,
                y - DPAD_H,
                x + DPAD_W,
                y + DPAD_H,
                fill=fill,
                outline=outline,
                width=2 if selected else 1,
                tags=tag,
            )
        elif shape == "pill":
            self.canvas.create_oval(
                x - 30, y - 14, x + 30, y + 14, fill=fill, outline=outline, width=2 if selected else 1, tags=tag
            )
        elif shape == "bar-v":
            # Vertical bar for triggers, fills based on analog value
            h = 60
            val = self._get_trigger_value(gui_key)
            fill_h = int(h * val)
            self.canvas.create_rectangle(
                x - 12, y - h // 2, x + 12, y + h // 2, fill="#333333", outline=outline, tags=tag
            )
            self.canvas.create_rectangle(
                x - 12,
                y + h // 2 - fill_h,
                x + 12,
                y + h // 2,
                fill="#ff5555" if val > 0.1 else "#666666",
                outline="",
                tags=tag,
            )

        self.canvas.create_text(
            x, y, text=label, fill="white", font=("Helvetica", 10, "bold"), tags=tag
        )

    def _get_trigger_value(self, gui_key: str) -> float:
        if self.latest_state is None:
            return 0.0
        axis = gui_key.lower()
        return self.latest_state.get(axis, 0.0)

    def _is_input_active(self, gui_key: str) -> bool:
        if self.latest_state is None:
            return False
        state = self.latest_state
        buttons = state["buttons"]

        if gui_key == "LEFT_STICK":
            return (
                abs(state.get("lx", 0.0)) > 0.3
                or abs(state.get("ly", 0.0)) > 0.3
                or buttons.get("LS", False)
            )
        if gui_key == "RIGHT_STICK":
            return (
                abs(state.get("rx", 0.0)) > 0.3
                or abs(state.get("ry", 0.0)) > 0.3
                or buttons.get("RS", False)
            )
        if gui_key in ("LT", "RT"):
            return self._get_trigger_value(gui_key) > 0.1
        if gui_key.startswith("DPAD_"):
            return buttons.get(GUI_TO_PROFILE_INPUT.get(gui_key, gui_key), False)
        return buttons.get(gui_key, False)

    def _refresh_canvas(self) -> None:
        # Remove old button shapes
        for gui_key in BUTTON_SHAPES:
            self.canvas.delete(f"btn_{gui_key}")

        for gui_key, (x, y, shape, label) in BUTTON_SHAPES.items():
            active = self._is_input_active(gui_key)
            selected = self.selected_input == gui_key
            self._draw_shape(gui_key, x, y, shape, label, active, selected)

        self.root.after(30, self._refresh_canvas)

    def _on_canvas_click(self, event: tk.Event) -> None:
        # Find closest clickable region
        best_key: Optional[str] = None
        best_dist = float("inf")
        for gui_key, (x, y, shape, _label) in BUTTON_SHAPES.items():
            dist = ((event.x - x) ** 2 + (event.y - y) ** 2) ** 0.5
            radius = BTN_R if shape == "circle" else 30
            if shape == "rect":
                radius = max(DPAD_W, DPAD_H)
            if dist < radius and dist < best_dist:
                best_dist = dist
                best_key = gui_key

        if best_key:
            self.selected_input = best_key
            self._update_selected_label()
            self._render_props()

    def _update_selected_label(self) -> None:
        if self.selected_input is None:
            self.selected_label.config(text="未选择按键")
            return
        prof_input = self._profile_input_name(self.selected_input)
        action = self.profile.get_action(self.current_layer, prof_input)
        label = ACTION_TYPE_LABELS.get(action.kind, action.kind)
        self.selected_label.config(text=f"当前: {self.selected_input} ({prof_input}) -> {label}")

    def _render_props(self) -> None:
        for widget in self.props_frame.winfo_children():
            widget.destroy()

        if self.selected_input is None:
            tk.Label(self.props_frame, text="点击左侧手柄按键进行配置").pack(anchor=tk.W)
            return

        prof_input = self._profile_input_name(self.selected_input)
        action = self.profile.get_action(self.current_layer, prof_input)

        # Translate current action kind to readable label
        readable = ACTION_TYPE_LABELS.get(action.kind, "none")
        self.action_type_var.set(readable)

        # Create dynamic fields
        self._props_vars: dict[str, Any] = {}
        self._build_action_fields(action)
        self._apply_button = tk.Button(
            self.props_frame, text="应用", command=self._apply_action
        )
        self._apply_button.pack(anchor=tk.W, pady=(10, 0))

    def _build_action_fields(self, action: Action) -> None:
        kind = action.kind

        if kind == "mouse_click":
            cfg = action if isinstance(action, MouseClickAction) else MouseClickAction()
            self._make_dropdown("鼠标按键", "button", MOUSE_BUTTONS, cfg.button)

        elif kind == "mouse_move":
            cfg = action if isinstance(action, MouseMoveAction) else MouseMoveAction()
            axes = self._infer_stick_axes()
            self._make_readonly("X 轴", "x_axis", axes[0])
            self._make_readonly("Y 轴", "y_axis", axes[1])
            self._make_spinbox("灵敏度", "sensitivity", cfg.sensitivity, 1, 200, 1)
            self._make_spinbox("死区", "deadzone", cfg.deadzone, 0, 1, 0.01)

        elif kind == "scroll":
            cfg = action if isinstance(action, ScrollAction) else ScrollAction()
            self._make_dropdown("方向", "direction", ["向上", "向下"], "向上" if cfg.direction < 0 else "向下")
            self._make_spinbox("速度", "speed", cfg.speed, 1, 100, 1)
            self._make_spinbox("首次延迟", "initial_delay", cfg.initial_delay, 0, 2, 0.05)
            self._make_spinbox("重复间隔", "repeat_rate", cfg.repeat_rate, 0.01, 1, 0.01)

        elif kind == "analog_scroll":
            cfg = action if isinstance(action, AnalogScrollAction) else AnalogScrollAction()
            self._make_readonly("轴", "axis", self.selected_input.lower())
            self._make_spinbox("阈值", "threshold", cfg.threshold, 0, 1, 0.01)
            self._make_dropdown("方向", "direction", ["向上", "向下"], "向上" if cfg.direction < 0 else "向下")
            self._make_spinbox("速度", "speed", cfg.speed, 1, 100, 1)
            self._make_spinbox("首次延迟", "initial_delay", cfg.initial_delay, 0, 2, 0.05)
            self._make_spinbox("重复间隔", "repeat_rate", cfg.repeat_rate, 0.01, 1, 0.01)

        elif kind == "key":
            cfg = action if isinstance(action, KeyAction) else KeyAction()
            self._make_entry("按键", "key", cfg.key)
            self._make_multichoice("修饰键", "modifiers", MODIFIER_KEYS, cfg.modifiers)

        elif kind == "modifier":
            cfg = action if isinstance(action, ModifierAction) else ModifierAction()
            self._make_entry("目标层名", "target_layer", cfg.target_layer)
            tk.Label(
                self.props_frame,
                text="保存后会自动创建对应层标签页",
                fg="gray",
            ).pack(anchor=tk.W)

        elif kind == "caps_writer":
            tk.Label(self.props_frame, text="按住开始录音，松开发送识别").pack(anchor=tk.W)

        else:  # none
            tk.Label(self.props_frame, text="该按键在当前层不执行任何动作").pack(anchor=tk.W)

    def _infer_stick_axes(self) -> tuple[str, str]:
        if self.selected_input == "RIGHT_STICK":
            return ("rx", "ry")
        return ("lx", "ly")

    def _make_label(self, text: str) -> None:
        tk.Label(self.props_frame, text=text).pack(anchor=tk.W, pady=(5, 0))

    def _make_entry(self, label: str, key: str, default: str) -> None:
        self._make_label(label)
        var = tk.StringVar(value=str(default))
        self._props_vars[key] = var
        tk.Entry(self.props_frame, textvariable=var).pack(fill=tk.X)

    def _make_readonly(self, label: str, key: str, value: str) -> None:
        self._make_label(label)
        tk.Label(self.props_frame, text=str(value)).pack(anchor=tk.W)
        self._props_vars[key] = value

    def _make_dropdown(self, label: str, key: str, options: list[str], default: str) -> None:
        self._make_label(label)
        var = tk.StringVar(value=default)
        self._props_vars[key] = var
        ttk.Combobox(
            self.props_frame, textvariable=var, values=options, state="readonly"
        ).pack(fill=tk.X)

    def _make_spinbox(
        self, label: str, key: str, default: float, min_val: float, max_val: float, step: float
    ) -> None:
        self._make_label(label)
        var = tk.DoubleVar(value=default)
        self._props_vars[key] = var
        tk.Spinbox(
            self.props_frame,
            from_=min_val,
            to=max_val,
            increment=step,
            textvariable=var,
        ).pack(fill=tk.X)

    def _make_multichoice(self, label: str, key: str, options: list[str], selected: list[str]) -> None:
        self._make_label(label)
        frame = tk.Frame(self.props_frame)
        frame.pack(fill=tk.X)
        vars_dict: dict[str, tk.BooleanVar] = {}
        for opt in options:
            var = tk.BooleanVar(value=opt in selected)
            vars_dict[opt] = var
            tk.Checkbutton(frame, text=opt, variable=var).pack(side=tk.LEFT)
        self._props_vars[key] = vars_dict

    def _on_action_type_changed(self, _event: tk.Event) -> None:
        readable = self.action_type_var.get()
        kind = next(k for k, v in ACTION_TYPE_LABELS.items() if v == readable)

        # Build a default action of the selected kind
        default_action = self._default_action_for_kind(kind)
        self._render_props_with_action(default_action)

    def _render_props_with_action(self, action: Action) -> None:
        for widget in self.props_frame.winfo_children():
            widget.destroy()
        self._props_vars = {}
        self._build_action_fields(action)
        self._apply_button = tk.Button(
            self.props_frame, text="应用", command=self._apply_action
        )
        self._apply_button.pack(anchor=tk.W, pady=(10, 0))

    def _default_action_for_kind(self, kind: str) -> Action:
        if kind == "mouse_click":
            return MouseClickAction()
        if kind == "mouse_move":
            axes = self._infer_stick_axes()
            return MouseMoveAction(x_axis=axes[0], y_axis=axes[1])
        if kind == "scroll":
            return ScrollAction()
        if kind == "analog_scroll":
            return AnalogScrollAction(axis=self.selected_input.lower() if self.selected_input else "lt")
        if kind == "key":
            return KeyAction()
        if kind == "modifier":
            return ModifierAction(target_layer=f"layer_{self.selected_input}")
        if kind == "caps_writer":
            return CapsWriterAction()
        return NoAction()

    def _apply_action(self) -> None:
        if self.selected_input is None:
            return

        readable = self.action_type_var.get()
        kind = next(k for k, v in ACTION_TYPE_LABELS.items() if v == readable)
        prof_input = self._profile_input_name(self.selected_input)

        action: Action = NoAction()

        if kind == "mouse_click":
            action = MouseClickAction(button=self._props_vars["button"].get())

        elif kind == "mouse_move":
            axes = self._infer_stick_axes()
            action = MouseMoveAction(
                x_axis=axes[0],
                y_axis=axes[1],
                sensitivity=float(self._props_vars["sensitivity"].get()),
                deadzone=float(self._props_vars["deadzone"].get()),
            )

        elif kind == "scroll":
            direction = -1 if self._props_vars["direction"].get() == "向上" else 1
            action = ScrollAction(
                direction=direction,
                speed=int(self._props_vars["speed"].get()),
                initial_delay=float(self._props_vars["initial_delay"].get()),
                repeat_rate=float(self._props_vars["repeat_rate"].get()),
            )

        elif kind == "analog_scroll":
            direction = -1 if self._props_vars["direction"].get() == "向上" else 1
            action = AnalogScrollAction(
                axis=self._props_vars["axis"],
                threshold=float(self._props_vars["threshold"].get()),
                direction=direction,
                speed=int(self._props_vars["speed"].get()),
                initial_delay=float(self._props_vars["initial_delay"].get()),
                repeat_rate=float(self._props_vars["repeat_rate"].get()),
            )

        elif kind == "key":
            mods = [k for k, v in self._props_vars["modifiers"].items() if v.get()]
            action = KeyAction(key=self._props_vars["key"].get(), modifiers=mods)

        elif kind == "modifier":
            target = self._props_vars["target_layer"].get()
            action = ModifierAction(target_layer=target)
            # Ensure layer exists
            self.profile.get_or_create_layer(target)
            self._render_layer_tabs()

        elif kind == "caps_writer":
            action = CapsWriterAction()

        self.profile.set_action(self.current_layer, prof_input, action)
        self._update_selected_label()
        self._render_props()

    def _save_profile(self) -> None:
        try:
            path = save_profile(self.profile)
            messagebox.showinfo("保存成功", f"配置已保存到:\n{path}")
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    def _start_poller(self) -> None:
        self.poller = ControllerPoller(
            self.profile.hardware, self._on_state_update
        )
        self.poller.start()

    def _restart_poller(self) -> None:
        if hasattr(self, "poller"):
            self.poller.stop()
        self._start_poller()

    def _on_state_update(self, state: dict[str, Any]) -> None:
        self.latest_state = state

    def run(self) -> None:
        self.root.mainloop()
        if hasattr(self, "poller"):
            self.poller.stop()


def _detect_controller_name() -> Optional[str]:
    """Briefly initialize pygame joystick to detect the first connected controller name."""
    pygame.joystick.init()
    try:
        for _ in range(50):
            if pygame.joystick.get_count() > 0:
                break
            time.sleep(0.1)
        if pygame.joystick.get_count() == 0:
            return None
        joy = pygame.joystick.Joystick(0)
        joy.init()
        return joy.get_name()
    finally:
        pygame.joystick.quit()


def run_config_gui(controller_name: Optional[str] = None) -> None:
    """Launch the configuration GUI."""
    if controller_name is None:
        controller_name = _detect_controller_name()
        if controller_name is None:
            messagebox.showerror("未检测到手柄", "请连接手柄后重试。")
            return

    profile = load_profile(controller_name)
    app = ConfigApp(profile)
    app.run()


if __name__ == "__main__":
    run_config_gui()
