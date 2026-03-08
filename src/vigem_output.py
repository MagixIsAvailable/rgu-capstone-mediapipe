import sys

# Global gamepad instance
gamepad = None
vg = None

try:
    import vgamepad as vg
except ImportError:
    print("[ViGEm] Error: 'vgamepad' module not found. Please run 'pip install vgamepad'.")

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

def apply_gesture(gesture_label: str, hand: str):
    """Maps a gesture string to a specific controller input."""
    gp = _get_gamepad()
    if not gp:
        return

    label = gesture_label.upper() if gesture_label else ""
    hand_side = hand.upper() if hand else ""
    
    # Mapping Logic
    if hand_side == "LEFT":
        if label == "SWIPE_RIGHT":
            gp.left_joystick_float(x_value_float=1.0, y_value_float=0.0)
        elif label == "SWIPE_LEFT":
            gp.left_joystick_float(x_value_float=-1.0, y_value_float=0.0)
        elif label == "SWIPE_UP":
            gp.left_joystick_float(x_value_float=0.0, y_value_float=1.0)
        elif label == "SWIPE_DOWN":
            gp.left_joystick_float(x_value_float=0.0, y_value_float=-1.0)
        elif label == "OPEN_PALM":
            gp.left_joystick_float(x_value_float=0.0, y_value_float=0.0)
        elif label == "CLOSED_FIST":
            gp.left_joystick_float(x_value_float=0.0, y_value_float=0.5)
        else:
            release_all()
            return

    elif hand_side == "RIGHT":
        # Clear previous buttons for this hand
        gp.report.wButtons = 0
        
        if label == "PINCH":
            gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_A)
        elif label == "THUMB_UP":
            gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_Y)
        elif label == "THUMB_DOWN":
            gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
        elif label == "POINTING_UP":
            gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_X)
        elif label == "VICTORY":
            gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER)
        elif label == "OPEN_PALM":
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
        print(f"[ViGEm] {hand} hand: {gesture_label} -> sent")
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