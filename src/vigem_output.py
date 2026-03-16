import sys
import json
import os

# Global gamepad instance
gamepad = None
vg = None
GESTURE_MAP = {}

try:
    import vgamepad as vg
except ImportError:
    print("[ViGEm] Error: 'vgamepad' module not found. Please run 'pip install vgamepad'.")

# Load gesture map
def load_gesture_map():
    global GESTURE_MAP
    try:
        # Path relative to this script: goes up one level to root, then into config
        root_dir = os.path.dirname(os.path.dirname(__file__))
        map_path = os.path.join(root_dir, 'config', 'gesture_map.json')
        
        with open(map_path, 'r') as f:
            GESTURE_MAP = json.load(f)
    except FileNotFoundError:
        print("[ViGEm] Error: gesture_map.json not found.")
    except json.JSONDecodeError:
        print("[ViGEm] Error: gesture_map.json is not valid JSON.")
    except Exception as e:
        print(f"[ViGEm] Error loading gesture map: {e}")

load_gesture_map()

def _get_gamepad():
    """Singleton accessor for the gamepad instance."""
    global gamepad
    if vg is None:
        return None
    
    if gamepad is None:
        try:
            gamepad = vg.VX360Gamepad()
            print("[ViGEm] VX360Gamepad initialized successfully.")
        except Exception as e:
            print(f"[ViGEm] Critical Error: Could not create virtual controller. {e}")
            print("[ViGEm] Please ensure the ViGEmBus driver is installed.")
            print("[ViGEm] Download driver: https://github.com/nefarius/ViGEmBus/releases")
            return None
    return gamepad

def release_all():
    """Releases all buttons and resets joysticks to center."""
    gp = _get_gamepad()
    if gp:
        gp.reset()
        gp.update()
        print("[ViGEm] Released all inputs.")

def apply_gesture(gesture_label: str, hand: str, wrist_x: float = 0.0, wrist_y: float = 0.0):
    """Maps a gesture string or wrist coords to controller input."""
    gp = _get_gamepad()
    if not gp:
        return

    hand_side = hand.upper() if hand else ""
    
    if hand_side == "LEFT":
        # Continuous Joystick Control with Deadzone
        if abs(wrist_x) < 0.15 and abs(wrist_y) < 0.15:
            # Deadzone: Center joystick
            gp.left_joystick_float(x_value_float=0.0, y_value_float=0.0)
        else:
            # Apply normalised coordinates directly
            gp.left_joystick_float(x_value_float=wrist_x, y_value_float=wrist_y)

    elif hand_side == "RIGHT":
        # Clear previous buttons for this hand
        gp.report.wButtons = 0
        # Reset triggers
        gp.right_trigger_float(value_float=0.0)
        gp.left_trigger_float(value_float=0.0)

        # Handle list of gestures or single string
        labels = gesture_label if isinstance(gesture_label, list) else [gesture_label]

        for lbl in labels:
            if lbl == "BUTTON_1":
                gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_A)
            elif lbl == "BUTTON_2":
                gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
            elif lbl == "BUTTON_3":
                gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_X)
            elif lbl == "BUTTON_4":
                gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_Y)
            elif lbl == "BUTTON_5":
                gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER)
            elif lbl == "BUTTON_6":
                gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER)
            elif lbl == "BUTTON_7":
                gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_BACK)
            elif lbl == "BUTTON_8":
                gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_START)
            elif lbl == "TRIGGER_LT":
                gp.left_trigger_float(value_float=1.0)
            elif lbl == "TRIGGER_RT":
                gp.right_trigger_float(value_float=1.0)
        
        gp.update()
    else:
        release_all()
        return

    # Send the report to the virtual bus
    try:
        gp.update()
        # print(f"[ViGEm] {hand} hand: {gesture_label} -> sent")
    except Exception as e:
        print(f"[ViGEm] Error updating controller: {e}")

# ----------------------------------------------------------------
# Main Execution (Test Mode)
# ----------------------------------------------------------------
if __name__ == "__main__":
    # If this file is run directly, run a Keep-Alive test
    if vg:
        print("=================================================")
        print("   ViGEm OUTPUT MODULE - DIRECT TEST MODE")
        print("=================================================")
        print("Check https://hardwaretester.com/gamepad")
        print("Press CTRL+C to stop.")
        
        import time
        _get_gamepad()
        
        try:
            while True:
                print(">> Simulating 'PINCH' (Button A) on RIGHT hand...")
                apply_gesture("PINCH", "RIGHT")
                time.sleep(0.5)
                release_all()
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("\nStopped.")
elif vg:
    # If imported as a module, just initialize
    _get_gamepad()