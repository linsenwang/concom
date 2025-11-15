import pygame

class GenericController:
    def __init__(self, custom_mapping):
        if not custom_mapping:
            raise ValueError("必须提供自定义映射 (custom_mapping)。")
        
        self.mapping = custom_mapping
        
        self.joysticks = {}
        self.active_joy = None

        self.button_map = {v[1]: k for k, v in self.mapping.items() if v[0] == 'button'}
        self.axis_map = {v[1]: k for k, v in self.mapping.items() if v[0] == 'axis'}
        self.hat_map_index = self.mapping.get("dpad", (None, -1))[1]

        pygame.init()
        pygame.joystick.init()
        print("Pygame 已初始化。")
        
        # 重要修改：移除初始化时的 get_count() 循环
        # 完全依赖事件驱动来检测手柄
        print("等待手柄连接事件...")
        
        if not self.joysticks:
            print("未检测到手柄。请确保手柄已连接，然后移动或按下任意键...")

    def _add_joystick(self, device_index):
        """
        添加一个新检测到的手柄。
        """
        try:
            joy = pygame.joystick.Joystick(device_index)
            instance_id = joy.get_instance_id()

            if instance_id in self.joysticks:
                return

            # 直接添加设备
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
            if self.joysticks:
                 print(f"剩余 {len(self.joysticks)} 个设备。请再次选择一个手柄来激活...")
            return True
        return False

    def close(self):
        pygame.quit()

    def read(self):
        active_joy_disconnected = False

        for event in pygame.event.get():
            if event.type == pygame.JOYDEVICEADDED:
                print(f"检测到新设备连接，device_index: {event.device_index}")
                self._add_joystick(event.device_index)
                if not self.active_joy:
                    print("请移动或按下您想使用的手柄上的任意键来激活控制...")

            elif event.type == pygame.JOYDEVICEREMOVED:
                print(f"检测到设备断开，instance_id: {event.instance_id}")
                if self._remove_joystick(event.instance_id):
                    active_joy_disconnected = True

            elif self.active_joy is None:
                if (event.type == pygame.JOYBUTTONDOWN or
                   (event.type == pygame.JOYAXISMOTION and abs(event.value) > 0.8) or
                   (event.type == pygame.JOYHATMOTION and event.value != (0, 0))):
                    
                    joy_to_activate = self.joysticks.get(event.instance_id)
                    if joy_to_activate:
                        # 有效性检查
                        if joy_to_activate.get_numbuttons() == 0 and \
                           joy_to_activate.get_numaxes() == 0 and \
                           joy_to_activate.get_numhats() == 0:
                            
                            print(f"检测到来自 '{joy_to_activate.get_name()}' 的输入，但该设备无按钮/摇杆，无法激活。可能仍在初始化...")
                            continue

                        # 验证通过，执行激活
                        self.active_joy = joy_to_activate
                        print(f"\n🎮 手柄已激活: {self.active_joy.get_name()} (ID: {self.active_joy.get_instance_id()})")
                        
                        if self.mapping['name'].split(' ')[0].lower() not in self.active_joy.get_name().lower():
                            print(f"警告：激活的手柄 '{self.active_joy.get_name()}' 可能与映射文件中的 '{self.mapping['name']}' 不匹配。")
                        print("已成功加载自定义映射。")
                        break 

        if active_joy_disconnected:
            return {"status": "disconnected"}

        if self.active_joy is None:
            return None

        # 轮询逻辑
        joy = self.active_joy
        buttons = {name: False for name in self.button_map.values()}
        for i in range(joy.get_numbuttons()):
            if joy.get_button(i):
                button_name = self.button_map.get(i)
                if button_name: buttons[button_name] = True
        
        if self.hat_map_index != -1 and joy.get_numhats() > self.hat_map_index:
            hat = joy.get_hat(self.hat_map_index)
            buttons['UP'], buttons['DOWN'], buttons['LEFT'], buttons['RIGHT'] = (hat[1] == 1), (hat[1] == -1), (hat[0] == -1), (hat[0] == 1)
        
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