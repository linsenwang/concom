# ==============================================================================
# =================== Interactive Gamepad Mapping Tool (Enhanced) =================
# ==============================================================================
# Version 2.0: Now with intelligent D-Pad mapping and backward compatibility.

import os

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "hide"

import pygame

from config_models import (
    HardwareMapping,
    Layer,
    Profile,
    ProfileSettings,
    hardware_input_from_value,
)
from profile_manager import save_profile, sanitize_filename

# --- Configuration ---
SKIP_KEY = pygame.K_s

class TextPrint:
    """A helper class to render text on the screen."""
    def __init__(self):
        self.reset()
        self.font = pygame.font.SysFont(None, 28) # Use system default font
        self.color = (230, 230, 230)

    def tprint(self, screen, text):
        screen.blit(self.font.render(text, True, self.color), (self.x, self.y))
        self.y += self.line_height

    def reset(self):
        self.x = 20
        self.y = 20
        self.line_height = 30


def run_mapping_tool():
    pygame.init()
    screen = pygame.display.set_mode((800, 700))
    pygame.display.set_caption("Gamepad Mapping Tool (Backward Compatible)")
    clock = pygame.time.Clock()
    text_print = TextPrint()

    joysticks = {}
    
    tasks = [
        ("A", "Press the 'A' button (bottom face button)"),
        ("B", "Press the 'B' button (right face button)"),
        ("X", "Press the 'X' button (left face button)"),
        ("Y", "Press the 'Y' button (top face button)"),
        ("LB", "Press the 'Left Bumper' (L1)"),
        ("RB", "Press the 'Right Bumper' (R1)"),
        ("MENU", "Press the 'Menu / Back / Select' button"),
        ("HOME", "Press the 'Home / Start' button"),
        ("LS", "Press the 'Left Stick' button (L3)"),
        ("RS", "Press the 'Right Stick' button (R3)"),
        ("lt", "Fully press the 'Left Trigger' (L2)"),
        ("rt", "Fully press the 'Right Trigger' (R2)"),
        ("lx", "Move the 'Left Stick' fully HORIZONTALLY"),
        ("ly", "Move the 'Left Stick' fully VERTICALLY"),
        ("rx", "Move the 'Right Stick' fully HORIZONTALLY"),
        ("ry", "Move the 'Right Stick' fully VERTICALLY"),
        ("DPAD_UP", "Press the 'D-Pad UP' direction"),
        ("DPAD_DOWN", "Press the 'D-Pad DOWN' direction"),
        ("DPAD_LEFT", "Press the 'D-Pad LEFT' direction"),
        ("DPAD_RIGHT", "Press the 'D-Pad RIGHT' direction")
    ]
    
    mapping = {}
    dpad_inputs = {}
    task_i = 0
    selected_joystick_id = None
    output_filename = None
    done = False
    dpad_analysis_pending = True

    print("Gamepad Mapping Tool started. Please follow the instructions in the window.")

    while not done:
        # --- Event Handling Loop (这部分代码与上一版相同，无需修改) ---
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                done = True
            if event.type == pygame.KEYDOWN:
                if event.key == SKIP_KEY and selected_joystick_id is not None and task_i < len(tasks):
                    key, _ = tasks[task_i]
                    if key.startswith("DPAD"): dpad_inputs[key] = None
                    else: mapping[key] = None
                    print(f"  - Skipped '{key}'")
                    task_i += 1
            if event.type == pygame.JOYDEVICEADDED:
                joy = pygame.joystick.Joystick(event.device_index)
                joysticks[joy.get_instance_id()] = joy
                print(f"Gamepad connected: {joy.get_name()}")
            if event.type == pygame.JOYDEVICEREMOVED:
                print(f"Gamepad (ID: {event.instance_id}) disconnected")
                if event.instance_id in joysticks: del joysticks[event.instance_id]
                if event.instance_id == selected_joystick_id:
                    selected_joystick_id, task_i, mapping, output_filename, dpad_inputs = None, 0, {}, None, {}
                    print("The gamepad being mapped has been disconnected. Please restart.")
            if selected_joystick_id is None and joysticks:
                if (event.type == pygame.JOYBUTTONDOWN or
                   (event.type == pygame.JOYAXISMOTION and abs(event.value) > 0.8) or
                   (event.type == pygame.JOYHATMOTION and event.value != (0, 0))):
                    selected_joystick_id = event.instance_id
                    mapping['name'] = joysticks[selected_joystick_id].get_name()
                    output_filename = sanitize_filename(mapping['name'])
                    print(f"Starting mapping for: '{mapping['name']}'")
                    print(f"Configuration will be saved to: {output_filename}")
                continue
            if selected_joystick_id is not None and task_i < len(tasks):
                if not hasattr(event, 'instance_id') or event.instance_id != selected_joystick_id: continue
                key, _ = tasks[task_i]
                detected_input = None
                if event.type == pygame.JOYBUTTONDOWN: detected_input = ("button", event.button)
                elif event.type == pygame.JOYAXISMOTION and abs(event.value) > 0.8: detected_input = ("axis", event.axis)
                elif event.type == pygame.JOYHATMOTION and event.value != (0, 0): detected_input = ("hat", event.hat, event.value)
                is_already_mapped = any(val == detected_input for k, val in mapping.items() if not k.startswith("DPAD"))
                if detected_input and not is_already_mapped:
                    print(f"  - Detected for '{key}' -> {detected_input}")
                    if key.startswith("DPAD"): dpad_inputs[key] = detected_input
                    else: mapping[key] = detected_input
                    task_i += 1

        # --- D-PAD MAPPING ANALYSIS (<<< 主要修改区域 >>>) ---
        if task_i >= len(tasks) and dpad_analysis_pending:
            dpad_analysis_pending = False
            print("\n--- Analyzing D-Pad Inputs ---")

            hat_indices = {v[1] for k, v in dpad_inputs.items() if v and v[0] == 'hat'}
            axis_indices = {v[1] for k, v in dpad_inputs.items() if v and v[0] == 'axis'}
            
            # 1. 检查是否为标准的 Hat Switch
            if len(dpad_inputs) == 4 and all(v and v[0] == 'hat' for v in dpad_inputs.values()) and len(hat_indices) == 1:
                hat_index = hat_indices.pop()
                mapping['dpad'] = ('hat', hat_index)
                print(f"Result: D-Pad is a standard HAT ({hat_index}). Mapping as 'dpad'. Fully compatible.")
            
            # 2. <<< 新增: 检查是否为双轴 D-Pad >>>
            elif len(dpad_inputs) == 4 and all(v and v[0] == 'axis' for v in dpad_inputs.values()) and len(axis_indices) == 2:
                y_axis = dpad_inputs.get("DPAD_UP", (None, -1))[1]
                x_axis = dpad_inputs.get("DPAD_LEFT", (None, -1))[1]
                # 验证 UP/DOWN 和 LEFT/RIGHT 是否分别在同一个轴上
                if (y_axis == dpad_inputs.get("DPAD_DOWN", (None, -2))[1] and
                    x_axis == dpad_inputs.get("DPAD_RIGHT", (None, -3))[1] and
                    y_axis != x_axis and y_axis != -1 and x_axis != -1):
                    mapping['dpad'] = {"type": "axes", "y_axis": y_axis, "x_axis": x_axis}
                    print(f"Result: D-Pad uses two axes (Y-axis: {y_axis}, X-axis: {x_axis}). Compatible with updated GenericController.")
                else:
                    print("Result: D-Pad uses axes, but axis assignment is inconsistent. Skipping.")

            # 3. 检查是否为独立按键
            elif len(dpad_inputs) > 0 and all(v is None or v[0] == 'button' for v in dpad_inputs.values()):
                print("Result: D-Pad uses separate buttons.")
                print("WARNING: GenericController class needs modification to support button-based D-Pads.")
                for key, val in dpad_inputs.items():
                    if val: mapping[key] = val
            
            # 4. 其他情况
            else:
                print("Result: D-Pad inputs are inconsistent or use an unsupported type. Skipping D-Pad mapping.")

        # --- Screen Rendering & Save Logic (这部分代码与上一版相同，无需修改) ---
        screen.fill((30, 30, 30))
        text_print.reset()
        if not joysticks: text_print.tprint(screen, "Please connect a gamepad...")
        elif selected_joystick_id is None: text_print.tprint(screen, "Press any button on the gamepad you want to map.")
        elif task_i < len(tasks):
            text_print.tprint(screen, f"Mapping: {mapping.get('name', '')}")
            text_print.tprint(screen, "-"*50)
            text_print.tprint(screen, f"Step {task_i + 1}/{len(tasks)}:")
            text_print.tprint(screen, f"--> {tasks[task_i][1]}")
            text_print.tprint(screen, "")
            text_print.tprint(screen, f"(Press '{pygame.key.name(SKIP_KEY).upper()}' on keyboard to skip)")
        else:
            text_print.tprint(screen, "Mapping Complete!")
            text_print.tprint(screen, f"Configuration will be saved to '{output_filename}'.")
            text_print.tprint(screen, "You can now close this window.")
        pygame.display.flip()
        clock.tick(60)

    if len(mapping) > 1 and output_filename:
        try:
            controller_name = mapping.pop('name', '')
            inputs = {}
            for key, value in mapping.items():
                hw = hardware_input_from_value(value)
                if hw is not None:
                    inputs[key] = hw

            profile = Profile(
                name=controller_name,
                hardware=HardwareMapping(name=controller_name, inputs=inputs),
                settings=ProfileSettings(),
                layers={"default": Layer(name="default")},
            )
            saved_path = save_profile(profile)
            print(f"\nProfile successfully saved to {saved_path}")
        except Exception as e:
            print(f"\nError: Could not save profile file: {e}")
    pygame.quit()

if __name__ == '__main__':
    run_mapping_tool()