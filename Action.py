import time
import socket
import subprocess

class Action:
    def update(self, state, last_state, mouse, keyboard):
        pass

import Quartz

def get_virtual_screen_bounds():
    """获取所有活跃显示器的并集边界，支持多屏幕环境。"""
    max_displays = 32
    (error, display_ids, count) = Quartz.CGGetActiveDisplayList(max_displays, None, None)
    if error != 0 or count == 0:
        # 回退到主屏幕
        main = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID())
        return int(main.origin.x), int(main.origin.y), int(main.origin.x + main.size.width), int(main.origin.y + main.size.height)
    
    min_x = float('inf')
    min_y = float('inf')
    max_x = float('-inf')
    max_y = float('-inf')
    
    for display_id in display_ids:
        bounds = Quartz.CGDisplayBounds(display_id)
        min_x = min(min_x, bounds.origin.x)
        min_y = min(min_y, bounds.origin.y)
        max_x = max(max_x, bounds.origin.x + bounds.size.width)
        max_y = max(max_y, bounds.origin.y + bounds.size.height)
    
    return int(min_x), int(min_y), int(max_x), int(max_y)

SCREEN_BOUNDS = get_virtual_screen_bounds()  # (min_x, min_y, max_x, max_y)

class MouseMoveAction(Action):
    def __init__(self, x_axis, y_axis, sensitivity, deadzone):
        self.x_axis = x_axis
        self.y_axis = y_axis
        self.sensitivity = sensitivity
        self.deadzone = deadzone

    def update(self, state, last_state, mouse, keyboard):
        lx, ly = state[self.x_axis], state[self.y_axis]

        if abs(lx) < self.deadzone: lx = 0
        if abs(ly) < self.deadzone: ly = 0

        if lx != 0 or ly != 0:
            dx = (lx ** 3) * self.sensitivity
            dy = -(ly ** 3) * self.sensitivity

            # 当前绝对位置
            x, y = mouse.position

            # 新位置（做钳制，使用所有屏幕的并集边界）
            new_x = min(max(SCREEN_BOUNDS[0], x + dx), SCREEN_BOUNDS[2] - 1)
            new_y = min(max(SCREEN_BOUNDS[1], y + dy), SCREEN_BOUNDS[3] - 1)

            mouse.position = (new_x, new_y)

class ClickAction(Action):
    def __init__(self, controller_button, mouse_button): self.controller_button, self.mouse_button = controller_button, mouse_button
    def update(self, state, last_state, mouse, keyboard):
        is_pressed = state['buttons'].get(self.controller_button, False)
        was_pressed = last_state['buttons'].get(self.controller_button, False) if last_state else False
        if is_pressed and not was_pressed: mouse.press(self.mouse_button)
        elif not is_pressed and was_pressed: mouse.release(self.mouse_button)
class ScrollAction(Action):
    def __init__(self, controller_button, scroll_speed, initial_delay, repeat_rate): self.controller_button, self.scroll_speed, self.initial_delay, self.repeat_rate = controller_button, scroll_speed, initial_delay, repeat_rate; self.pressed, self.next_scroll_time = False, 0
    def update(self, state, last_state, mouse, keyboard):
        is_down = state['buttons'].get(self.controller_button, False)
        current_time = time.time()
        if is_down:
            if not self.pressed: mouse.scroll(0, self.scroll_speed); self.pressed = True; self.next_scroll_time = current_time + self.initial_delay
            elif current_time >= self.next_scroll_time: mouse.scroll(0, self.scroll_speed); self.next_scroll_time = current_time + self.repeat_rate
        else: self.pressed = False
class KeyboardAction(Action):
    def __init__(self, controller_button, key, modifier=None): self.controller_button, self.key, self.modifier = controller_button, key, ([modifier] if modifier and not isinstance(modifier, (list, tuple)) else modifier)
    def update(self, state, last_state, mouse, keyboard):
        is_pressed = state['buttons'].get(self.controller_button, False)
        was_pressed = last_state['buttons'].get(self.controller_button, False) if last_state else False
        if is_pressed and not was_pressed:
            if self.modifier:
                with keyboard.pressed(*self.modifier): keyboard.tap(self.key)
            else: keyboard.tap(self.key)
class AnalogAsButtonScrollAction(Action):
    def __init__(self, axis_name, threshold, scroll_speed, initial_delay, repeat_rate): self.axis_name, self.threshold, self.scroll_speed, self.initial_delay, self.repeat_rate = axis_name, threshold, scroll_speed, initial_delay, repeat_rate; self.pressed, self.next_scroll_time = False, 0
    def update(self, state, last_state, mouse, keyboard):
        value = state.get(self.axis_name, 0.0); is_down = value >= self.threshold if self.threshold >= 0 else value <= self.threshold; current_time = time.time()
        if is_down:
            if not self.pressed: mouse.scroll(0, self.scroll_speed); self.pressed = True; self.next_scroll_time = current_time + self.initial_delay
            elif current_time >= self.next_scroll_time: mouse.scroll(0, self.scroll_speed); self.next_scroll_time = current_time + self.repeat_rate
        else: self.pressed = False
class ThresholdAction(Action):
    def __init__(self, source_axis, threshold, output_button_name): self.source_axis, self.threshold, self.output_button_name = source_axis, threshold, output_button_name
    def update(self, state, last_state, mouse, keyboard):
        value = state.get(self.source_axis, 0.0)
        state['buttons'][self.output_button_name] = (value >= self.threshold if self.threshold >= 0 else value <= self.threshold)
SHARED_CONSUMED_STATE = {}

class ComboKeyAction(Action):
    def __init__(self, mod_btn, trigger_btn, key, modifier=None):
        self.mod_btn = mod_btn
        self.trigger_btn = trigger_btn
        self.key = key
        self.modifier = ([modifier] if modifier and not isinstance(modifier, (list, tuple)) else modifier)
        # 自己记录 trigger 的真实状态，不受 state 修改的影响
        self.prev_trigger_real_state = False 

    def update(self, state, last_state, mouse, keyboard):
        mod_down = state['buttons'].get(self.mod_btn, False)
        # 获取当前帧 trigger 的真实物理状态
        trigger_real_down = state['buttons'].get(self.trigger_btn, False)

        if mod_down and trigger_real_down:
            # 1. 标记修饰键已脏（全局记录，直到修饰键松开才清除）
            SHARED_CONSUMED_STATE[self.mod_btn] = True

            # 2. 检测上升沿：只有当“物理上”刚按下 trigger 时才触发
            if not self.prev_trigger_real_state:
                if self.modifier:
                    with keyboard.pressed(*self.modifier): keyboard.tap(self.key)
                else:
                    keyboard.tap(self.key)
                print(f"Combo Executed: {self.mod_btn} + {self.trigger_btn}")

            # 3. 拦截：从 state 中移除 trigger，防止后面的普通 Action 触发
            state['buttons'][self.trigger_btn] = False
        
        # 更新内部记录的真实状态，供下一帧使用
        self.prev_trigger_real_state = trigger_real_down


class SmartKeyAction(Action):
    def __init__(self, controller_button, key, modifier=None):
        self.button = controller_button
        self.key = key
        self.modifier = ([modifier] if modifier and not isinstance(modifier, (list, tuple)) else modifier)

    def update(self, state, last_state, mouse, keyboard):
        curr = state['buttons'].get(self.button, False)
        prev = last_state['buttons'].get(self.button, False) if last_state else False

        # 当按键松开的瞬间 (Falling Edge)
        if prev and not curr:
            # 检查全局状态：这个键刚才被 Combo 用过吗？
            was_consumed = SHARED_CONSUMED_STATE.get(self.button, False)
            
            if not was_consumed:
                # 没被用过，说明是单纯的单击，触发原功能
                if self.modifier:
                    with keyboard.pressed(*self.modifier): keyboard.tap(self.key)
                else:
                    keyboard.tap(self.key)
                print(f"SmartKey Triggered: {self.button}")
            else:
                print(f"SmartKey Ignored (Consumed): {self.button}")

            # 重置消费状态，为下一次按下做准备
            SHARED_CONSUMED_STATE[self.button] = False

class UDPCapsWriterAction(Action):
    """按住开始录音，松开发送识别（对讲机模式）

    通过 AppleScript 调用 Hammerspoon，让 Hammerspoon 显示悬浮窗并控制 CapsWriter。
    Smart 逻辑：当 X 被用作组合键修饰键时，不触发录音。
    支持 X + 方向键 的组合键功能（切桌面、Tab 切换）。
    """
    def __init__(self, controller_button, addr='127.0.0.1', port=6018):
        self.controller_button = controller_button
        # addr/port 保留兼容性，但实际通过 Hammerspoon 中转
        self.addr = addr
        self.port = port
        self._recording = False
        self._prev_consumed = False

    def _call_hammerspoon(self, func_name):
        """通过 osascript 调用 Hammerspoon 的全局 Lua 函数"""
        script = f'tell application "Hammerspoon" to execute lua code "{func_name}()"'
        try:
            subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                timeout=2
            )
        except Exception as e:
            print(f"[CapsWriter] Hammerspoon call failed ({func_name}): {e}")

    def update(self, state, last_state, mouse, keyboard):
        is_pressed = state['buttons'].get(self.controller_button, False)
        was_pressed = last_state['buttons'].get(self.controller_button, False) if last_state else False

        is_consumed = SHARED_CONSUMED_STATE.get(self.controller_button, False)

        # 如果正在录音，且 X 刚被标记为消费（用于组合键），则取消录音
        if self._recording and is_consumed and not self._prev_consumed:
            self._call_hammerspoon("CapsWriterGamepadStop")
            print(f"[CapsWriter] STOP via Hammerspoon (cancelled by combo)")
            self._recording = False

        # 按下边缘检测
        if is_pressed and not was_pressed:
            if not is_consumed:
                self._call_hammerspoon("CapsWriterGamepadStart")
                print(f"[CapsWriter] START via Hammerspoon")
                self._recording = True
            else:
                print(f"[CapsWriter] START ignored (consumed by combo)")
                self._recording = False

        # 松开边缘检测
        elif not is_pressed and was_pressed:
            if self._recording:
                self._call_hammerspoon("CapsWriterGamepadStop")
                print(f"[CapsWriter] STOP via Hammerspoon")
                self._recording = False

        self._prev_consumed = is_consumed

        # 在 X 松开时重置消费状态，确保下次单独按 X 能正常工作
        if not is_pressed and was_pressed:
            SHARED_CONSUMED_STATE.pop(self.controller_button, None)