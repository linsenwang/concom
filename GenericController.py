import pygame

class GenericController:
    def __init__(self, custom_mapping, auto_activate_index=None):
        pygame.joystick.init()
        
        if not custom_mapping:
            raise ValueError("必须提供自定义映射 (custom_mapping)。")
        
        self.mapping = custom_mapping
        self.joysticks = {}
        self.active_joy = None

        # --- 映射配置 ---
        self.button_map = {}
        self.axis_map = {}
        # 这里获取配置中的 dpad 设置
        self.dpad_config = self.mapping.get("dpad") 

        # 记录扳机键是否完成初始化（是否被按过）
        self.trigger_initialized = {'lt': False, 'rt': False}

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
        
        # 尝试自动激活指定索引的设备
        if auto_activate_index is not None:
            # 遍历当前已识别的 joystick 对象
            for j_id, joy in self.joysticks.items():
                # 简单通过设备索引判断（注意：instance_id 和 device_index 不同，这里仅作简单尝试）
                # 实际场景中通常通过按键激活更稳妥
                pass

        if not self.active_joy:
            print("等待手柄输入以激活...")

    def read(self):
        active_joy_disconnected = False
        
        # --- 事件处理 ---
        for event in pygame.event.get():
            if event.type == pygame.JOYDEVICEADDED:
                self._add_joystick(event.device_index)
                if not self.active_joy: 
                    print(f"新设备已连接。请按键激活...")
            
            elif event.type == pygame.JOYDEVICEREMOVED:
                if self._remove_joystick(event.instance_id): 
                    active_joy_disconnected = True
            
            # 激活逻辑
            elif self.active_joy is None:
                if (event.type == pygame.JOYBUTTONDOWN or
                   (event.type == pygame.JOYAXISMOTION and abs(event.value) > 0.8) or
                   (event.type == pygame.JOYHATMOTION and event.value != (0, 0))):
                    
                    joy_to_activate = self.joysticks.get(event.instance_id)
                    if joy_to_activate:
                        self.active_joy = joy_to_activate
                        # 激活新/重连手柄时，重置扳机状态
                        self.trigger_initialized = {'lt': False, 'rt': False}
                        print(f"\n🎮 手柄已激活: {self.active_joy.get_name()} (ID: {self.active_joy.get_instance_id()})")
                        break 
        
        if active_joy_disconnected: return {"status": "disconnected"}
        if self.active_joy is None: return None

        joy = self.active_joy
        
        # --- 1. 读取所有普通按钮 ---
        buttons = {name: False for name in self.button_map.values()}
        for i in range(joy.get_numbuttons()):
            if joy.get_button(i):
                button_name = self.button_map.get(i)
                if button_name: buttons[button_name] = True
        
        # --- 2. 初始化通用方向键 ---
        for direction in ['UP', 'DOWN', 'LEFT', 'RIGHT']:
            if direction not in buttons:
                buttons[direction] = False

        # --- 3. 处理特殊 D-pad 配置 (修复部分) ---
        if self.dpad_config:
            # [修复] 情况 A: JSON 配置为字典 (针对 Switch Pro / 轴模拟方向)
            if isinstance(self.dpad_config, dict) and self.dpad_config.get("type") == "axes":
                x_axis_idx = self.dpad_config.get("x_axis")
                y_axis_idx = self.dpad_config.get("y_axis")
                threshold = 0.5  # 轴死区

                # 读取 X 轴 (左右)
                if x_axis_idx is not None and x_axis_idx < joy.get_numaxes():
                    val = joy.get_axis(x_axis_idx)
                    if val < -threshold: buttons['LEFT'] = True
                    if val > threshold: buttons['RIGHT'] = True

                # 读取 Y 轴 (上下)
                if y_axis_idx is not None and y_axis_idx < joy.get_numaxes():
                    val = joy.get_axis(y_axis_idx)
                    if val < -threshold: buttons['UP'] = True
                    if val > threshold: buttons['DOWN'] = True

            # [保持] 情况 B: JSON 配置为列表 (针对 HAT/苦力帽 配置)
            elif isinstance(self.dpad_config, list) and self.dpad_config[0] == 'hat':
                hat_index = self.dpad_config[1]
                if joy.get_numhats() > hat_index:
                    hat_val = joy.get_hat(hat_index)
                    if hat_val[1] == 1: buttons['UP'] = True
                    if hat_val[1] == -1: buttons['DOWN'] = True
                    if hat_val[0] == -1: buttons['LEFT'] = True
                    if hat_val[0] == 1: buttons['RIGHT'] = True

        # --- 4. 处理按钮形式的 D-pad ---
        # 支持 "DPAD_UP": ["button", 11] 这种映射，与上面的轴逻辑是“或”的关系
        if buttons.get('DPAD_UP'): buttons['UP'] = True
        if buttons.get('DPAD_DOWN'): buttons['DOWN'] = True
        if buttons.get('DPAD_LEFT'): buttons['LEFT'] = True
        if buttons.get('DPAD_RIGHT'): buttons['RIGHT'] = True

        # --- 5. 读取轴数据 ---
        axes = {}
        for name in self.axis_map.values():
            if name in ['lt', 'rt']:
                axes[name] = -1.0 # 默认松开
            else:
                axes[name] = 0.0

        for i in range(joy.get_numaxes()):
            axis_name = self.axis_map.get(i)
            if axis_name:
                value = joy.get_axis(i)

                # Xbox 扳机键初始化修正
                if axis_name in ['lt', 'rt']:
                    if value == 0.0 and not self.trigger_initialized[axis_name]:
                        value = -1.0
                    elif value != 0.0:
                        self.trigger_initialized[axis_name] = True
                
                if axis_name in ['ly', 'ry']: value *= -1
                axes[axis_name] = value

        # 计算归一化数值 (0.0 - 1.0)
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

    # --- 辅助方法 & 资源释放 (补全) ---

    def _add_joystick(self, device_index):
        try:
            joy = pygame.joystick.Joystick(device_index)
            instance_id = joy.get_instance_id()
            if instance_id in self.joysticks: return
            self.joysticks[instance_id] = joy
            if not joy.get_init(): joy.init()
            print(f"系统挂载设备: '{joy.get_name()}' (ID: {instance_id})")
        except pygame.error as e:
            print(f"添加手柄错误: {e}")

    def _remove_joystick(self, instance_id):
        if instance_id in self.joysticks:
            joy_name = self.joysticks[instance_id].get_name()
            print(f"\n设备 '{joy_name}' (ID: {instance_id}) 已断开。")
            del self.joysticks[instance_id]
        
        if self.active_joy and self.active_joy.get_instance_id() == instance_id:
            print("❌ 当前活动手柄已断开。")
            self.active_joy = None
            return True
        return False

    def close(self):
        """释放手柄资源"""
        self.active_joy = None
        self.joysticks.clear()
        # 退出 pygame 的 joystick 模块，防止程序退出时报错
        if pygame.joystick.get_init():
            pygame.joystick.quit()
        print("控制器资源已释放。")