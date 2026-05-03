from Action import *
from pynput.mouse import Button
from pynput.keyboard import Key

rate = 0.8

ACTION_CONFIG = [
# ================= 1. 组合键逻辑 (必须放在最前面) =================

# 这会拦截 'RIGHT' 的原功能，并标记 'X' 被消费
ComboKeyAction(mod_btn='X', trigger_btn='RIGHT', key=Key.right, modifier=[Key.cmd, Key.alt]),
ComboKeyAction(mod_btn='X', trigger_btn='LEFT', key=Key.left, modifier=[Key.cmd, Key.alt]),
ComboKeyAction(mod_btn='X', trigger_btn='UP', key=Key.tab, modifier=Key.shift),
ComboKeyAction(mod_btn='X', trigger_btn='DOWN', key=Key.tab),

# ================= 2. 摇杆与鼠标移动 (不受组合键影响) =================
MouseMoveAction(x_axis='lx', y_axis='ly', sensitivity=30 * rate, deadzone=0.15), 
MouseMoveAction(x_axis='rx', y_axis='ry', sensitivity=30 * rate, deadzone=0.15), 

# ================= 3. 普通点击与滚动 =================
ClickAction(controller_button='A', mouse_button=Button.left), 
ClickAction(controller_button='B', mouse_button=Button.right), 

AnalogAsButtonScrollAction(axis_name='lt', threshold=0.01, scroll_speed=-15, initial_delay=0.3, repeat_rate=0.05), 
AnalogAsButtonScrollAction(axis_name='rt', threshold=0.01, scroll_speed=15, initial_delay=0.3, repeat_rate=0.05), 

ScrollAction(controller_button='RB', scroll_speed=-15, initial_delay=0.3, repeat_rate=0.05), 
ScrollAction(controller_button='LB', scroll_speed=15, initial_delay=0.3, repeat_rate=0.05), 
ScrollAction(controller_button='UP', scroll_speed=-15, initial_delay=0.4, repeat_rate=0.1), 
ScrollAction(controller_button='DOWN', scroll_speed=15, initial_delay=0.4, repeat_rate=0.1), 

# ================= 4. 按键映射 (注意 X, LEFT, RIGHT 的变化) =================

# [Smart] X 键：按住开始录音，松开结束识别（对讲机模式）
# 保留 X + 方向键 的组合键功能（切桌面、Tab 切换）
UDPCapsWriterAction(controller_button='X'), 

# Y 键保持不变
# KeyboardAction(controller_button='Y', key=Key.right, modifier=Key.cmd), 
KeyboardAction(controller_button='Y', key=Key.enter), 

# [普通] RIGHT 和 LEFT
# 如果上面触发了 X+RIGHT，这里的 RIGHT 会被 ComboKeyAction 屏蔽，不会触发
KeyboardAction(controller_button='RIGHT', key=Key.right), 
KeyboardAction(controller_button='LEFT', key=Key.left), 

KeyboardAction(controller_button='HOME', key=Key.enter), 
# KeyboardAction(controller_button='MENU', key='q', modifier=[Key.cmd, Key.ctrl]), 
KeyboardAction(controller_button='MENU', key='w', modifier=Key.cmd),
KeyboardAction(controller_button='RS', key='w', modifier=Key.cmd),


]