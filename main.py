# ==============================================================================
# ======================== 依赖导入 ========================================
# ==============================================================================
import os
import sys
import json
import time
import ctypes

# --- 模式检测 ---
IS_MAPPING_MODE = '--map' in sys.argv
# if not IS_MAPPING_MODE:
#     os.environ["SDL_VIDEODRIVER"] = "dummy"

from pynput.mouse import Button, Controller as MouseController
from pynput.keyboard import Key, Controller as KeyboardController

try:
    if not IS_MAPPING_MODE:
        ctypes.CDLL(None).SDL_EnableScreenSaver()
except Exception:
    pass

MAPPING_FILE = "controller_map.json"
from run_mapping_tool import run_mapping_tool
from GenericController import GenericController
from Action import *
from ACTION_CONFIG import ACTION_CONFIG

# ==============================================================================
# ======================== 主程序与配置 (不变) =================================
# ==============================================================================
def main_controller_loop(custom_mapping):
    controller = None
    try:
        controller = GenericController(custom_mapping)
        mouse = MouseController(); keyboard = KeyboardController()
        last_state = None; last_print_time = 0; is_active = False
        print("请按手柄上的任意键来激活控制...")

        while True:
            state = controller.read()
            if state:
                if not is_active:
                    is_active = True
                    print("手柄控制已激活。按 Ctrl+C 退出。")
                    print("-" * 50)
                
                for action in ACTION_CONFIG:
                    action.update(state, last_state, mouse, keyboard)
                last_state = state

                current_time = time.time()
                if current_time - last_print_time > 0.1:
                    pressed = sorted([name for name, is_on in state["buttons"].items() if is_on])
                    print(f"L:({state['lx']:.2f},{state['ly']:.2f}) R:({state['rx']:.2f},{state['ry']:.2f}) LT:{state['lt']:.2f} RT:{state['rt']:.2f} B:{pressed}      ", end='\r')
                    last_print_time = current_time
            else:
                if is_active:
                    is_active = False
                    print("\n" + "-" * 50)
                    print("手柄控制已暂停。请按任意键重新激活...")
                    last_state = None
                
                # 在等待激活时减少CPU占用
                time.sleep(0.5)
            
            # 在每次循环后短暂休眠，以避免CPU占用过高
            time.sleep(0.008)

    except KeyboardInterrupt: print("\n正在退出。")
    except Exception as e: print(f"\n发生错误: {e}")
    finally:
        if controller: controller.close()

if __name__ == "__main__":
    if IS_MAPPING_MODE:
        run_mapping_tool()
    else:
        try:
            with open(MAPPING_FILE, 'r') as f: mapping_data = json.load(f)
            print(f"已成功从 '{MAPPING_FILE}' 加载手柄映射。")
            main_controller_loop(mapping_data)
        except FileNotFoundError:
            print("="*60 + f"\n错误：找不到手柄映射文件 '{MAPPING_FILE}'。\n" + "请使用 --map 参数运行一次以创建映射文件：\n" + f"    python {os.path.basename(__file__)} --map\n" + "="*60)
        except Exception as e:
            print(f"启动时发生错误: {e}")