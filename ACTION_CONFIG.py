from Action import *
from pynput.mouse import Button
from pynput.keyboard import Key

ACTION_CONFIG = [
MouseMoveAction(x_axis='lx', y_axis='ly', sensitivity=30, deadzone=0.15), 
MouseMoveAction(x_axis='rx', y_axis='ry', sensitivity=30, deadzone=0.15), 
ClickAction(controller_button='A', mouse_button=Button.left), 
ClickAction(controller_button='B', mouse_button=Button.right), 
AnalogAsButtonScrollAction(axis_name='lt', threshold=0.01, scroll_speed=-15, initial_delay=0.3, repeat_rate=0.05), 
AnalogAsButtonScrollAction(axis_name='rt', threshold=0.01, scroll_speed=15, initial_delay=0.3, repeat_rate=0.05), 
ScrollAction(controller_button='RB', scroll_speed=-15, initial_delay=0.3, repeat_rate=0.05), 
ScrollAction(controller_button='LB', scroll_speed=15, initial_delay=0.3, repeat_rate=0.05), 
ScrollAction(controller_button='UP', scroll_speed=-15, initial_delay=0.4, repeat_rate=0.1), 
ScrollAction(controller_button='DOWN', scroll_speed=15, initial_delay=0.4, repeat_rate=0.1), 
KeyboardAction(controller_button='X', key=Key.left, modifier=Key.cmd), 
KeyboardAction(controller_button='Y', key=Key.right, modifier=Key.cmd), 
# KeyboardAction(controller_button='RIGHT', key=Key.tab), 
# KeyboardAction(controller_button='LEFT', key=Key.tab, modifier=Key.shift), 
KeyboardAction(controller_button='RIGHT', key=Key.right), 
KeyboardAction(controller_button='LEFT', key=Key.left), 
KeyboardAction(controller_button='WIN', key=Key.enter), 
KeyboardAction(controller_button='MENU', key='q', modifier=[Key.cmd, Key.ctrl]), 
KeyboardAction(controller_button='RS', key='w', modifier=Key.cmd),
    ]