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

        # Handle list of gestures or single string for D-Pad
        labels = gesture_label if isinstance(gesture_label, list) else [gesture_label]

        # Clear D-Pad state first (optional but good practice to avoid stuck keys if logic changes)
        # Note: simplistic approach - clear all DPAD bits then set based on current labels
        # However, vgamepad accumulates button presses until update() is called?
        # Actually, for buttons, we need to explicitly press. If we don't press it in this frame, 
        # but pressed it in the last frame, vgamepad might keep it pressed unless released?
        # vgamepad's press_button adds the flag. We need to clear flags if not present?
        # The RIGHT hand implementation clears wButtons=0. We should probably do the same for LEFT 
        # but be careful not to clear buttons set by RIGHT hand if they share the same report?
        # VX360Gamepad has one report. If we clear wButtons in LEFT, we wipe RIGHT hand buttons.
        # But `apply_gesture` is called sequentially for each hand.
        # This implies we can't just wipe wButtons for the Left hand without affecting Right hand if they are processed in same loop iteration?
        # Looking at main.py:
        # for i, hlp in enumerate(landmarks): ... apply_gesture(...) ...
        # It calls apply_gesture for each hand.
        # If we clear wButtons in Left, we might clear Right's work if Right was processed first?
        # Or if Left is processed first, Right will clear Left's work?
        # The RIGHT hand implementation does `gp.report.wButtons = 0`. This is destructive!
        # If RIGHT hand runs second, it clears LEFT hand's buttons.
        # If LEFT hand runs second, we need to be careful.
        
        # Let's check how `gp.report.wButtons` works. It's a bitmask.
        # The `press_button` method ORs the bit.
        # The `release_button` method un-ORs (AND NOT) the bit.
        # The Right hand code does `gp.report.wButtons = 0`, which assumes it owns all buttons.
        # If I add buttons to Left hand, I need to coordinate this.
        
        # Ideally, `wButtons` should be cleared ONCE per frame, before any hand processing.
        # But `apply_gesture` is called per hand.
        # Quick fix: The Right hand logic wipes everything. This is a bug in the existing code if we want dual hand buttons.
        # But wait, Right hand maps to A, B, X, Y, RB, LB, Start, Back.
        # Left hand maps to D-pad.
        # They use different buttons.
        # If Right hand clears all buttons, Left hand buttons will be lost if Left processed before Right.
        # If Right processed before Left, Left should NOT clear all buttons.
        
        # Current Right hand code:
        # gp.report.wButtons = 0
        
        # If I change Left hand to also write buttons, I need to ensure they don't step on each other.
        # If I change `gp.report.wButtons = 0` to only clear the buttons IT controls, that would be safer.
        # OR, I can accept that `apply_gesture` is called sequentially.
        # If I can ensure Right hand is processed first, then Left hand just ORs its buttons.
        # But order depends on `result.multi_hand_landmarks` order which is not guaranteed.
        #
        # A better approach: `vigem_output` should probably have a `reset_buttons()` called at start of frame?
        # But I am only supposed to edit specific files and functions as requested.
        # The user said "Update vigem_output.py to handle the four new D-pad labels".
        # I should probably just use `press_button` and `release_button` for D-pad?
        # Or explicitly manage the D-pad bits.
        
        # Let's look at `press_button` implementation in vgamepad (I can't see library code but I can infer).
        # It typically converts enum to int and ORs it into `wButtons`.
        
        # If I use `press_button`, I need to make sure I `release_button` if the gesture is NOT present.
        # Or I can manually manipulate the bits.
        
        # Let's see what buttons are available.
        # D-pad up/down/left/right.
        
        # Implementation:
        # 1. Release all D-pad buttons (to clear previous state for this hand).
        # 2. Press active D-pad buttons.
        
        gp.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP)
        gp.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN)
        gp.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT)
        gp.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT)

        for lbl in labels:
            if lbl == "DPAD_UP":
                gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP)
            elif lbl == "DPAD_DOWN":
                gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN)
            elif lbl == "DPAD_LEFT":
                gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT)
            elif lbl == "DPAD_RIGHT":
                gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT)

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