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
    CommandAction,
    KeyAction,
    ModifierAction,
    MouseClickAction,
    MouseMoveAction,
    Profile,
    ScrollAction,
    WheelAction,
    action_from_dict,
)
from wheel_overlay import RadialWheelOverlay, direction_to_index

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

    def trigger_once(self, mouse: Any, keyboard: Any) -> None:
        """Fire the action immediately, ignoring button state (used by the wheel)."""
        pass


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

    def trigger_once(self, mouse, keyboard):
        mouse.click(self.button)

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

    def trigger_once(self, mouse, keyboard):
        if self.modifiers:
            with keyboard.pressed(*self.modifiers):
                keyboard.tap(self.key)
        else:
            keyboard.tap(self.key)

    def update(self, state, last_state, mouse, keyboard, current_time):
        input_name = getattr(self, "_input_name", "")
        is_pressed = state["buttons"].get(input_name, False)
        was_pressed = (
            last_state["buttons"].get(input_name, False) if last_state else False
        )
        if is_pressed and not was_pressed:
            self.trigger_once(mouse, keyboard)


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


class CommandRuntimeAction(RuntimeAction):
    """Runs a shell command, e.g. 'open -a "Google Chrome"'."""

    def __init__(self, config: CommandAction):
        self.config = config

    def trigger_once(self, mouse, keyboard):
        if not self.config.command:
            return
        try:
            subprocess.Popen(self.config.command, shell=True)
        except Exception as e:
            print(f"[Command] 执行失败 ({self.config.command}): {e}")

    def update(self, state, last_state, mouse, keyboard, current_time):
        input_name = getattr(self, "_input_name", "")
        is_pressed = state["buttons"].get(input_name, False)
        was_pressed = (
            last_state["buttons"].get(input_name, False) if last_state else False
        )
        if is_pressed and not was_pressed:
            self.trigger_once(mouse, keyboard)


class WheelRuntimeAction(RuntimeAction):
    """Hold the bound button to show a wheel, aim with a stick, let the stick go.

    Commit: let the aiming stick fall back inside the deadzone after having
    pointed somewhere.  Cancel: let go of the bound button first.
    The stick used for aiming is relieved of its normal duty (mouse movement)
    for as long as the wheel is open, see ProfileRunner.update.
    """
    def __init__(self, config: WheelAction):
        self.config = config
        self.segments: list[tuple[str, RuntimeAction]] = [
            (
                segment.label or segment.action.get("kind", "?"),
                build_runtime_action(action_from_dict(segment.action)),
            )
            for segment in config.segments
        ]
        self.overlay = RadialWheelOverlay()
        self.visible = False
        self.selected = -1
        self._aimed = False
        self._fired = False
        self._await_recenter = False
        self._warned = False

    @property
    def labels(self) -> list[str]:
        return [label for label, _ in self.segments]

    @property
    def pointer_axes(self) -> tuple[str, str]:
        return (self.config.pointer_x, self.config.pointer_y)

    @property
    def grabbing_pointer(self) -> bool:
        """True while the aiming stick must not drag the mouse.

        Stays true after a cancel until the stick falls back to centre, so a
        cancelled gesture cannot fling the cursor across the screen.
        """
        return self.visible or self._await_recenter

    def _open(self) -> None:
        if not self.segments:
            return
        self.visible = True
        self.selected = -1
        self._aimed = False
        self._fired = False
        if self.overlay.available:
            self.overlay.show(self.labels, -1)
        elif not self._warned:
            self._warned = True
            print("[转轮] 无法创建悬浮窗，改为在终端提示选中项。")

    def _hide(self) -> None:
        self.visible = False
        self.selected = -1
        if self.overlay.available:
            self.overlay.hide()

    def _point_at(self, state: dict[str, Any]) -> int:
        return direction_to_index(
            state.get(self.config.pointer_x, 0.0),
            state.get(self.config.pointer_y, 0.0),
            len(self.segments),
            self.config.deadzone,
        )

    def _aim(self, state: dict[str, Any], mouse: Any, keyboard: Any) -> None:
        index = self._point_at(state)
        if index >= 0:
            self._aimed = True
        elif self._aimed:
            # Stick released back to centre: commit whatever was highlighted.
            self._fire(mouse, keyboard)
            return

        if index == self.selected:
            return
        self.selected = index
        if self.overlay.available:
            self.overlay.show(self.labels, index)
        elif index >= 0:
            print(f"[转轮] 选中: {self.segments[index][0]}")

    def _fire(self, mouse: Any, keyboard: Any) -> None:
        index = self.selected
        self._fired = True
        self._hide()
        if 0 <= index < len(self.segments):
            label, runtime = self.segments[index]
            print(f"[转轮] 执行: {label}")
            runtime.trigger_once(mouse, keyboard)

    def hide(self) -> None:
        """Drop the overlay without firing anything."""
        self._hide()
        self._aimed = False
        self._fired = False
        self._await_recenter = False

    def update(self, state, last_state, mouse, keyboard, current_time):
        input_name = getattr(self, "_input_name", "")
        is_down = state["buttons"].get(input_name, False)
        was_down = (
            last_state["buttons"].get(input_name, False) if last_state else False
        )

        if self._await_recenter and self._point_at(state) < 0:
            self._await_recenter = False  # stick is home again

        if not is_down:
            if was_down or self.visible:
                if self._fired:
                    self.hide()
                else:
                    # Right hand let go first: cancel. Keep the aiming stick
                    # muzzled until it falls back to centre so cancelling does
                    # not fling the cursor across the screen.
                    deflected = self._point_at(state) >= 0
                    self.hide()  # resets the muzzle flag
                    self._await_recenter = deflected
                    print("[转轮] 取消")
            return

        if not was_down:
            self._open()
        if self._fired:
            return
        self._aim(state, mouse, keyboard)


ACTION_RUNTIME_MAP = {
    "none": NoRuntimeAction,
    "mouse_click": MouseClickRuntimeAction,
    "mouse_move": MouseMoveRuntimeAction,
    "scroll": ScrollRuntimeAction,
    "analog_scroll": AnalogScrollRuntimeAction,
    "key": KeyRuntimeAction,
    "modifier": ModifierRuntimeAction,
    "caps_writer": CapsWriterRuntimeAction,
    "command": CommandRuntimeAction,
    "wheel": WheelRuntimeAction,
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
        self._wheel_actions: list[WheelRuntimeAction] = []
        for layer_name, layer in profile.layers.items():
            for input_name, action_cfg in layer.actions.items():
                runtime = build_runtime_action(action_cfg)
                runtime._input_name = input_name  # type: ignore[attr-defined]
                if isinstance(runtime, WheelRuntimeAction):
                    self._wheel_actions.append(runtime)
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

        # While a wheel is aiming (or waiting for the stick to fall back after
        # a cancel) the stick that points at it must not drag the mouse.
        pointer_axes = {
            axis
            for wheel in self._wheel_actions
            if wheel.grabbing_pointer
            for axis in wheel.pointer_axes
        }

        for input_name, action_cfg in layer.actions.items():
            if action_cfg.kind == "none":
                continue
            if action_cfg.kind == "mouse_move" and (
                action_cfg.x_axis in pointer_axes or action_cfg.y_axis in pointer_axes
            ):
                continue
            runtime = self._runtime_actions.get((active_layer, input_name))
            if runtime is None:
                continue
            runtime.update(state, self.last_state, mouse, keyboard, current_time)

        self.last_state = state

    def close(self) -> None:
        """Release on-screen state, e.g. when the controller goes away."""
        for action in self._wheel_actions:
            action.hide()


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
