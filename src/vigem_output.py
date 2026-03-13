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
        # Path relative to this script
        map_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'gesture_map.json')
        with open(map_path, 'r') as f:
            GESTURE_MAP = json.load(f)
        print(f"[ViGEm] Loaded gesture map from {map_path}")
    except Exception as e:
        print(f"[ViGEm] Warning: Could not load gesture_map.json: {e}")
        GESTURE_MAP = {}

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

    label = gesture_label.upper() if gesture_label else ""
    hand_side = hand.upper() if hand else ""
    
    # Mapping Logic
    # Try to get action from map, default to None
    action = GESTURE_MAP.get(hand_side, {}).get(label)

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
        
        if action == "BUTTON_A":
            gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_A)
        elif action == "BUTTON_Y":
            gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_Y)
        elif action == "BUTTON_B":
            gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
        elif action == "BUTTON_X":
            gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_X)
        elif action == "SHOULDER_RIGHT":
            gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER)
        elif action == "NONE":
            # Buttons already cleared above
            pass
        else:
            release_all()
            return
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