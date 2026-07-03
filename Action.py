"""Runtime actions and profile runner for the controller companion."""

from __future__ import annotations

import subprocess
import time
from typing import Any, Optional

from pynput.keyboard import Key
from pynput.mouse import Button

from config_models import (
    Action as ActionConfig,
    AnalogScrollAction,
    CapsWriterAction,
    KeyAction,
    ModifierAction,
    MouseClickAction,
    MouseMoveAction,
    Profile,
    ScrollAction,
)

# ---------------------------------------------------------------------------
# Platform helpers
# ---------------------------------------------------------------------------

try:
    import Quartz
    _QUARTZ = True
except Exception:
    _QUARTZ = False


def _get_virtual_screen_bounds() -> tuple[int, int, int, int]:
    """Get the union of all active displays. Falls back to the main display."""
    if not _QUARTZ:
        return 0, 0, 1920, 1080

    max_displays = 32
    error, display_ids, count = Quartz.CGGetActiveDisplayList(max_displays, None, None)
    if error != 0 or count == 0:
        main = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID())
        return (
            int(main.origin.x),
            int(main.origin.y),
            int(main.origin.x + main.size.width),
            int(main.origin.y + main.size.height),
        )

    min_x = float("inf")
    min_y = float("inf")
    max_x = float("-inf")
    max_y = float("-inf")
    for display_id in display_ids:
        bounds = Quartz.CGDisplayBounds(display_id)
        min_x = min(min_x, bounds.origin.x)
        min_y = min(min_y, bounds.origin.y)
        max_x = max(max_x, bounds.origin.x + bounds.size.width)
        max_y = max(max_y, bounds.origin.y + bounds.size.height)

    return int(min_x), int(min_y), int(max_x), int(max_y)


class ScreenBounds:
    """Lazy, refreshable screen bounds cache."""

    def __init__(self) -> None:
        self._bounds: Optional[tuple[int, int, int, int]] = None
        self._last_update = 0.0

    def get(self, ttl: float = 5.0) -> tuple[int, int, int, int]:
        now = time.time()
        if self._bounds is None or now - self._last_update > ttl:
            self._bounds = _get_virtual_screen_bounds()
            self._last_update = now
        return self._bounds


SCREEN_BOUNDS = ScreenBounds()


# ---------------------------------------------------------------------------
# Key / Button resolution caches
# ---------------------------------------------------------------------------

_KEY_CACHE: dict[str, Key | str] = {}
_BUTTON_CACHE: dict[str, Button] = {}


def resolve_key(name: str) -> Key | str:
    if name not in _KEY_CACHE:
        key = getattr(Key, name, None)
        _KEY_CACHE[name] = key if key is not None else name
    return _KEY_CACHE[name]


def resolve_mouse_button(name: str) -> Button:
    if name not in _BUTTON_CACHE:
        btn = getattr(Button, name, None)
        _BUTTON_CACHE[name] = btn if btn is not None else Button.left
    return _BUTTON_CACHE[name]


# ---------------------------------------------------------------------------
# Action runtime base class
# ---------------------------------------------------------------------------

class RuntimeAction:
    def update(
        self,
        state: dict[str, Any],
        last_state: Optional[dict[str, Any]],
        mouse: Any,
        keyboard: Any,
        current_time: float,
    ) -> None:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Concrete runtime actions
# ---------------------------------------------------------------------------

class NoRuntimeAction(RuntimeAction):
    def update(self, state, last_state, mouse, keyboard, current_time):
        pass


class MouseMoveRuntimeAction(RuntimeAction):
    def __init__(self, config: MouseMoveAction):
        self.config = config

    def update(self, state, last_state, mouse, keyboard, current_time):
        lx = state.get(self.config.x_axis, 0.0)
        ly = state.get(self.config.y_axis, 0.0)

        if abs(lx) < self.config.deadzone:
            lx = 0.0
        if abs(ly) < self.config.deadzone:
            ly = 0.0

        if lx == 0.0 and ly == 0.0:
            return

        dx = (lx ** 3) * self.config.sensitivity
        dy = -(ly ** 3) * self.config.sensitivity

        x, y = mouse.position
        bounds = SCREEN_BOUNDS.get()
        new_x = min(max(bounds[0], int(x + dx)), bounds[2] - 1)
        new_y = min(max(bounds[1], int(y + dy)), bounds[3] - 1)
        mouse.position = (new_x, new_y)


class MouseClickRuntimeAction(RuntimeAction):
    def __init__(self, config: MouseClickAction):
        self.config = config
        self.button = resolve_mouse_button(config.button)

    def update(self, state, last_state, mouse, keyboard, current_time):
        input_name = getattr(self, "_input_name", "")
        is_pressed = state["buttons"].get(input_name, False)
        was_pressed = (
            last_state["buttons"].get(input_name, False) if last_state else False
        )
        if is_pressed and not was_pressed:
            mouse.press(self.button)
        elif not is_pressed and was_pressed:
            mouse.release(self.button)


class RepeatingScrollMixin:
    """Shared timing logic for scroll actions."""

    def __init__(self):
        self.pressed = False
        self.next_scroll_time = 0.0

    def _update_scroll(
        self,
        is_active: bool,
        speed: int,
        initial_delay: float,
        repeat_rate: float,
        current_time: float,
        mouse: Any,
    ) -> None:
        if is_active:
            if not self.pressed:
                mouse.scroll(0, speed)
                self.pressed = True
                self.next_scroll_time = current_time + initial_delay
            elif current_time >= self.next_scroll_time:
                mouse.scroll(0, speed)
                self.next_scroll_time = current_time + repeat_rate
        else:
            self.pressed = False


class ScrollRuntimeAction(RuntimeAction, RepeatingScrollMixin):
    def __init__(self, config: ScrollAction):
        super().__init__()
        self.config = config

    def update(self, state, last_state, mouse, keyboard, current_time):
        input_name = getattr(self, "_input_name", "")
        is_down = state["buttons"].get(input_name, False)
        self._update_scroll(
            is_down,
            self.config.direction * self.config.speed,
            self.config.initial_delay,
            self.config.repeat_rate,
            current_time,
            mouse,
        )


class AnalogScrollRuntimeAction(RuntimeAction, RepeatingScrollMixin):
    def __init__(self, config: AnalogScrollAction):
        super().__init__()
        self.config = config

    def update(self, state, last_state, mouse, keyboard, current_time):
        value = state.get(self.config.axis, 0.0)
        threshold = self.config.threshold
        is_down = value >= threshold if threshold >= 0 else value <= threshold
        self._update_scroll(
            is_down,
            self.config.direction * self.config.speed,
            self.config.initial_delay,
            self.config.repeat_rate,
            current_time,
            mouse,
        )


class KeyRuntimeAction(RuntimeAction):
    def __init__(self, config: KeyAction):
        self.config = config
        self.key = resolve_key(config.key)
        self.modifiers = [resolve_key(m) for m in config.modifiers]

    def update(self, state, last_state, mouse, keyboard, current_time):
        input_name = getattr(self, "_input_name", "")
        is_pressed = state["buttons"].get(input_name, False)
        was_pressed = (
            last_state["buttons"].get(input_name, False) if last_state else False
        )
        if is_pressed and not was_pressed:
            if self.modifiers:
                with keyboard.pressed(*self.modifiers):
                    keyboard.tap(self.key)
            else:
                keyboard.tap(self.key)


class ModifierRuntimeAction(RuntimeAction):
    """No-op at action level; layer switching is handled by ProfileRunner."""

    def __init__(self, config: ModifierAction):
        self.config = config

    def update(self, state, last_state, mouse, keyboard, current_time):
        pass


class CapsWriterRuntimeAction(RuntimeAction):
    def __init__(self, config: CapsWriterAction):
        self.config = config
        self.recording = False

    def _call_hammerspoon(self, func_name: str) -> None:
        script = f'tell application "Hammerspoon" to execute lua code "{func_name}()"'
        try:
            subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                timeout=2,
            )
        except Exception as e:
            print(f"[CapsWriter] Hammerspoon call failed ({func_name}): {e}")

    def update(self, state, last_state, mouse, keyboard, current_time):
        input_name = getattr(self, "_input_name", "")
        is_pressed = state["buttons"].get(input_name, False)
        was_pressed = (
            last_state["buttons"].get(input_name, False) if last_state else False
        )

        if is_pressed and not was_pressed:
            self._call_hammerspoon("CapsWriterGamepadStart")
            self.recording = True
        elif not is_pressed and was_pressed:
            if self.recording:
                self._call_hammerspoon("CapsWriterGamepadStop")
                self.recording = False


ACTION_RUNTIME_MAP = {
    "none": NoRuntimeAction,
    "mouse_click": MouseClickRuntimeAction,
    "mouse_move": MouseMoveRuntimeAction,
    "scroll": ScrollRuntimeAction,
    "analog_scroll": AnalogScrollRuntimeAction,
    "key": KeyRuntimeAction,
    "modifier": ModifierRuntimeAction,
    "caps_writer": CapsWriterRuntimeAction,
}


def build_runtime_action(config: ActionConfig) -> RuntimeAction:
    cls = ACTION_RUNTIME_MAP.get(config.kind, NoRuntimeAction)
    return cls(config)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Profile runner
# ---------------------------------------------------------------------------

class ProfileRunner:
    """Runs a Profile: determines active layer and executes its actions."""

    def __init__(self, profile: Profile):
        self.profile = profile
        self._runtime_actions: dict[tuple[str, str], RuntimeAction] = {}
        for layer_name, layer in profile.layers.items():
            for input_name, action_cfg in layer.actions.items():
                runtime = build_runtime_action(action_cfg)
                runtime._input_name = input_name  # type: ignore[attr-defined]
                self._runtime_actions[(layer_name, input_name)] = runtime
        self.last_state: Optional[dict[str, Any]] = None

    def _resolve_layer(
        self, state: dict[str, Any], layer_name: str = "default", visited: Optional[set[str]] = None
    ) -> str:
        if visited is None:
            visited = set()
        if layer_name in visited:
            return layer_name
        visited.add(layer_name)

        layer = self.profile.layers.get(layer_name)
        if not layer:
            return "default"

        for input_name, action_cfg in layer.actions.items():
            if isinstance(action_cfg, ModifierAction):
                if state["buttons"].get(input_name, False):
                    return self._resolve_layer(state, action_cfg.target_layer, visited)
        return layer_name

    def update(self, state: dict[str, Any], mouse: Any, keyboard: Any) -> None:
        current_time = time.time()
        active_layer = self._resolve_layer(state)

        layer = self.profile.layers.get(active_layer)
        if not layer:
            self.last_state = state
            return

        for input_name, action_cfg in layer.actions.items():
            if action_cfg.kind == "none":
                continue
            runtime = self._runtime_actions.get((active_layer, input_name))
            if runtime is None:
                continue
            runtime.update(state, self.last_state, mouse, keyboard, current_time)

        self.last_state = state


# ---------------------------------------------------------------------------
# Legacy action stubs (preserved so ACTION_CONFIG.py can still be imported
# and migrated to the new v2 profile format by profile_manager).
# ---------------------------------------------------------------------------

class _LegacyAction:
    def update(self, state, last_state, mouse, keyboard):
        pass


class MouseMoveAction(_LegacyAction):
    def __init__(self, x_axis, y_axis, sensitivity, deadzone):
        self.x_axis = x_axis
        self.y_axis = y_axis
        self.sensitivity = sensitivity
        self.deadzone = deadzone


class ClickAction(_LegacyAction):
    def __init__(self, controller_button, mouse_button):
        self.controller_button = controller_button
        self.mouse_button = mouse_button


class ScrollAction(_LegacyAction):
    def __init__(self, controller_button, scroll_speed, initial_delay, repeat_rate):
        self.controller_button = controller_button
        self.scroll_speed = scroll_speed
        self.initial_delay = initial_delay
        self.repeat_rate = repeat_rate


class AnalogAsButtonScrollAction(_LegacyAction):
    def __init__(self, axis_name, threshold, scroll_speed, initial_delay, repeat_rate):
        self.axis_name = axis_name
        self.threshold = threshold
        self.scroll_speed = scroll_speed
        self.initial_delay = initial_delay
        self.repeat_rate = repeat_rate


class KeyboardAction(_LegacyAction):
    def __init__(self, controller_button, key, modifier=None):
        self.controller_button = controller_button
        self.key = key
        self.modifier = modifier


class ComboKeyAction(_LegacyAction):
    def __init__(self, mod_btn, trigger_btn, key, modifier=None):
        self.mod_btn = mod_btn
        self.trigger_btn = trigger_btn
        self.key = key
        self.modifier = modifier


class UDPCapsWriterAction(_LegacyAction):
    def __init__(self, controller_button):
        self.controller_button = controller_button
