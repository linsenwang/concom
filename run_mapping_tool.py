# ==============================================================================
# ======================= 交互式手柄映射工具=======================
# ==============================================================================
# 
# import pygame, json

MAPPING_FILE = "controller_map.json"

class TextPrint:
    def __init__(self): self.reset(); self.font = pygame.font.SysFont(None, 28); self.color = (230, 230, 230)
    def tprint(self, screen, text): screen.blit(self.font.render(text, True, self.color), (self.x, self.y)); self.y += self.line_height
    def reset(self): self.x = 20; self.y = 20; self.line_height = 30
    def indent(self): self.x += 20
    def unindent(self): self.x -= 20

def run_mapping_tool():
    pygame.init()
    screen = pygame.display.set_mode((800, 600)); pygame.display.set_caption("手柄映射工具"); clock = pygame.time.Clock(); text_print = TextPrint()
    joysticks = {}; tasks = [("A", "请按下 'A' 键"), ("B", "请按下 'B' 键"), ("X", "请按下 'X' 键"), ("Y", "请按下 'Y' 键"), ("LB", "请按下 '左肩键'"), ("RB", "请按下 '右肩键'"), ("MENU", "请按下 '菜单/Back' 键"), ("WIN", "请按下 '主页/Start' 键"), ("LS", "请按下 '左摇杆'"), ("RS", "请按下 '右摇杆'"), ("lt", "请扣下 '左扳机'"), ("rt", "请扣下 '右扳机'"), ("lx", "请左右移动 '左摇杆'"), ("ly", "请上下移动 '左摇杆'"), ("rx", "请左右移动 '右摇杆'"), ("ry", "请上下移动 '右摇杆'"), ("dpad", "请按下 '十字键'")]
    mapping = {}; task_i = 0; selected_joystick_id = None; done = False
    print("手柄映射工具已启动。请查看弹出的窗口并按提示操作。")
    while not done:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: done = True
            if event.type == pygame.JOYDEVICEADDED: joy = pygame.joystick.Joystick(event.device_index); joysticks[joy.get_instance_id()] = joy; print(f"检测到手柄: {joy.get_name()}")
            if event.type == pygame.JOYDEVICEREMOVED: print(f"手柄 (ID: {event.instance_id}) 已断开"); del joysticks[event.instance_id];
            if selected_joystick_id is None and len(joysticks) > 0:
                if (event.type == pygame.JOYBUTTONDOWN or (event.type == pygame.JOYAXISMOTION and abs(event.value) > 0.8) or (event.type == pygame.JOYHATMOTION and event.value != (0, 0))):
                    selected_joystick_id = event.instance_id; mapping['name'] = joysticks[selected_joystick_id].get_name(); print(f"开始为手柄 '{mapping['name']}' 映射...")
                continue
            if selected_joystick_id is not None and task_i < len(tasks):
                if not hasattr(event, 'instance_id') or event.instance_id != selected_joystick_id: continue
                key, msg = tasks[task_i]; detected = None
                if event.type == pygame.JOYBUTTONDOWN: detected = ("button", event.button)
                elif event.type == pygame.JOYAXISMOTION and abs(event.value) > 0.8: detected = ("axis", event.axis)
                elif event.type == pygame.JOYHATMOTION and event.value != (0, 0): detected = ("hat", event.hat)
                if detected and detected not in mapping.values(): mapping[key] = detected; print(f"  - 已映射 '{key}' -> {detected}"); task_i += 1
        screen.fill((30, 30, 30)); text_print.reset()
        if len(joysticks) == 0: text_print.tprint(screen, "请连接一个手柄...")
        elif selected_joystick_id is None: text_print.tprint(screen, "请按您想映射的手柄上的任意按键来开始。")
        elif task_i < len(tasks): text_print.tprint(screen, f"正在映射: {mapping.get('name', '')}"); text_print.tprint(screen, "-"*40); text_print.tprint(screen, f"步骤 {task_i + 1}/{len(tasks)}:"); text_print.tprint(screen, f"--> {tasks[task_i][1]}")
        else: text_print.tprint(screen, "映射完成!"); text_print.tprint(screen, f"将保存为 '{MAPPING_FILE}'。"); text_print.tprint(screen, "现在可以关闭此窗口。")
    if len(mapping) > 1:
        try:
            with open(MAPPING_FILE, 'w') as f: json.dump(mapping, f, indent=4)
            print(f"\n映射成功保存到 {MAPPING_FILE}")
        except Exception as e: print(f"\n错误：无法保存映射文件: {e}")
    pygame.quit()