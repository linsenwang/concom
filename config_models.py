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


# The d-pad reaches the runtime both as four buttons (UP/DOWN/LEFT/RIGHT) and
# as a pair of axes ("dx"/"dy"), so a wheel menu can be aimed with it.  Each
# axis is derived from the two buttons listed here, which is why a wheel aimed
# with the d-pad has to mute those buttons' own bindings while it is open.
DPAD_AXIS_INPUTS: dict[str, tuple[str, str]] = {
    "dx": ("RIGHT", "LEFT"),
    "dy": ("UP", "DOWN"),
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


@dataclass
class CommandAction:
    kind: str = "command"
    command: str = ""


def segment_width(value: Any) -> float:
    """Coerce a petal's share to a usable float; 0 means "never picked"."""
    try:
        width = float(value)
    except (TypeError, ValueError):
        return 1.0
    if not 0.0 <= width < float("inf"):  # rejects NaN, inf and negatives
        return 1.0
    return width


@dataclass
class WheelSegment:
    """One petal of a wheel menu: a label, a nested action dict, and its share.

    ``width`` is a relative share: a petal takes ``width / sum(widths)`` of the
    circle, so 2.0 is twice as wide as 1.0 and 0.5 half as wide.
    """

    label: str = ""
    action: dict[str, Any] = field(default_factory=dict)
    width: float = 1.0

    def __post_init__(self) -> None:
        self.width = segment_width(self.width)


@dataclass
class WheelAction:
    """Hold the bound button to show a radial menu, aim with a stick, release to fire."""

    kind: str = "wheel"
    segments: list[WheelSegment] = field(default_factory=list)
    pointer_x: str = "lx"
    pointer_y: str = "ly"
    deadzone: float = 0.45


Action = (
    NoAction
    | MouseClickAction
    | MouseMoveAction
    | ScrollAction
    | AnalogScrollAction
    | KeyAction
    | ModifierAction
    | CapsWriterAction
    | CommandAction
    | WheelAction
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
    "command": CommandAction,
    "wheel": WheelAction,
}


def wheel_segments_from_value(value: Any) -> list[WheelSegment]:
    """Normalise a wheel's petals from JSON (list of {label, action} dicts)."""
    segments: list[WheelSegment] = []
    if not isinstance(value, (list, tuple)):
        return segments
    for item in value:
        if isinstance(item, WheelSegment):
            segments.append(item)
            continue
        if not isinstance(item, dict):
            continue
        action = item.get("action")
        segments.append(
            WheelSegment(
                label=str(item.get("label", "")),
                action=action if isinstance(action, dict) else {},
                width=item.get("width", 1.0),
            )
        )
    return segments


def action_from_dict(d: Optional[dict[str, Any]]) -> Action:
    if not d:
        return NoAction()
    kind = d.get("kind") or d.get("type") or "none"
    if kind == "wheel":
        return WheelAction(
            segments=wheel_segments_from_value(d.get("segments", [])),
            pointer_x=str(d.get("pointer_x", "lx")),
            pointer_y=str(d.get("pointer_y", "ly")),
            deadzone=float(d.get("deadzone", 0.45)),
        )
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
    if action.kind == "wheel":
        # Only spell out shares that differ from the default, so a hand-written
        # profile keeps its shape after a round-trip through the configurator.
        for segment in d.get("segments", []):
            if segment.get("width") == 1.0:
                segment.pop("width", None)
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
    # Input poll period in seconds. Raising the rate only makes the pointer
    # smoother; it does not change how fast it travels.
    poll_interval: float = 0.002


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
