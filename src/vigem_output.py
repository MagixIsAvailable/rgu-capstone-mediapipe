"""
Module: vigem_output.py
Project: VisionInput — Gesture-Based Controller for Immersive Projection Environments
Author: Michal Lazovy | RGU CM4134 Honours Capstone 2026
Supervisor: Dr John N.A. Brown | Partner: James Hutton Institute, Aberdeen

Purpose:
Output layer for the VisionInput pipeline. Translates gesture labels and normalised joystick values into virtual Xbox 360 controller signals using the ViGEmBus driver via the vgamepad library. Handles left joystick float values, right hand button presses, D-pad inputs, triggers, and bumpers. All controller output is centralised here — no gesture logic is contained in this module.

Dependencies:
vgamepad

Usage:
Imported by main.py — not run directly.
"""
import logging
from config import DEAD_ZONE

# Global gamepad instance
gamepad = None
vg = None

try:
    import vgamepad as vg
except ImportError:
    logging.error("[ViGEm] Error: 'vgamepad' module not found. Please run 'pip install vgamepad'.")

def _get_gamepad():
    """Singleton accessor for the gamepad instance."""
    global gamepad
    if vg is None:
        return None
    
    if gamepad is None:
        try:
            gamepad = vg.VX360Gamepad()
            logging.info("[ViGEm] VX360Gamepad initialized successfully.")
        except Exception as e:
            logging.critical(f"[ViGEm] Critical Error: Could not create virtual controller. {e}")
            logging.critical("[ViGEm] Please ensure the ViGEmBus driver is installed.")
            logging.critical("[ViGEm] Download driver: https://github.com/nefarius/ViGEmBus/releases")
            return None
    return gamepad

def release_all():
    """Releases all buttons and resets joysticks to center."""
    gp = _get_gamepad()
    if gp:
        gp.reset()
        gp.update()
        logging.info("[ViGEm] Released all inputs.")

def apply_gesture(gesture_label: str, hand: str, wrist_x: float = 0.0, wrist_y: float = 0.0):
    """Maps resolved action labels and wrist coords to controller input."""
    gp = _get_gamepad()
    if not gp:
        return

    hand_side = hand.upper() if hand else ""
    
    if hand_side == "LEFT":
        # Continuous Joystick Control with Deadzone
        if abs(wrist_x) < DEAD_ZONE and abs(wrist_y) < DEAD_ZONE:
            # Deadzone: Center joystick
            gp.left_joystick_float(x_value_float=0.0, y_value_float=0.0)
        else:
            # Apply normalised coordinates directly
            gp.left_joystick_float(x_value_float=wrist_x, y_value_float=wrist_y)

        # Handle list of gestures or single string for D-Pad
        labels = gesture_label if isinstance(gesture_label, list) else [gesture_label]

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
            elif lbl == "BUTTON_A":
                gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_A)
            elif lbl == "BUTTON_2":
                gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
            elif lbl == "BUTTON_B":
                gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
            elif lbl == "BUTTON_3":
                gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_X)
            elif lbl == "BUTTON_X":
                gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_X)
            elif lbl == "BUTTON_4":
                gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_Y)
            elif lbl == "BUTTON_Y":
                gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_Y)
            elif lbl == "BUTTON_5":
                gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER)
            elif lbl == "SHOULDER_LEFT":
                gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER)
            elif lbl == "BUTTON_6":
                gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER)
            elif lbl == "SHOULDER_RIGHT":
                gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER)
            elif lbl == "BUTTON_7":
                gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_BACK)
            elif lbl == "BUTTON_BACK":
                gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_BACK)
            elif lbl == "BUTTON_8":
                gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_START)
            elif lbl == "BUTTON_START":
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
    except Exception as e:
        logging.error(f"[ViGEm] Error updating controller: {e}")

# ----------------------------------------------------------------
# Main Execution (Test Mode)
# ----------------------------------------------------------------
if vg:
    # If imported as a module, just initialize
    _get_gamepad()