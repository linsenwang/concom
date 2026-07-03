# =============================================================================
# Controller Companion
# =============================================================================
import argparse
import os
import re
import subprocess
import sys
import time

# Hide pygame support prompt before importing pygame
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "hide"

import pygame
from pynput.keyboard import Controller as KeyboardController
from pynput.mouse import Controller as MouseController

from Action import ProfileRunner
from config_gui import run_config_gui
from GenericController import GenericController
from profile_manager import load_profile
from run_mapping_tool import run_mapping_tool

# 空闲多久后自动断开蓝牙并退出（秒），默认 10 分钟
IDLE_TIMEOUT_SECONDS = int(os.environ.get("CC_IDLE_TIMEOUT", "600"))


KNOWN_GAMEPAD_NAMES = [
    "Nintendo Switch Pro Controller",
    "Xbox Series X Controller",
    "Xbox Wireless Controller",
    "Pro Controller",
    "DualSense Wireless Controller",
    "Controller",
]


def _has_input_activity(state: dict) -> bool:
    """Return True if any button/axis/trigger is currently active."""
    if not state:
        return False
    pressed = any(state.get("buttons", {}).values())
    return pressed or (
        state.get("lt", 0.0) > 0.01
        or state.get("rt", 0.0) > 0.01
        or abs(state.get("lx", 0.0)) > 0.15
        or abs(state.get("ly", 0.0)) > 0.15
        or abs(state.get("rx", 0.0)) > 0.15
        or abs(state.get("ry", 0.0)) > 0.15
    )


def disconnect_bluetooth_controller(controller_name: str | None = None) -> None:
    """Disconnect the controller via blueutil."""
    try:
        result = subprocess.run(
            ["blueutil", "--connected"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as e:
        print(f"[Bluetooth] 无法获取已连接设备: {e}")
        return

    lines = result.stdout.strip().splitlines()
    targets = []
    for line in lines:
        addr_match = re.search(r"address:\s*([0-9a-fA-F:-]{17})", line)
        name_match = re.search(r'name:\s*"([^"]+)"', line)
        if not addr_match:
            continue
        address = addr_match.group(1)
        name = name_match.group(1) if name_match else ""

        if controller_name:
            if controller_name.lower() in name.lower():
                targets.append((address, name))
        else:
            if any(n.lower() in name.lower() for n in KNOWN_GAMEPAD_NAMES):
                targets.append((address, name))

    for address, name in targets:
        try:
            subprocess.run(
                ["blueutil", "--disconnect", address],
                capture_output=True,
                timeout=10,
            )
            print(f"[Bluetooth] 已断开 '{name}' ({address})")
        except Exception as e:
            print(f"[Bluetooth] 断开 '{name}' 失败: {e}")


def wait_for_controller(timeout_seconds: float = 180.0) -> tuple[str, int]:
    """Wait for a controller and return (name, device_index)."""
    print("正在初始化系统...")
    pygame.init()
    pygame.joystick.init()

    print(f"等待手柄连接...（{timeout_seconds}秒后自动关闭）", end="", flush=True)
    start_time = time.time()
    while pygame.joystick.get_count() == 0:
        pygame.event.pump()
        time.sleep(0.5)
        if time.time() - start_time > timeout_seconds:
            print(f"\n⏰ 等待超时（{timeout_seconds}秒），未检测到手柄连接，自动关闭。")
            pygame.quit()
            sys.exit(0)
        if int(time.time() - start_time) % 10 == 0:
            print(".", end="", flush=True)

    print("\n检测到手柄连接！")
    device_index = 0
    joystick = pygame.joystick.Joystick(device_index)
    joystick.init()
    controller_name = joystick.get_name()
    print(f"识别设备: '{controller_name}'")
    return controller_name, device_index


def main_controller_loop(profile, device_index: int, controller_name: str) -> str:
    """Run the controller loop. Returns a status string."""
    print("-" * 50)
    print("启动手柄控制引擎...")

    controller = GenericController(
        profile.hardware,
        auto_activate_index=device_index,
        xbox_trigger_fix=True,
    )
    runner = ProfileRunner(profile)
    mouse = MouseController()
    keyboard = KeyboardController()

    if controller.active_joy:
        print("✅ 控制已激活。按 Ctrl+C 退出。")
    else:
        print("请按手柄上的任意键来激活控制...")

    last_print_time = 0.0
    last_input_time = time.time()
    poll_interval = profile.settings.poll_interval

    try:
        while True:
            state = controller.read()

            if state is None:
                time.sleep(poll_interval)
                continue

            if state.get("status") == "disconnected":
                print("\n⚠️ 手柄已断开，等待重新连接...")
                return "disconnected"

            runner.update(state, mouse, keyboard)

            current_time = time.time()

            # 空闲超时检测
            if _has_input_activity(state):
                last_input_time = current_time
            elif current_time - last_input_time > IDLE_TIMEOUT_SECONDS:
                print(
                    f"\n⏰ 超过 {IDLE_TIMEOUT_SECONDS} 秒没有任何操作，"
                    "即将断开蓝牙并退出程序。"
                )
                disconnect_bluetooth_controller(controller_name)
                return "idle_exit"

            if current_time - last_print_time > 0.1:
                pressed = sorted(
                    name for name, is_on in state["buttons"].items() if is_on
                )
                is_active = (
                    pressed
                    or state["lt"] > 0.01
                    or state["rt"] > 0.01
                    or abs(state["lx"]) > 0.15
                    or abs(state["ly"]) > 0.15
                    or abs(state["rx"]) > 0.15
                    or abs(state["ry"]) > 0.15
                )
                if is_active:
                    line = (
                        f"L:({state['lx']:.2f},{state['ly']:.2f}) "
                        f"R:({state['rx']:.2f},{state['ry']:.2f}) "
                        f"LT:{state['lt']:.2f} RT:{state['rt']:.2f} B:{pressed}"
                    )
                    print(f"\r{line}\033[K", end="", flush=True)
                last_print_time = current_time

            time.sleep(poll_interval)

    except KeyboardInterrupt:
        print("\n\n用户终止程序。")
        return "exit"
    except Exception:
        import traceback
        traceback.print_exc()
        return "error"
    finally:
        controller.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Controller Companion")
    parser.add_argument(
        "--map", action="store_true", help="运行手柄硬件映射工具"
    )
    parser.add_argument(
        "--config", action="store_true", help="运行可视化配置界面"
    )
    parser.add_argument(
        "--controller", type=str, default=None, help="指定手柄名称（用于 --config）"
    )
    args = parser.parse_args()

    if args.map:
        run_mapping_tool()
        return

    if args.config:
        run_config_gui(args.controller)
        return

    while True:
        controller_name, device_index = wait_for_controller()
        profile = load_profile(controller_name)

        if not profile.hardware.inputs:
            print(f"\n❌ 错误：找不到 '{controller_name}' 的硬件映射。")
            print("请运行映射工具：python main.py --map")
            print("或运行配置界面：python main.py --config")
            time.sleep(5)
            continue

        print(f"读取配置: '{controller_name}'")
        result = main_controller_loop(profile, device_index, controller_name)

        if result in ("exit", "idle_exit"):
            break
        if result == "disconnected":
            time.sleep(1)
            continue
        if result == "error":
            time.sleep(2)
            continue

    pygame.quit()


if __name__ == "__main__":
    main()
