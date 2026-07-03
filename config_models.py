"""Data models for the unified controller profile format."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional


PROFILE_VERSION = 2


# ---------------------------------------------------------------------------
# Hardware mapping
# ---------------------------------------------------------------------------

@dataclass
class ButtonMapping:
    kind: str = "button"
    index: int = 0


@dataclass
class AxisMapping:
    kind: str = "axis"
    index: int = 0


@dataclass
class HatMapping:
    kind: str = "hat"
    index: int = 0


@dataclass
class DpadAxesMapping:
    kind: str = "axes"
    x_axis: int = 0
    y_axis: int = 0


HardwareInput = ButtonMapping | AxisMapping | HatMapping | DpadAxesMapping


HARDWARE_DISPATCH = {
    "button": ButtonMapping,
    "axis": AxisMapping,
    "hat": HatMapping,
    "axes": DpadAxesMapping,
}


def hardware_input_from_value(value: Any) -> Optional[HardwareInput]:
    """Parse old list/dict formats and new dataclass dicts into a hardware input."""
    if value is None:
        return None

    if isinstance(value, dict):
        kind = value.get("type") or value.get("kind")
        if kind == "button":
            return ButtonMapping(index=int(value["index"]))
        if kind == "axis":
            return AxisMapping(index=int(value["index"]))
        if kind == "hat":
            return HatMapping(index=int(value["index"]))
        if kind == "axes":
            return DpadAxesMapping(
                x_axis=int(value["x_axis"]),
                y_axis=int(value["y_axis"]),
            )
        return None

    if isinstance(value, (list, tuple)) and len(value) >= 2:
        kind = value[0]
        if kind == "button":
            return ButtonMapping(index=int(value[1]))
        if kind == "axis":
            return AxisMapping(index=int(value[1]))
        if kind == "hat":
            return HatMapping(index=int(value[1]))
        return None

    if isinstance(value, (ButtonMapping, AxisMapping, HatMapping, DpadAxesMapping)):
        return value

    return None


def hardware_input_to_value(hw: Optional[HardwareInput]) -> Optional[Any]:
    if hw is None:
        return None
    return [hw.kind, hw.index] if hw.kind != "axes" else {
        "type": "axes",
        "x_axis": hw.x_axis,
        "y_axis": hw.y_axis,
    }


@dataclass
class HardwareMapping:
    name: str = ""
    # Logical input name -> hardware input
    inputs: dict[str, Optional[HardwareInput]] = field(default_factory=dict)

    def get(self, name: str) -> Optional[HardwareInput]:
        return self.inputs.get(name)

    def set(self, name: str, value: Optional[HardwareInput]) -> None:
        self.inputs[name] = value


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

@dataclass
class NoAction:
    kind: str = "none"


@dataclass
class MouseClickAction:
    kind: str = "mouse_click"
    button: str = "left"  # left, right, middle


@dataclass
class MouseMoveAction:
    kind: str = "mouse_move"
    x_axis: str = "lx"
    y_axis: str = "ly"
    sensitivity: float = 24.0
    deadzone: float = 0.15


@dataclass
class ScrollAction:
    kind: str = "scroll"
    direction: int = -1  # positive or negative speed
    speed: int = 15
    initial_delay: float = 0.3
    repeat_rate: float = 0.05


@dataclass
class AnalogScrollAction:
    kind: str = "analog_scroll"
    axis: str = "lt"
    threshold: float = 0.01
    direction: int = -1
    speed: int = 15
    initial_delay: float = 0.3
    repeat_rate: float = 0.05


@dataclass
class KeyAction:
    kind: str = "key"
    key: str = ""
    modifiers: list[str] = field(default_factory=list)


@dataclass
class ModifierAction:
    kind: str = "modifier"
    target_layer: str = "layer_1"


@dataclass
class CapsWriterAction:
    kind: str = "caps_writer"


Action = (
    NoAction
    | MouseClickAction
    | MouseMoveAction
    | ScrollAction
    | AnalogScrollAction
    | KeyAction
    | ModifierAction
    | CapsWriterAction
)


ACTION_DISPATCH: dict[str, type] = {
    "none": NoAction,
    "mouse_click": MouseClickAction,
    "mouse_move": MouseMoveAction,
    "scroll": ScrollAction,
    "analog_scroll": AnalogScrollAction,
    "key": KeyAction,
    "modifier": ModifierAction,
    "caps_writer": CapsWriterAction,
}


def action_from_dict(d: Optional[dict[str, Any]]) -> Action:
    if not d:
        return NoAction()
    kind = d.get("kind") or d.get("type") or "none"
    cls = ACTION_DISPATCH.get(kind, NoAction)
    # Remove discriminator fields used in old formats if any
    data = {k: v for k, v in d.items() if k not in ("kind", "type")}
    try:
        return cls(**data)
    except TypeError:
        return NoAction()


def action_to_dict(action: Action) -> dict[str, Any]:
    d = asdict(action)
    d["kind"] = d.pop("kind", action.kind)
    return d


# ---------------------------------------------------------------------------
# Layer & Profile
# ---------------------------------------------------------------------------

@dataclass
class Layer:
    name: str = "default"
    actions: dict[str, Action] = field(default_factory=dict)


@dataclass
class ProfileSettings:
    mouse_sensitivity: float = 24.0
    mouse_deadzone: float = 0.15
    scroll_initial_delay: float = 0.3
    scroll_repeat_rate: float = 0.05
    poll_interval: float = 0.005


@dataclass
class Profile:
    version: int = PROFILE_VERSION
    name: str = ""
    hardware: HardwareMapping = field(default_factory=HardwareMapping)
    settings: ProfileSettings = field(default_factory=ProfileSettings)
    layers: dict[str, Layer] = field(default_factory=lambda: {"default": Layer()})

    def get_default_layer(self) -> Layer:
        return self.layers.setdefault("default", Layer(name="default"))

    def get_or_create_layer(self, name: str) -> Layer:
        if name not in self.layers:
            self.layers[name] = Layer(name=name)
        return self.layers[name]

    def get_action(self, layer_name: str, input_name: str) -> Action:
        layer = self.layers.get(layer_name)
        if layer is None:
            return NoAction()
        return layer.actions.get(input_name, NoAction())

    def set_action(self, layer_name: str, input_name: str, action: Action) -> None:
        layer = self.get_or_create_layer(layer_name)
        layer.actions[input_name] = action
