"""Load, save, and migrate unified controller profiles."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

from config_models import (
    Action,
    AnalogScrollAction,
    ButtonMapping,
    CapsWriterAction,
    DpadAxesMapping,
    HardwareInput,
    HardwareMapping,
    HatMapping,
    KeyAction,
    Layer,
    ModifierAction,
    MouseClickAction,
    MouseMoveAction,
    NoAction,
    Profile,
    ProfileSettings,
    ScrollAction,
    action_from_dict,
    action_to_dict,
    hardware_input_from_value,
    hardware_input_to_value,
)


def sanitize_filename(name: str) -> str:
    s = re.sub(r"[^\w\s-]", "", name).strip()
    s = re.sub(r"[-\s]+", "_", s)
    return f"profile_{s}.json"


def _pynput_to_str(value: Any) -> str:
    """Convert pynput Key/Button enums to strings for storage."""
    if value is None:
        return ""
    name = str(value)
    # pynput repr looks like 'Key.cmd' or 'Button.left'
    if "." in name:
        return name.split(".")[-1]
    return name


def _normalize_modifiers(modifier: Any) -> list[str]:
    if modifier is None:
        return []
    if isinstance(modifier, (list, tuple)):
        return [_pynput_to_str(m) for m in modifier]
    return [_pynput_to_str(modifier)]


def _hardware_from_old_map(data: dict[str, Any]) -> HardwareMapping:
    """Convert old map_*.json (list or dict format) into HardwareMapping."""
    name = data.get("name", "")
    inputs: dict[str, Optional[HardwareInput]] = {}
    dpad_axes: dict[str, int] = {}

    for key, value in data.items():
        if key == "name":
            continue

        upper_key = key.upper()

        # Old dict format for dpad: {"type": "axis", "index": 0, "value": -1}
        if isinstance(value, dict):
            kind = value.get("type")
            if kind == "axis" and upper_key.startswith("DPAD_"):
                axis_index = int(value["index"])
                axis_value = int(value.get("value", 0))
                if upper_key in ("DPAD_UP", "DPAD_DOWN"):
                    dpad_axes.setdefault("y_axis", axis_index)
                elif upper_key in ("DPAD_LEFT", "DPAD_RIGHT"):
                    dpad_axes.setdefault("x_axis", axis_index)
                continue
            # Generic dict mapping
            hw = hardware_input_from_value(value)
            if hw:
                inputs[key] = hw
            continue

        # List format: ["button", 0]
        if isinstance(value, (list, tuple)):
            hw = hardware_input_from_value(value)
            if hw:
                inputs[key] = hw
            continue

    if "dpad" not in inputs and "x_axis" in dpad_axes and "y_axis" in dpad_axes:
        inputs["dpad"] = DpadAxesMapping(
            x_axis=dpad_axes["x_axis"],
            y_axis=dpad_axes["y_axis"],
        )

    return HardwareMapping(name=name, inputs=inputs)


def _actions_from_old_action_config() -> tuple[dict[str, Action], dict[str, dict[str, Action]]]:
    """Import the legacy ACTION_CONFIG and convert it into a default layer + modifier layers."""
    default_actions: dict[str, Action] = {}
    modifier_layers: dict[str, dict[str, Action]] = {}

    try:
        import ACTION_CONFIG as ac
    except Exception:
        return default_actions, modifier_layers

    # First pass: convert simple actions.
    for action in ac.ACTION_CONFIG:
        cls_name = type(action).__name__

        if cls_name == "MouseMoveAction":
            stick_key = "RIGHT_STICK" if action.x_axis == "rx" else "LEFT_STICK"
            default_actions[stick_key] = MouseMoveAction(
                x_axis=action.x_axis,
                y_axis=action.y_axis,
                sensitivity=action.sensitivity,
                deadzone=action.deadzone,
            )

        elif cls_name == "ClickAction":
            default_actions[action.controller_button] = MouseClickAction(
                button=_pynput_to_str(action.mouse_button)
            )

        elif cls_name == "ScrollAction":
            default_actions[action.controller_button] = ScrollAction(
                direction=-1 if action.scroll_speed < 0 else 1,
                speed=abs(action.scroll_speed),
                initial_delay=action.initial_delay,
                repeat_rate=action.repeat_rate,
            )

        elif cls_name == "AnalogAsButtonScrollAction":
            trigger_key = "RT" if action.axis_name == "rt" else "LT"
            default_actions[trigger_key] = AnalogScrollAction(
                axis=action.axis_name,
                threshold=action.threshold,
                direction=-1 if action.scroll_speed < 0 else 1,
                speed=abs(action.scroll_speed),
                initial_delay=action.initial_delay,
                repeat_rate=action.repeat_rate,
            )

        elif cls_name == "KeyboardAction":
            default_actions[action.controller_button] = KeyAction(
                key=_pynput_to_str(action.key),
                modifiers=_normalize_modifiers(action.modifier),
            )

        elif cls_name == "UDPCapsWriterAction":
            default_actions[action.controller_button] = CapsWriterAction()

        elif cls_name == "ComboKeyAction":
            layer_name = f"layer_{action.mod_btn}"
            layer = modifier_layers.setdefault(layer_name, {})
            layer[action.trigger_btn] = KeyAction(
                key=_pynput_to_str(action.key),
                modifiers=_normalize_modifiers(action.modifier),
            )

    # Second pass: any button used as a combo modifier becomes a layer switch.
    for layer_name, actions in modifier_layers.items():
        mod_btn = layer_name.replace("layer_", "", 1)
        default_actions[mod_btn] = ModifierAction(target_layer=layer_name)

    return default_actions, modifier_layers


def _build_default_profile(hardware: HardwareMapping) -> Profile:
    """Build a minimal default profile from legacy ACTION_CONFIG."""
    default_actions, modifier_layers = _actions_from_old_action_config()

    layers: dict[str, Layer] = {"default": Layer(name="default", actions=default_actions)}
    for layer_name, actions in modifier_layers.items():
        layers[layer_name] = Layer(name=layer_name, actions=actions)

    return Profile(
        name=hardware.name,
        hardware=hardware,
        layers=layers,
    )


def load_profile(controller_name: str, mapping_dir: str = ".") -> Profile:
    """Load a profile. Migrate from old map_*.json + ACTION_CONFIG if no profile exists."""
    profile_file = os.path.join(mapping_dir, sanitize_filename(controller_name))

    if os.path.exists(profile_file):
        with open(profile_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return _profile_from_dict(data)

    # Fallback: migrate from old map file
    old_map_file = os.path.join(mapping_dir, _old_map_filename(controller_name))
    if os.path.exists(old_map_file):
        with open(old_map_file, "r", encoding="utf-8") as f:
            old_data = json.load(f)
        hardware = _hardware_from_old_map(old_data)
        profile = _build_default_profile(hardware)
        save_profile(profile, mapping_dir=mapping_dir)
        return profile

    # Nothing found: return empty profile
    return Profile(name=controller_name)


def _old_map_filename(name: str) -> str:
    s = re.sub(r"[^\w\s-]", "", name).strip()
    s = re.sub(r"[-\s]+", "_", s)
    return f"map_{s}.json"


def _profile_from_dict(data: dict[str, Any]) -> Profile:
    version = data.get("version", 1)
    name = data.get("name", "")

    hardware_data = data.get("hardware", {})
    inputs: dict[str, Optional[HardwareInput]] = {}
    for k, v in hardware_data.items():
        inputs[k] = hardware_input_from_value(v)
    hardware = HardwareMapping(name=name, inputs=inputs)

    settings_data = data.get("settings", {})
    settings = ProfileSettings(**settings_data)

    layers_data = data.get("layers", {})
    layers: dict[str, Layer] = {}
    for layer_name, layer_data in layers_data.items():
        actions_data = layer_data if isinstance(layer_data, dict) else layer_data.get("actions", {})
        actions: dict[str, Action] = {}
        for input_name, action_data in actions_data.items():
            actions[input_name] = action_from_dict(action_data)
        layers[layer_name] = Layer(name=layer_name, actions=actions)

    if "default" not in layers:
        layers["default"] = Layer(name="default")

    return Profile(
        version=version,
        name=name,
        hardware=hardware,
        settings=settings,
        layers=layers,
    )


def _profile_to_dict(profile: Profile) -> dict[str, Any]:
    layers_dict: dict[str, Any] = {}
    for layer_name, layer in profile.layers.items():
        layers_dict[layer_name] = {
            input_name: action_to_dict(action)
            for input_name, action in layer.actions.items()
        }

    hardware_dict = {
        k: hardware_input_to_value(v)
        for k, v in profile.hardware.inputs.items()
        if v is not None
    }

    return {
        "version": profile.version,
        "name": profile.name,
        "hardware": hardware_dict,
        "settings": {
            "mouse_sensitivity": profile.settings.mouse_sensitivity,
            "mouse_deadzone": profile.settings.mouse_deadzone,
            "scroll_initial_delay": profile.settings.scroll_initial_delay,
            "scroll_repeat_rate": profile.settings.scroll_repeat_rate,
            "poll_interval": profile.settings.poll_interval,
        },
        "layers": layers_dict,
    }


def save_profile(profile: Profile, mapping_dir: str = ".") -> str:
    """Save profile to disk and return the file path."""
    profile_file = os.path.join(mapping_dir, sanitize_filename(profile.name or "unknown"))
    data = _profile_to_dict(profile)
    with open(profile_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    return profile_file


def list_profiles(mapping_dir: str = ".") -> list[str]:
    """Return names of controllers that have a v2 profile."""
    profiles = []
    if not os.path.isdir(mapping_dir):
        return profiles
    for fname in os.listdir(mapping_dir):
        if fname.startswith("profile_") and fname.endswith(".json"):
            profiles.append(fname[8:-5])
    return profiles
