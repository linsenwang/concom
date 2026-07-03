"""Joystick input reader built around the unified hardware mapping."""

from __future__ import annotations

from typing import Any, Optional

import pygame

from config_models import (
    AxisMapping,
    ButtonMapping,
    DpadAxesMapping,
    HardwareMapping,
    HatMapping,
)


class GenericController:
    def __init__(
        self,
        hardware: HardwareMapping,
        auto_activate_index: Optional[int] = None,
        xbox_trigger_fix: bool = True,
    ):
        if not hardware or not hardware.inputs:
            raise ValueError("必须提供有效的硬件映射 (hardware mapping)。")

        self.hardware = hardware
        self.xbox_trigger_fix = xbox_trigger_fix

        self.button_map: dict[int, str] = {}
        self.axis_map: dict[int, str] = {}
        self.dpad_config: Optional[DpadAxesMapping | HatMapping] = None

        for logical_name, hw in hardware.inputs.items():
            if hw is None:
                continue
            if isinstance(hw, ButtonMapping):
                self.button_map[hw.index] = logical_name
            elif isinstance(hw, AxisMapping):
                self.axis_map[hw.index] = logical_name
            elif isinstance(hw, (DpadAxesMapping, HatMapping)):
                if logical_name == "dpad":
                    self.dpad_config = hw

        self.joysticks: dict[int, pygame.joystick.Joystick] = {}
        self.active_joy: Optional[pygame.joystick.Joystick] = None
        self.trigger_initialized = {"lt": False, "rt": False}

        # Cached capabilities of the active joystick
        self._num_buttons = 0
        self._num_axes = 0
        self._num_hats = 0

        pygame.joystick.init()
        for i in range(pygame.joystick.get_count()):
            self._add_joystick(i)

        if auto_activate_index is not None:
            self._try_auto_activate(auto_activate_index)

        if not self.active_joy:
            print("等待手柄输入以激活...")

    def _add_joystick(self, device_index: int) -> None:
        try:
            joy = pygame.joystick.Joystick(device_index)
            instance_id = joy.get_instance_id()
            if instance_id in self.joysticks:
                return
            self.joysticks[instance_id] = joy
            if not joy.get_init():
                joy.init()
            print(f"系统挂载设备: '{joy.get_name()}' (ID: {instance_id})")
        except pygame.error as e:
            print(f"添加手柄错误: {e}")

    def _remove_joystick(self, instance_id: int) -> bool:
        was_active = False
        if instance_id in self.joysticks:
            joy_name = self.joysticks[instance_id].get_name()
            print(f"\n设备 '{joy_name}' (ID: {instance_id}) 已断开。")
            del self.joysticks[instance_id]

        if self.active_joy and self.active_joy.get_instance_id() == instance_id:
            print("❌ 当前活动手柄已断开。")
            self.active_joy = None
            was_active = True
        return was_active

    def _try_auto_activate(self, device_index: int) -> None:
        """Try to activate the joystick with the given device index."""
        try:
            joy = pygame.joystick.Joystick(device_index)
            instance_id = joy.get_instance_id()
            if instance_id not in self.joysticks:
                self._add_joystick(device_index)
            self.active_joy = self.joysticks.get(instance_id)
            if self.active_joy:
                self.trigger_initialized = {"lt": False, "rt": False}
                self._cache_capabilities()
                print(
                    f"\n🎮 手柄已自动激活: {self.active_joy.get_name()} "
                    f"(ID: {self.active_joy.get_instance_id()})"
                )
        except pygame.error as e:
            print(f"自动激活失败: {e}")

    def _cache_capabilities(self) -> None:
        if self.active_joy is None:
            return
        self._num_buttons = self.active_joy.get_numbuttons()
        self._num_axes = self.active_joy.get_numaxes()
        self._num_hats = self.active_joy.get_numhats()

    def read(self) -> Optional[dict[str, Any]]:
        active_joy_disconnected = False

        try:
            events = pygame.event.get()
        except (SystemError, pygame.error, KeyError) as e:
            # pygame 在手柄热插拔时可能抛出内部错误；清掉事件队列并重试
            print(f"[GenericController] 读取事件异常: {e}")
            try:
                pygame.event.clear()
            except Exception:
                pass
            return None

        for event in events:
            if event.type == pygame.JOYDEVICEADDED:
                self._add_joystick(event.device_index)
                if not self.active_joy:
                    print("新设备已连接。请按键激活...")

            elif event.type == pygame.JOYDEVICEREMOVED:
                if self._remove_joystick(event.instance_id):
                    active_joy_disconnected = True

            elif self.active_joy is None:
                if (
                    event.type == pygame.JOYBUTTONDOWN
                    or (
                        event.type == pygame.JOYAXISMOTION
                        and abs(event.value) > 0.8
                    )
                    or (
                        event.type == pygame.JOYHATMOTION
                        and event.value != (0, 0)
                    )
                ):
                    joy_to_activate = self.joysticks.get(event.instance_id)
                    if joy_to_activate:
                        self.active_joy = joy_to_activate
                        self.trigger_initialized = {"lt": False, "rt": False}
                        self._cache_capabilities()
                        print(
                            f"\n🎮 手柄已激活: {self.active_joy.get_name()} "
                            f"(ID: {self.active_joy.get_instance_id()})"
                        )
                        break

        if active_joy_disconnected:
            return {"status": "disconnected"}
        if self.active_joy is None:
            return None

        joy = self.active_joy

        # Buttons
        buttons = {name: False for name in self.button_map.values()}
        for i in range(self._num_buttons):
            if joy.get_button(i):
                name = self.button_map.get(i)
                if name:
                    buttons[name] = True

        # Directional aliases
        for direction in ("UP", "DOWN", "LEFT", "RIGHT"):
            if direction not in buttons:
                buttons[direction] = False

        # D-pad
        if self.dpad_config:
            if isinstance(self.dpad_config, DpadAxesMapping):
                x_idx = self.dpad_config.x_axis
                y_idx = self.dpad_config.y_axis
                threshold = 0.5
                if x_idx < self._num_axes:
                    val = joy.get_axis(x_idx)
                    if val < -threshold:
                        buttons["LEFT"] = True
                    if val > threshold:
                        buttons["RIGHT"] = True
                if y_idx < self._num_axes:
                    val = joy.get_axis(y_idx)
                    if val < -threshold:
                        buttons["UP"] = True
                    if val > threshold:
                        buttons["DOWN"] = True
            elif isinstance(self.dpad_config, HatMapping):
                hat_idx = self.dpad_config.index
                if self._num_hats > hat_idx:
                    hat_val = joy.get_hat(hat_idx)
                    if hat_val[1] == 1:
                        buttons["UP"] = True
                    if hat_val[1] == -1:
                        buttons["DOWN"] = True
                    if hat_val[0] == -1:
                        buttons["LEFT"] = True
                    if hat_val[0] == 1:
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

        # Axes
        axes: dict[str, float] = {}
        for name in self.axis_map.values():
            axes[name] = -1.0 if name in ("lt", "rt") else 0.0

        for i in range(self._num_axes):
            axis_name = self.axis_map.get(i)
            if not axis_name:
                continue
            value = joy.get_axis(i)

            if axis_name in ("lt", "rt") and self.xbox_trigger_fix:
                if value == 0.0 and not self.trigger_initialized[axis_name]:
                    value = -1.0
                elif value != 0.0:
                    self.trigger_initialized[axis_name] = True

            if axis_name in ("ly", "ry"):
                value *= -1
            axes[axis_name] = value

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

    def close(self) -> None:
        self.active_joy = None
        self.joysticks.clear()
        if pygame.joystick.get_init():
            pygame.joystick.quit()
        print("控制器资源已释放。")
