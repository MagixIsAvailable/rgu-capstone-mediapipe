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
vg = None  # ViGEm module (vgamepad) — loaded conditionally below

try:
    import vgamepad as vg  # Virtual Xbox 360 gamepad driver
except ImportError:
    logging.error("[ViGEm] Error: 'vgamepad' module not found. Please run 'pip install vgamepad'.")

def _get_gamepad():
    """Singleton accessor for the virtual Xbox 360 gamepad instance.
    
    ViGEm (Virtual Gamepad Emulation Bus) is a low-level Windows bus driver that
    allows this application to present itself as a virtual Xbox 360 controller to
    any Windows application, bypassing the need for physical hardware.
    
    This function follows the singleton pattern: the first call initializes the
    gamepad, and subsequent calls return the cached instance. If ViGEm initialization
    fails (e.g., driver not installed), returns None and logs critical error.
    
    Returns:
        vgamepad.VX360Gamepad or None
            Virtual controller instance if ViGEm initialized successfully.
            None if module import failed or VX360Gamepad() constructor raised exception.
    
    Side effects:
        - Lazy initialization of global `gamepad` variable (only on first call)
        - Logs critical error and driver setup instructions if initialization fails
        - Silent no-op if vgamepad module was not imported (see module top-level try/except)
    
    References:
        - ViGEm driver: https://github.com/nefarius/ViGEmBus/releases
        - vgamepad pypi package: https://pypi.org/project/vgamepad/
    
    Known issues:
        - On first call, USB bus access may block for 100-200ms during driver communication
        - If ViGEm driver is not installed, this causes a critical failure (program cannot
          continue as there's no physical fallback output)
    """
    global gamepad
    if vg is None:
        # vgamepad import failed — module not installed
        return None
    
    if gamepad is None:
        try:
            # Initialize new VX360Gamepad instance — blocks during USB bus initialization
            gamepad = vg.VX360Gamepad()
            logging.info("[ViGEm] VX360Gamepad initialized successfully.")
        except Exception as e:
            logging.critical(f"[ViGEm] Critical Error: Could not create virtual controller. {e}")
            logging.critical("[ViGEm] Please ensure the ViGEmBus driver is installed.")
            logging.critical("[ViGEm] Download driver: https://github.com/nefarius/ViGEmBus/releases")
            return None
    return gamepad

def release_all():
    """Release all pressed buttons and reset analog inputs to neutral.
    
    Called when no hand is detected or when transitioning to neutral state.
    Ensures the virtual controller returns to a known clean state to prevent
    unintended button holds or joystick drift affecting the application.
    
    Side effects:
        - Sends update to ViGEm bus (blocking on USB communication)
        - Logs state change via logging module
    
    Returns:
        None
    """
    gp = _get_gamepad()
    if gp:
        gp.reset()  # Reset all buttons, triggers, and joysticks to neutral
        gp.update()  # Flush update to virtual bus
        logging.info("[ViGEm] Released all inputs.")

def apply_gesture(gesture_label: str, hand: str, wrist_x: float = 0.0, wrist_y: float = 0.0):
    """Maps resolved action labels and wrist coordinates to Xbox 360 controller input.
    
    Implements bimanual asymmetry (Guiard, 1987):
    - LEFT hand: continuous joystick control (wrist_x, wrist_y) + D-Pad from gestures
    - RIGHT hand: discrete button/trigger presses from gestures + analog triggers for pinches
    
    Design:
        - Dead zone filtering (defined in config.DEAD_ZONE) prevents unintended drift when
          wrist coords are near (0,0) due to tracking noise
        - Left-hand D-pad and right-hand buttons are processed with clear release logic
          to prevent button ghosting (holding multiple buttons unintentionally)
        - Per-hand action routing ensures left-hand joystick state is never corrupted
          by right-hand button releases (e.g., XUSB_GAMEPAD_A release doesn't affect D-Pad)
    
    Args:
        gesture_label: str or list[str]
            Controller action label(s) from map_hand_actions() in gesture_mapping.py.
            Examples (right hand): 'BUTTON_A', 'TRIGGER_RT', ['BUTTON_7', 'BUTTON_8']
            Examples (left hand): 'DPAD_UP', 'DPAD_DOWN' (after normalization)
        
        hand: str
            "LEFT" or "RIGHT" (case-insensitive via .upper())
            Determines which controller features are activated:
            - LEFT: joystick + D-pad
            - RIGHT: buttons A/B/X/Y + shoulders + back/start + triggers
        
        wrist_x: float, default 0.0
            Normalized X-axis tilt from wrist angle (range: -1.0 to +1.0).
            Positive = rightward tilt, negative = leftward.
            Only used for LEFT hand; defines left joystick X position.
            Dead zone applied before transmission (see config.DEAD_ZONE).
        
        wrist_y: float, default 0.0
            Normalized Y-axis tilt from wrist/inter-hand angle (range: -1.0 to +1.0).
            Positive = upward, negative = downward.
            Only used for LEFT hand; defines left joystick Y position.
            Dead zone applied before transmission.
    
    Side effects:
        - Presses/releases Xbox buttons on the ViGEm virtual bus
        - Updates joystick position (continuous)
        - Logs errors if gamepad initialization failed
        - Blocking USB communication (typically <1ms per update)
    
    Returns:
        None
    
    References:
        - Chapter 3, Section 3.5 Output Layer
        - config.py: DEAD_ZONE tunable
        - gesture_mapping.py: map_hand_actions() source of action labels
    """
    gp = _get_gamepad()
    if not gp:
        return  # ViGEm failed to initialize; silently no-op to avoid crash

    hand_side = hand.upper() if hand else ""
    
    if hand_side == "LEFT":
        # LEFT HAND: Continuous Joystick + Directional Pad
        # =====================================================
        
        # Dead zone filtering (Chapter 3.5):
        # When both normalized coords fall below DEAD_ZONE threshold (e.g., 0.15),
        # the joystick is centered to zero. This prevents camera tracking noise from
        # causing unintended drifting motion in applications. Threshold chosen empirically
        # during calibration phase to balance responsiveness with noise rejection.
        if abs(wrist_x) < DEAD_ZONE and abs(wrist_y) < DEAD_ZONE:
            # Deadzone: Center joystick to (0, 0)
            gp.left_joystick_float(x_value_float=0.0, y_value_float=0.0)
        else:
            # Apply normalised coordinates directly to joystick axis
            gp.left_joystick_float(x_value_float=wrist_x, y_value_float=wrist_y)

        # D-Pad processing: handle list of gestures or single string
        labels = gesture_label if isinstance(gesture_label, list) else [gesture_label]

        # First release all D-pad directions to ensure clean state
        # (prevents simultaneous conflicting directions like UP+DOWN)
        gp.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP)
        gp.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN)
        gp.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT)
        gp.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT)

        # Press detected directions
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
        # RIGHT HAND: Discrete Buttons + Triggers
        # ========================================
        # 
        # Design decision: Only release right-hand mapped buttons, NOT D-pad buttons.
        # This allows simultaneous left-hand D-pad navigation while right-hand is
        # pressing action buttons. Example: left hand pressing UP while right hand
        # presses BUTTON_A should result in D-PAD_UP + BUTTON_A both active.
        # 
        # Releasing all right-side buttons at frame N ensures press/release
        # debouncing (prevents release logic from conflicting with new press).
        
        gp.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_A)
        gp.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
        gp.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_X)
        gp.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_Y)
        gp.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER)
        gp.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER)
        gp.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_BACK)
        gp.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_START)
        
        # Reset triggers to 0.0 (inactive)
        # Triggers are analog inputs, not buttons, so they require explicit value reset.
        # This ensures LT/RT don't remain pressed from previous frame.
        gp.right_trigger_float(value_float=0.0)
        gp.left_trigger_float(value_float=0.0)

        # Handle list of gestures or single string
        labels = gesture_label if isinstance(gesture_label, list) else [gesture_label]

        # Button/trigger mapping: convert gesture label to Xbox controller input
        for lbl in labels:
            # Face buttons (A/B/X/Y) and their numeric aliases
            if lbl == "BUTTON_1" or lbl == "BUTTON_A":
                gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_A)
            elif lbl == "BUTTON_2" or lbl == "BUTTON_B":
                gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
            elif lbl == "BUTTON_3" or lbl == "BUTTON_X":
                gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_X)
            elif lbl == "BUTTON_4" or lbl == "BUTTON_Y":
                gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_Y)
            
            # Shoulder buttons (LB/RB) and their numeric aliases
            elif lbl == "BUTTON_5" or lbl == "SHOULDER_LEFT":
                gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER)
            elif lbl == "BUTTON_6" or lbl == "SHOULDER_RIGHT":
                gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER)
            
            # Menu buttons (Back/Start) and their numeric aliases
            elif lbl == "BUTTON_7" or lbl == "BUTTON_BACK":
                gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_BACK)
            elif lbl == "BUTTON_8" or lbl == "BUTTON_START":
                gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_START)
            
            # Analog triggers (LT/RT) — use float values (0.0 to 1.0)
            # Mapped to pinch pressure gestures, allow partial trigger engagement
            elif lbl == "TRIGGER_LT":
                gp.left_trigger_float(value_float=1.0)  # Full engagement
            elif lbl == "TRIGGER_RT":
                gp.right_trigger_float(value_float=1.0)  # Full engagement
        
        # Transmit queued button states to virtual bus
        gp.update()
    else:
        # Invalid or empty hand string — safe fallback: release all and no-op
        release_all()
        return

    # Send the final report to the ViGEm virtual bus
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