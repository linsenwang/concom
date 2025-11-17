import time

class Action:
    def update(self, state, last_state, mouse, keyboard):
        pass

import Quartz
def get_screen_size():
    main = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID())
    return int(main.size.width), int(main.size.height)

SCREEN_W, SCREEN_H = get_screen_size()

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

            # 新位置（做钳制）
            new_x = min(max(0, x + dx), SCREEN_W - 1)
            new_y = min(max(0, y + dy), SCREEN_H - 1)

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