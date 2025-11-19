import pygame

class GenericController:
    def __init__(self, custom_mapping, auto_activate_index=None):
        """
        :param custom_mapping: 加载的 JSON 配置
        :param auto_activate_index: (可选) 如果 main.py 已经检测到了手柄，传入其索引以实现自动激活
        """
        if not custom_mapping:
            raise ValueError("必须提供自定义映射 (custom_mapping)。")
        
        self.mapping = custom_mapping
        self.joysticks = {}
        self.active_joy = None

        # --- 映射配置 ---
        self.button_map = {}
        self.axis_map = {}
        self.dpad_config = self.mapping.get("dpad") 

        for key, value in self.mapping.items():
            if not value or not isinstance(value, list):
                continue
            input_type = value[0]
            input_index = value[1]
            if input_type == 'button':
                self.button_map[input_index] = key
            elif input_type == 'axis':
                self.axis_map[input_index] = key

        print("控制器接口已就绪。")

        # 自动扫描已连接设备
        for i in range(pygame.joystick.get_count()):
            self._add_joystick(i)

        # 尝试自动激活
        if auto_activate_index is not None:
            target_joy = None
            for joy in self.joysticks.values():
                if self.mapping.get('name') == joy.get_name():
                    target_joy = joy
                    break
            
            if target_joy is None and auto_activate_index < pygame.joystick.get_count():
                 try:
                     temp_joy = pygame.joystick.Joystick(auto_activate_index)
                     instance_id = temp_joy.get_instance_id()
                     if instance_id in self.joysticks:
                         target_joy = self.joysticks[instance_id]
                 except:
                     pass

            if target_joy:
                self.active_joy = target_joy
                print(f"⚡ 自动激活手柄: {self.active_joy.get_name()}")
            else:
                print("未能自动激活指定手柄，进入手动激活模式。")

        if not self.active_joy:
            print("等待手柄输入以激活...")
    
    def _add_joystick(self, device_index):
        try:
            joy = pygame.joystick.Joystick(device_index)
            instance_id = joy.get_instance_id()
            if instance_id in self.joysticks: return
            
            self.joysticks[instance_id] = joy
            if not joy.get_init():
                joy.init()
                
            print(f"系统挂载设备: '{joy.get_name()}' (ID: {instance_id})")
        except pygame.error as e:
            print(f"添加手柄 device_index {device_index} 时出错: {e}")
    
    def _remove_joystick(self, instance_id):
        if instance_id in self.joysticks:
            joy_name = self.joysticks[instance_id].get_name()
            print(f"\n设备 '{joy_name}' (ID: {instance_id}) 已断开。")
            del self.joysticks[instance_id]
        
        if self.active_joy and self.active_joy.get_instance_id() == instance_id:
            print("❌ 当前活动手柄已断开，控制已暂停。")
            self.active_joy = None
            print("请重新连接手柄或按任意键激活备用手柄...")
            return True
        return False

    def close(self):
        pass

    def read(self):
        active_joy_disconnected = False
        
        # 事件处理
        for event in pygame.event.get():
            if event.type == pygame.JOYDEVICEADDED:
                self._add_joystick(event.device_index)
                if not self.active_joy: 
                    print(f"新设备已连接。请按键激活...")
            
            elif event.type == pygame.JOYDEVICEREMOVED:
                if self._remove_joystick(event.instance_id): 
                    active_joy_disconnected = True
            
            elif self.active_joy is None:
                if (event.type == pygame.JOYBUTTONDOWN or
                   (event.type == pygame.JOYAXISMOTION and abs(event.value) > 0.8) or
                   (event.type == pygame.JOYHATMOTION and event.value != (0, 0))):
                    
                    joy_to_activate = self.joysticks.get(event.instance_id)
                    if joy_to_activate:
                        self.active_joy = joy_to_activate
                        print(f"\n🎮 手柄已激活: {self.active_joy.get_name()} (ID: {self.active_joy.get_instance_id()})")
                        break 
        
        if active_joy_disconnected: return {"status": "disconnected"}
        if self.active_joy is None: return None

        joy = self.active_joy
        
        # --- 1. 读取所有普通按钮 ---
        # 这会根据 JSON 读取 A, B, X, Y 以及 DPAD_UP, DPAD_DOWN (如果配置里有的话)
        buttons = {name: False for name in self.button_map.values()}
        for i in range(joy.get_numbuttons()):
            if joy.get_button(i):
                button_name = self.button_map.get(i)
                if button_name: buttons[button_name] = True
        
        # --- 2. 初始化通用方向键 ---
        # 确保输出字典里一定有这四个键，默认 False
        for direction in ['UP', 'DOWN', 'LEFT', 'RIGHT']:
            if direction not in buttons:
                buttons[direction] = False

        # --- 3. 处理特殊 D-pad 配置 (Switch Pro 等 Hat/Axis 形式) ---
        if self.dpad_config:
            if isinstance(self.dpad_config, list) and self.dpad_config[0] == 'hat':
                hat_index = self.dpad_config[1]
                if joy.get_numhats() > hat_index:
                    hat_val = joy.get_hat(hat_index)
                    if hat_val[1] == 1: buttons['UP'] = True
                    if hat_val[1] == -1: buttons['DOWN'] = True
                    if hat_val[0] == -1: buttons['LEFT'] = True
                    if hat_val[0] == 1: buttons['RIGHT'] = True
            elif isinstance(self.dpad_config, dict) and self.dpad_config.get('type') == 'axes':
                x_axis_idx = self.dpad_config.get('x_axis')
                y_axis_idx = self.dpad_config.get('y_axis')
                AXIS_THRESHOLD = 0.6 
                if x_axis_idx is not None and joy.get_numaxes() > x_axis_idx:
                    x_val = joy.get_axis(x_axis_idx)
                    if x_val > AXIS_THRESHOLD: buttons['RIGHT'] = True
                    if x_val < -AXIS_THRESHOLD: buttons['LEFT'] = True
                if y_axis_idx is not None and joy.get_numaxes() > y_axis_idx:
                    y_val = joy.get_axis(y_axis_idx)
                    if y_val < -AXIS_THRESHOLD: buttons['UP'] = True
                    if y_val > AXIS_THRESHOLD: buttons['DOWN'] = True

        # --- 4. <<< 修复部分 >>> 处理按钮形式的 D-pad (Xbox 等) ---
        # 如果上面的按钮循环检测到了 'DPAD_UP'，我们需要同步将通用的 'UP' 设为 True
        if buttons.get('DPAD_UP'): buttons['UP'] = True
        if buttons.get('DPAD_DOWN'): buttons['DOWN'] = True
        if buttons.get('DPAD_LEFT'): buttons['LEFT'] = True
        if buttons.get('DPAD_RIGHT'): buttons['RIGHT'] = True

        # --- 5. 读取轴数据 ---
        axes = {name: 0.0 for name in self.axis_map.values()}
        for i in range(joy.get_numaxes()):
            axis_name = self.axis_map.get(i)
            if axis_name:
                value = joy.get_axis(i)
                if axis_name in ['ly', 'ry']: value *= -1
                axes[axis_name] = value

        lt_val = (axes.get('lt', -1.0) + 1.0) / 2.0
        rt_val = (axes.get('rt', -1.0) + 1.0) / 2.0

        return {
            "buttons": buttons, 
            "lt": lt_val, 
            "rt": rt_val, 
            "lx": axes.get('lx', 0.0), 
            "ly": axes.get('ly', 0.0), 
            "rx": axes.get('rx', 0.0), 
            "ry": axes.get('ry', 0.0)
        }