import pygame

class GenericController:
    def __init__(self, custom_mapping):
        if not custom_mapping:
            raise ValueError("必须提供自定义映射 (custom_mapping)。")
        
        self.mapping = custom_mapping
        self.joysticks = {}
        self.active_joy = None

        # --- <<< MODIFIED: 初始化逻辑更具弹性 >>> ---
        # 移除旧的 button/axis map，因为它们在 D-Pad 按钮模式下会出错
        self.button_map = {}
        self.axis_map = {}
        # 直接存储 dpad 配置，可以是 list, dict, 或 None
        self.dpad_config = self.mapping.get("dpad") 

        # 动态构建 button_map 和 axis_map
        for key, value in self.mapping.items():
            if not value or not isinstance(value, list):
                continue
            
            input_type = value[0]
            input_index = value[1]

            if input_type == 'button':
                self.button_map[input_index] = key
            elif input_type == 'axis':
                self.axis_map[input_index] = key

        pygame.init()
        pygame.joystick.init()
        print("Pygame 已初始化。")
        print("等待手柄连接事件...")
        if not self.joysticks:
            print("未检测到手柄。请确保手柄已连接，然后移动或按下任意键...")
    
    # _add_joystick, _remove_joystick, close 方法保持不变
    def _add_joystick(self, device_index):
        try:
            joy = pygame.joystick.Joystick(device_index)
            instance_id = joy.get_instance_id()
            if instance_id in self.joysticks: return
            self.joysticks[instance_id] = joy
            print(f"发现设备: '{joy.get_name()}' (ID: {instance_id})，等待输入以激活。")
        except pygame.error as e:
            print(f"添加手柄 device_index {device_index} 时出错: {e}")
    
    def _remove_joystick(self, instance_id):
        if instance_id in self.joysticks:
            joy_name = self.joysticks[instance_id].get_name()
            print(f"\n设备 '{joy_name}' (ID: {instance_id}) 已断开。")
            del self.joysticks[instance_id]
        if self.active_joy and self.active_joy.get_instance_id() == instance_id:
            print("当前活动手柄已断开，控制已暂停。")
            self.active_joy = None
            if self.joysticks: print(f"剩余 {len(self.joysticks)} 个设备。请再次选择一个手柄来激活...")
            return True
        return False

    def close(self):
        pygame.quit()

    def read(self):
        active_joy_disconnected = False
        for event in pygame.event.get():
            if event.type == pygame.JOYDEVICEADDED:
                self._add_joystick(event.device_index)
                if not self.active_joy: print("请移动或按下您想使用的手柄上的任意键来激活控制...")
            elif event.type == pygame.JOYDEVICEREMOVED:
                if self._remove_joystick(event.instance_id): active_joy_disconnected = True
            elif self.active_joy is None:
                if (event.type == pygame.JOYBUTTONDOWN or
                   (event.type == pygame.JOYAXISMOTION and abs(event.value) > 0.8) or
                   (event.type == pygame.JOYHATMOTION and event.value != (0, 0))):
                    joy_to_activate = self.joysticks.get(event.instance_id)
                    if joy_to_activate:
                        if joy_to_activate.get_numbuttons() == 0 and joy_to_activate.get_numaxes() == 0 and joy_to_activate.get_numhats() == 0:
                            print(f"检测到来自 '{joy_to_activate.get_name()}' 的输入，但该设备无按钮/摇杆，无法激活。")
                            continue
                        self.active_joy = joy_to_activate
                        print(f"\n🎮 手柄已激活: {self.active_joy.get_name()} (ID: {self.active_joy.get_instance_id()})")
                        if self.mapping['name'].split(' ')[0].lower() not in self.active_joy.get_name().lower():
                            print(f"警告：激活的手柄 '{self.active_joy.get_name()}' 可能与映射文件中的 '{self.mapping['name']}' 不匹配。")
                        print("已成功加载自定义映射。")
                        break 
        
        if active_joy_disconnected: return {"status": "disconnected"}
        if self.active_joy is None: return None

        joy = self.active_joy
        buttons = {name: False for name in self.button_map.values()}
        for i in range(joy.get_numbuttons()):
            if joy.get_button(i):
                button_name = self.button_map.get(i)
                if button_name: buttons[button_name] = True
        
        # --- <<< MODIFIED: 统一的 D-Pad 处理逻辑 >>> ---
        # 为D-Pad按键预留位置
        buttons.update({'UP': False, 'DOWN': False, 'LEFT': False, 'RIGHT': False})

        if self.dpad_config:
            # 兼容模式1: Hat Switch
            if isinstance(self.dpad_config, list) and self.dpad_config[0] == 'hat':
                hat_index = self.dpad_config[1]
                if joy.get_numhats() > hat_index:
                    hat_val = joy.get_hat(hat_index)
                    buttons['UP'] = hat_val[1] == 1
                    buttons['DOWN'] = hat_val[1] == -1
                    buttons['LEFT'] = hat_val[0] == -1
                    buttons['RIGHT'] = hat_val[0] == 1
            # 兼容模式2: Axes
            elif isinstance(self.dpad_config, dict) and self.dpad_config.get('type') == 'axes':
                x_axis_idx = self.dpad_config.get('x_axis')
                y_axis_idx = self.dpad_config.get('y_axis')
                
                # 设置一个阈值来避免摇杆漂移
                AXIS_THRESHOLD = 0.6 
                
                if x_axis_idx is not None and joy.get_numaxes() > x_axis_idx:
                    x_val = joy.get_axis(x_axis_idx)
                    buttons['RIGHT'] = x_val > AXIS_THRESHOLD
                    buttons['LEFT'] = x_val < -AXIS_THRESHOLD

                if y_axis_idx is not None and joy.get_numaxes() > y_axis_idx:
                    y_val = joy.get_axis(y_axis_idx)
                    # Pygame中，Y轴向上通常是负值
                    buttons['UP'] = y_val < -AXIS_THRESHOLD
                    buttons['DOWN'] = y_val > AXIS_THRESHOLD

        axes = {name: 0.0 for name in self.axis_map.values()}
        for i in range(joy.get_numaxes()):
            axis_name = self.axis_map.get(i)
            if axis_name:
                value = joy.get_axis(i)
                if axis_name in ['ly', 'ry']: value *= -1
                axes[axis_name] = value

        lt_val = (axes.get('lt', -1.0) + 1.0) / 2.0
        rt_val = (axes.get('rt', -1.0) + 1.0) / 2.0

        return {"buttons": buttons, "lt": lt_val, "rt": rt_val, "lx": axes.get('lx', 0.0), "ly": axes.get('ly', 0.0), "rx": axes.get('rx', 0.0), "ry": axes.get('ry', 0.0)}