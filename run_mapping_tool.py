# ==============================================================================
# ===================== 交互式手柄映射工具 (增强版) ====================
# ==============================================================================

import pygame
import json
import re

# --- 配置 ---
# 定义用于跳过当前步骤的键盘按键
SKIP_KEY = pygame.K_s

class TextPrint:
    """在屏幕上渲染文本的辅助类"""
    def __init__(self):
        self.reset()
        # 尝试加载常见中文字体，以确保提示信息正常显示
        font_names = ['Microsoft YaHei', 'SimHei', 'Arial Unicode MS', None] # None 是系统默认字体
        for font_name in font_names:
            try:
                self.font = pygame.font.SysFont(font_name, 28)
                # print(f"成功加载字体: {font_name}") # 调试时可以取消注释
                break
            except:
                continue
        self.color = (230, 230, 230)

    def tprint(self, screen, text):
        """在屏幕上打印一行文本"""
        screen.blit(self.font.render(text, True, self.color), (self.x, self.y))
        self.y += self.line_height

    def reset(self):
        """重置打印位置到屏幕左上角"""
        self.x = 20
        self.y = 20
        self.line_height = 30

    def indent(self):
        self.x += 20

    def unindent(self):
        self.x -= 20

def sanitize_filename(name):
    """根据设备名称生成一个安全的文件名"""
    # 移除非法字符，只保留字母、数字、下划线、连字符和空格
    s = re.sub(r'[^\w\s-]', '', name).strip()
    # 将空格或多个连字符替换为单个下划线
    s = re.sub(r'[-\s]+', '_', s)
    return f"map_{s}.json"

def run_mapping_tool():
    pygame.init()
    screen = pygame.display.set_mode((800, 600))
    pygame.display.set_caption("手柄映射工具 (增强版)")
    clock = pygame.time.Clock()
    text_print = TextPrint()

    joysticks = {}
    tasks = [
        ("A", "请按下 'A' 键 (通常是底部按钮)"),
        ("B", "请按下 'B' 键 (通常是右侧按钮)"),
        ("X", "请按下 'X' 键 (通常是左侧按钮)"),
        ("Y", "请按下 'Y' 键 (通常是顶部按钮)"),
        ("LB", "请按下 '左肩键' (L1)"),
        ("RB", "请按下 '右肩键' (R1)"),
        ("MENU", "请按下 '菜单/Back/Select' 键"),
        ("WIN", "请按下 '主页/Start' 键"),
        ("LS", "请按下 '左摇杆' (L3)"),
        ("RS", "请按下 '右摇杆' (R3)"),
        ("lt", "请完全扣下 '左扳机' (L2)"),
        ("rt", "请完全扣下 '右扳机' (R2)"),
        ("lx", "请将 '左摇杆' 水平移动到底"),
        ("ly", "请将 '左摇杆' 垂直移动到底"),
        ("rx", "请将 '右摇杆' 水平移动到底"),
        ("ry", "请将 '右摇杆' 垂直移动到底"),
        ("dpad", "请按下 '十字键' 的任意方向")
    ]

    mapping = {}
    task_i = 0
    selected_joystick_id = None
    output_filename = None # <--- 新增: 用于存储动态生成的文件名
    done = False

    print("手柄映射工具已启动。请查看弹出的窗口并按提示操作。")

    while not done:
        # --- 事件处理循环 ---
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                done = True

            # --- 新增: 监听键盘事件以实现“跳过”功能 ---
            if event.type == pygame.KEYDOWN:
                if event.key == SKIP_KEY and selected_joystick_id is not None and task_i < len(tasks):
                    key, msg = tasks[task_i]
                    mapping[key] = None  # 将跳过的映射记为 None
                    print(f"  - 已跳过 '{key}'")
                    task_i += 1

            if event.type == pygame.JOYDEVICEADDED:
                joy = pygame.joystick.Joystick(event.device_index)
                joysticks[joy.get_instance_id()] = joy
                print(f"检测到手柄: {joy.get_name()}")

            if event.type == pygame.JOYDEVICEREMOVED:
                print(f"手柄 (ID: {event.instance_id}) 已断开")
                if event.instance_id in joysticks:
                    del joysticks[event.instance_id]
                # 如果断开的是正在映射的手柄，则重置状态
                if event.instance_id == selected_joystick_id:
                    selected_joystick_id = None
                    task_i = 0
                    mapping = {}
                    output_filename = None
                    print("当前映射的手柄已断开，请重新开始。")

            # 步骤1: 等待用户选择一个手柄
            if selected_joystick_id is None and len(joysticks) > 0:
                if (event.type == pygame.JOYBUTTONDOWN or
                   (event.type == pygame.JOYAXISMOTION and abs(event.value) > 0.8) or
                   (event.type == pygame.JOYHATMOTION and event.value != (0, 0))):
                    selected_joystick_id = event.instance_id
                    mapping['name'] = joysticks[selected_joystick_id].get_name()
                    
                    # <--- 修改: 根据手柄名称生成文件名
                    output_filename = sanitize_filename(mapping['name'])
                    
                    print(f"开始为手柄 '{mapping['name']}' 映射...")
                    print(f"配置文件将保存为: {output_filename}")
                continue

            # 步骤2: 执行映射任务
            if selected_joystick_id is not None and task_i < len(tasks):
                if not hasattr(event, 'instance_id') or event.instance_id != selected_joystick_id:
                    continue

                key, msg = tasks[task_i]
                detected = None

                # 检测输入类型
                if event.type == pygame.JOYBUTTONDOWN:
                    detected = ("button", event.button)
                elif event.type == pygame.JOYAXISMOTION and abs(event.value) > 0.8:
                    detected = ("axis", event.axis)
                elif event.type == pygame.JOYHATMOTION and event.value != (0, 0):
                    detected = ("hat", event.hat)

                # 如果检测到新的、未被映射过的输入，则记录并进入下一步
                if detected and detected not in mapping.values():
                    mapping[key] = detected
                    print(f"  - 已映射 '{key}' -> {detected}")
                    task_i += 1

        # --- 屏幕渲染 ---
        screen.fill((30, 30, 30))
        text_print.reset()

        if len(joysticks) == 0:
            text_print.tprint(screen, "请连接一个手柄...")
        elif selected_joystick_id is None:
            text_print.tprint(screen, "请按您想映射的手柄上的任意键来开始。")
        elif task_i < len(tasks):
            text_print.tprint(screen, f"正在映射: {mapping.get('name', '')}")
            text_print.tprint(screen, "-"*50)
            text_print.tprint(screen, f"步骤 {task_i + 1}/{len(tasks)}:")
            text_print.tprint(screen, f"--> {tasks[task_i][1]}")
            text_print.tprint(screen, "")
            # <--- 新增: 屏幕上显示跳过提示
            text_print.tprint(screen, f"(或按键盘上的 'S' 键跳过此项)")
        else:
            text_print.tprint(screen, "映射完成!")
            # <--- 修改: 显示动态文件名
            text_print.tprint(screen, f"将保存为 '{output_filename}'。")
            text_print.tprint(screen, "现在可以关闭此窗口。")

        pygame.display.flip()
        clock.tick(60)

    # --- 保存映射文件 ---
    # <--- 修改: 使用动态文件名进行保存
    if len(mapping) > 1 and output_filename:
        try:
            with open(output_filename, 'w', encoding='utf-8') as f:
                json.dump(mapping, f, indent=4, ensure_ascii=False)
            print(f"\n映射成功保存到 {output_filename}")
        except Exception as e:
            print(f"\n错误：无法保存映射文件: {e}")

    pygame.quit()


if __name__ == '__main__':
    run_mapping_tool()