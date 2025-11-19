import pygame

class GenericController:
    def __init__(self, custom_mapping, auto_activate_index=None):
        # ... (前半部分代码保持不变) ...
        if not custom_mapping:
            raise ValueError("必须提供自定义映射 (custom_mapping)。")
        
        self.mapping = custom_mapping
        self.joysticks = {}
        self.active_joy = None

        # --- 映射配置 ---
        self.button_map = {}
        self.axis_map = {}
        self.dpad_config = self.mapping.get("dpad") 

        # [新增] 记录扳机键是否完成初始化（是否被按过）
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

        # ... (自动扫描代码保持不变) ...
        # 自动扫描已连接设备
        for i in range(pygame.joystick.get_count()):
            self._add_joystick(i)
        
        # ... (自动激活代码保持不变，略过以节省篇幅) ...
        
        # 尝试自动激活 (这里省略了中间未修改的自动激活逻辑)
        if auto_activate_index is not None:
             # ... (保持原有逻辑) ...
             # 假设这里 active_joy 被赋值了
             pass

        if not self.active_joy:
            print("等待手柄输入以激活...")

    # ... (_add_joystick, _remove_joystick, close 方法保持不变) ...

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
                        # [新增] 激活新/重连手柄时，重置扳机状态，防止继承之前的错误状态
                        self.trigger_initialized = {'lt': False, 'rt': False}
                        print(f"\n🎮 手柄已激活: {self.active_joy.get_name()} (ID: {self.active_joy.get_instance_id()})")
                        break 
        
        if active_joy_disconnected: return {"status": "disconnected"}
        if self.active_joy is None: return None

        joy = self.active_joy
        
        # --- 1. 读取所有普通按钮 --- (保持不变)
        buttons = {name: False for name in self.button_map.values()}
        for i in range(joy.get_numbuttons()):
            if joy.get_button(i):
                button_name = self.button_map.get(i)
                if button_name: buttons[button_name] = True
        
        # --- 2. 初始化通用方向键 --- (保持不变)
        for direction in ['UP', 'DOWN', 'LEFT', 'RIGHT']:
            if direction not in buttons:
                buttons[direction] = False

        # --- 3. 处理特殊 D-pad 配置 --- (保持不变)
        if self.dpad_config:
            # ... (省略未修改代码) ...
            if isinstance(self.dpad_config, list) and self.dpad_config[0] == 'hat':
                hat_index = self.dpad_config[1]
                if joy.get_numhats() > hat_index:
                    hat_val = joy.get_hat(hat_index)
                    if hat_val[1] == 1: buttons['UP'] = True
                    if hat_val[1] == -1: buttons['DOWN'] = True
                    if hat_val[0] == -1: buttons['LEFT'] = True
                    if hat_val[0] == 1: buttons['RIGHT'] = True
            # ... (省略 axes 类型 dpad 代码) ...

        # --- 4. 处理按钮形式的 D-pad --- (保持不变)
        if buttons.get('DPAD_UP'): buttons['UP'] = True
        if buttons.get('DPAD_DOWN'): buttons['DOWN'] = True
        if buttons.get('DPAD_LEFT'): buttons['LEFT'] = True
        if buttons.get('DPAD_RIGHT'): buttons['RIGHT'] = True

        # --- 5. 读取轴数据 (核心修改部分) ---
        # 显式初始化 LT/RT 为 -1.0 (松开状态)，其他轴为 0.0
        axes = {}
        for name in self.axis_map.values():
            if name in ['lt', 'rt']:
                axes[name] = -1.0
            else:
                axes[name] = 0.0

        for i in range(joy.get_numaxes()):
            axis_name = self.axis_map.get(i)
            if axis_name:
                value = joy.get_axis(i)

                # [核心修复] Xbox 扳机键初始化修正
                if axis_name in ['lt', 'rt']:
                    # 如果值为 0.0 且从未被初始化过，强制视为 -1.0 (松开)
                    if value == 0.0 and not self.trigger_initialized[axis_name]:
                        value = -1.0
                    # 如果值不为 0.0，说明用户已经动过了，标记为已初始化
                    elif value != 0.0:
                        self.trigger_initialized[axis_name] = True
                
                if axis_name in ['ly', 'ry']: value *= -1
                axes[axis_name] = value

        # 计算归一化数值 (0.0 - 1.0)
        # 如果上面被修正为 -1.0，这里的结果就是 0.0，解决了自动移动问题
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

    # 补充：未修改的辅助函数需要包含在类中
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