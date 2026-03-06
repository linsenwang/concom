# ==============================================================================
# ======================== 依赖导入 ========================================
# ==============================================================================
import os
import sys
import json
import time
import ctypes
import re
import pygame # 提前导入

pygame.init()
pygame.display.init()
pygame.display.set_allow_screensaver(True)

# --- 模式检测 ---
IS_MAPPING_MODE = '--map' in sys.argv

# 设置环境变量必须在 pygame.init 之前
if not IS_MAPPING_MODE:
    # 隐藏 pygame 欢迎语
    os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
    # 如果是无头模式或需要 dummy 驱动可取消注释，但通常 Windows/Mac 需要默认驱动
    # os.environ["SDL_VIDEODRIVER"] = "dummy"

from pynput.mouse import Button, Controller as MouseController
from pynput.keyboard import Key, Controller as KeyboardController

try:
    if not IS_MAPPING_MODE:
        ctypes.CDLL(None).SDL_EnableScreenSaver()
except Exception:
    pass

from run_mapping_tool import run_mapping_tool
from GenericController import GenericController
from Action import *
from ACTION_CONFIG import ACTION_CONFIG

# ==============================================================================
# ======================== 辅助函数 ============================================
# ==============================================================================
def sanitize_filename(name):
    """Generate a safe filename from the device name."""
    s = re.sub(r'[^\w\s-]', '', name).strip()
    s = re.sub(r'[-\s]+', '_', s)
    return f"map_{s}.json"

def setup_and_find_config():
    """
    初始化 Pygame，等待手柄连接，并返回(映射数据, 映射文件名, 设备索引)。
    不会退出 Pygame。
    """
    print("正在初始化系统...")
    pygame.init()
    pygame.joystick.init()

    print("等待手柄连接...", end="", flush=True)
    
    # 简单的等待循环
    while pygame.joystick.get_count() == 0:
        pygame.event.pump() # 处理内部事件，防止无响应
        time.sleep(0.5)
        # print(".", end="", flush=True)
    
    print("\n检测到手柄连接！")
    
    # 默认选择第 0 号设备
    device_index = 0
    joystick = pygame.joystick.Joystick(device_index)
    # 需要 init 才能获取名称
    joystick.init()
    
    controller_name = joystick.get_name()
    mapping_file = sanitize_filename(controller_name)
    
    print(f"识别设备: '{controller_name}'")
    print(f"读取配置: '{mapping_file}'")
    
    mapping_data = None
    try:
        with open(mapping_file, 'r') as f:
            mapping_data = json.load(f)
        print("配置加载成功。")
    except FileNotFoundError:
        print(f"\n❌ 错误：找不到映射文件 '{mapping_file}'")
        print(f"请为此手柄运行映射工具：python {os.path.basename(__file__)} --map")
        # 这里我们不退出，而是返回 None，让主循环决定怎么做
        return None, mapping_file, device_index
    except Exception as e:
        print(f"读取配置文件时出错: {e}")
        return None, mapping_file, device_index
        
    return mapping_data, mapping_file, device_index

# ==============================================================================
# ======================== 主控制循环 ==========================================
# ==============================================================================
def main_controller_loop(custom_mapping, initial_device_index):
    print("-" * 50)
    print("启动手柄控制引擎...")
    controller = None
    try:
        # 传入 initial_device_index 以实现自动激活
        controller = GenericController(custom_mapping, auto_activate_index=initial_device_index)
        
        mouse = MouseController()
        keyboard = KeyboardController()
        
        last_state = None
        last_print_time = 0
        is_active = False
        
        # 如果自动激活成功，controller.active_joy 应该已经是非 None
        if controller.active_joy:
            is_active = True
            print("✅ 控制已激活。按 Ctrl+C 退出。")
        else:
            print("请按手柄上的任意键来激活控制...")

        while True:
            state = controller.read()
            
            # 状态处理
            if state:
                if state.get("status") == "disconnected":
                    print("\n⚠️ 手柄已断开，等待重新连接...")
                    return 'disconnected' # 返回上层，重新寻找手柄

                if not is_active:
                    is_active = True
                    print("\n✅ 控制已激活。")
                
                # 执行动作
                for action in ACTION_CONFIG:
                    action.update(state, last_state, mouse, keyboard)
                last_state = state

                # 打印状态 (限制刷新率)
                current_time = time.time()
                if current_time - last_print_time > 0.1:
                    pressed = sorted([name for name, is_on in state["buttons"].items() if is_on])
                    print(f"L:({state['lx']:.2f},{state['ly']:.2f}) R:({state['rx']:.2f},{state['ry']:.2f}) LT:{state['lt']:.2f} RT:{state['rt']:.2f} B:{pressed}      ", end='\r')
                    last_print_time = current_time
            else:
                # state 为 None (未激活或无事件)
                if is_active:
                    # 这里意味着 GenericController 内部把 active_joy 设为了 None (比如切断了但没触发 disconnected?)
                    # 通常 GenericController 在断开时会返回 disconnected status
                    # 此处主要是为了处理暂停状态
                    pass
                
                time.sleep(0.01) # 空闲等待
            
            time.sleep(0.005) # 循环限速

    except KeyboardInterrupt:
        print("\n\n用户终止程序。")
        return 'exit'
    except Exception as e:
        print(f"\n发生未捕获错误: {e}")
        import traceback
        traceback.print_exc()
        return 'error'
    finally:
        if controller:
            controller.close()

# ==============================================================================
# ======================== 程序入口 ============================================
# ==============================================================================
if __name__ == "__main__":
    if IS_MAPPING_MODE:
        run_mapping_tool()
    else:
        while True:
            # 这一步现在包含了 Pygame Init, 等待连接, 加载配置
            mapping_data, map_file, dev_idx = setup_and_find_config()
            
            if mapping_data:
                # 进入控制循环
                result = main_controller_loop(mapping_data, dev_idx)
                
                if result == 'exit':
                    break
                elif result == 'disconnected':
                    # 手柄断开，Pygame 仍然是 Init 状态，但我们需要重新走发现流程吗？
                    # GenericController 内部其实已经处理了热插拔，但如果返回了 'disconnected'
                    # 说明我们需要重新确认是哪个手柄（或者是为了重置状态）
                    # 由于 setup_and_find_config 内部会再次 init，Pygame 允许重复 init 它是安全的
                    # 或者我们可以稍微 sleep 一下再试
                    time.sleep(1)
                    continue
            else:
                # 未找到配置文件，等待重试
                time.sleep(5)
        
        # 退出前清理
        pygame.quit()