"""
Module: visualiser.py
Project: VisionInput — Gesture-Based Controller for Immersive Projection Environments
Author: Michal Lazovy | RGU CM4134 Honours Capstone 2026
Supervisor: Dr John N.A. Brown | Partner: James Hutton Institute, Aberdeen

Purpose:
Debug overlay rendering module for real-time visual diagnostics. Draws rich annotated
overlays on camera frames showing hand landmarks, gesture detection state, controller
output, calibration progress, and performance metrics. Activated via --visualise flag
in main.py for development and troubleshooting.

Output Features (8 distinct visualization layers):
1. LANDMARK NUMBERS — Numbered dots at each MediaPipe landmark position (0-20)
2. FINGER LABELS — Text labels ("THUMB", "INDEX", etc.) at finger tips
3. PINCH DISTANCE LINE — Color-coded line from thumb to index (red=pinched, green=open)
4. WRIST VECTOR ARROW — Cyan arrow from wrist to middle MCP (indicates hand tilt)
5. HAND BOUNDING BOX — White rectangle around hand with LEFT/RIGHT label
6. INTER-FINGER DISTANCE LINES — Grey lines between finger tips (index→middle→ring→pinky)
7. NORMALIZED COORDINATES PANEL — Semi-transparent data overlay (wrist X/Y, pinch, gesture)
8. TWO-HAND SPREAD LINE — Magenta line connecting wrists when both hands detected
9. FPS COUNTER — Green/orange/red text (>24fps/15-24fps/<15fps)
10. CALIBRATION INDICATOR — Yellow pulsing status or green checkmark when calibrated

Design rationale:
- Used for technical validation, not user-facing application (rough UI acceptable)
- Rich instrumentation enables rapid iteration on gesture detection parameters
- Frame-per-frame diagnostics help identify temporal glitches vs static issues
- Color coding accelerates visual pattern matching (muscle memory during testing)

Dependencies:
cv2 (OpenCV), numpy (for overlay blend operations)

Usage:
Imported by main.py. Called each frame when --visualise flag enabled:
    visualiser.draw_overlay(frame, landmarks_list, calculated_values)

Performance note:
- Overlay rendering adds ~5-15ms per frame (scales with number of hands/landmarks)
- Should not be used during production performance measurements (see --benchmark)
- Disabling --visualise restores full pipeline throughput

References:
- Chapter 5: Real-time diagnostic system design
- MediaPipe landmark indices: https://mediapipe-studio.webapps.google.com/home
"""
import cv2
import numpy as np
import math
import time

# =============================================================================
# COLOR PALETTE (BGR format for OpenCV)
# =============================================================================
# OpenCV uses BGR ordering (not RGB), so (B, G, R) tuples.
# Color choices optimize for visibility against typical skin tones and white/black backgrounds.

WHITE = (255, 255, 255)    # Landmarks, bounding box
RED = (0, 0, 255)          # Thumb (landmarks 1-4), error states
GREEN = (0, 255, 0)        # Index finger (landmarks 5-8), success states
BLUE = (255, 0, 0)         # Middle finger (landmarks 9-12)
YELLOW = (0, 255, 255)     # Ring finger (landmarks 13-16), calibration status
PURPLE = (255, 0, 255)     # Pinky (landmarks 17-20), two-hand interaction
ORANGE = (0, 165, 255)     # Intermediate values, FPS warnings
CYAN = (255, 255, 0)       # Wrist vector, coordinate labels
MAGENTA = (255, 0, 255)    # Two-hand metrics
GREY = (128, 128, 128)     # Inter-finger lines
BLACK = (0, 0, 0)          # Background fill

# =============================================================================
# LANDMARK COLOR MAPPING
# =============================================================================
# Each of 21 landmarks gets a color based on finger assignment.
# MediaPipe hand landmark indices:
#   0: wrist (center of hand)
#   1-4: thumb (MCP, PIP, DIP, tip)
#   5-8: index (MCP, PIP, DIP, tip)
#   9-12: middle (MCP, PIP, DIP, tip)
#   13-16: ring (MCP, PIP, DIP, tip)
#   17-20: pinky (MCP, PIP, DIP, tip)
# Reference: https://mediapipe-studio.webapps.google.com/home

FINGER_COLOR_MAP = {
    0: WHITE,   # Wrist
    1: RED,     # Thumb MCP
    2: RED,     # Thumb PIP
    3: RED,     # Thumb DIP
    4: RED,     # Thumb tip
    5: GREEN,   # Index MCP
    6: GREEN,   # Index PIP
    7: GREEN,   # Index DIP
    8: GREEN,   # Index tip
    9: BLUE,    # Middle MCP
    10: BLUE,   # Middle PIP
    11: BLUE,   # Middle DIP
    12: BLUE,   # Middle tip
    13: YELLOW, # Ring MCP
    14: YELLOW, # Ring PIP
    15: YELLOW, # Ring DIP
    16: YELLOW, # Ring tip
    17: PURPLE, # Pinky MCP
    18: PURPLE, # Pinky PIP
    19: PURPLE, # Pinky DIP
    20: PURPLE  # Pinky tip
}

# Finger tip indices for text label overlay
FINGER_TIPS = {
    4: "THUMB",
    8: "INDEX",
    12: "MIDDLE",
    16: "RING",
    20: "PINKY"
}

def to_pixel(landmark, shape):
    """Convert normalized landmark coordinates to pixel coordinates.
    
    MediaPipe returns normalized coordinates in range [0, 1] where (0,0) is
    top-left corner of image and (1,1) is bottom-right. This function maps
    to OpenCV pixel coordinates.
    
    Args:
        landmark: MediaPipe NormalizedLandmark with .x and .y attributes
                  Normalized to [0, 1] range relative to image dimensions.
        shape: tuple (height, width) from frame.shape
    
    Returns:
        tuple (int, int): Pixel coordinates (x_px, y_px) ready for cv2 drawing
    
    Examples:
        landmark at (0.5, 0.5) normalized, shape=(480, 640) -> (320, 240) px
    """
    return int(landmark.x * shape[1]), int(landmark.y * shape[0])

def draw_overlay(frame, landmarks_list, calculated_values):
    """Render diagnostic overlay on camera frame with rich hand data visualization.
    
    This function assembles 10 distinct visualization layers to help developers
    debug and validate gesture detection, tracking, and controller output. Each
    layer is conditionally rendered based on available data.
    
    Visualization Layers (rendering order):
        1. Semi-transparent background panel for text data overlay
        2-9. Hand-specific data (landmarks, vectors, pinch state)
        10. FPS and calibration status indicators
    
    Args:
        frame: numpy array (BGR), camera frame from cv2.read()
               Shape: (height, width, 3) with dtype uint8.
        
        landmarks_list: list of NormalizedLandmarkList objects from MediaPipe
                        Each element corresponds to one detected hand.
                        If empty, displays "No hands detected" implicitly via early exit.
        
        calculated_values: dict with per-frame diagnostic data
            Required keys:
            - 'fps': float, instantaneous frames per second
            - 'calibration_status': str, "calibrating" or "calibrated"
            - 'calibration_time_remain': float, seconds remaining (0 when calibrated)
            - 'gestures': list[str], detected gesture labels per hand
            - 'handedness': list[str], "Left" or "Right" per hand
            - 'pinch_dists': list[float], Euclidean distance (thumb to index tip)
            - 'pinch_speeds': list[float], change in pinch distance per frame
            - 'wrist_coords': list[tuple], normalized joystick values (x, y) per hand
    
    Returns:
        numpy array: Annotated BGR frame (same shape as input). Original frame
                     is copied before modification to avoid side effects.
    
    Side effects:
        - Modifies global OpenCV window state (creates "MediaPipe Gesture Controller" window)
        - No file I/O or network communication
    
    Performance notes:
        - O(L) complexity where L = total landmarks across all hands (max 42 for 2 hands)
        - OpenCV drawing operations: ~5-15ms per frame (display-GPU dependent)
        - Overlay blending for panel: O(panel_area) in pixels
        - Should be disabled during performance benchmarks (no --visualise flag)
    
    References:
        - Chapter 3, Section 3.5: Debug instrumentation design
        - MediaPipe Hands solution output:
          https://mediapipe-studio.webapps.google.com/home
    """
    # Work on a copy to maintain immutability of input
    overlay = frame.copy()
    shapes = frame.shape
    h, w = shapes[0], shapes[1]
    
    # Unpack calculated_values for convenience
    fps = calculated_values.get('fps', 0)
    calibration_status = calculated_values.get('calibration_status', "calibrated")  # "calibrating" or "calibrated"
    calibration_time_remain = calculated_values.get('calibration_time_remain', 0)
    
    # =============================================================================
    # LAYER 9: FPS COUNTER
    # =============================================================================
    # FPS color gradient:
    #   - GREEN (>24 fps): Excellent, no frame drops at 60fps target
    #   - ORANGE (15-24 fps): Acceptable, some frame loss but interactive
    #   - RED (<15 fps): Poor, avoid for interactive tasks (feels laggy)
    fps_color = GREEN if fps > 24 else (ORANGE if fps > 15 else RED)
    cv2.putText(overlay, f"FPS: {fps:.1f}", (w - 150, 40), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, fps_color, 2)

    # =============================================================================
    # LAYER 10: CALIBRATION INDICATOR
    # =============================================================================
    # Pulsing animation during calibration improves UX (visual feedback that system is active)
    if calibration_status == "calibrating":
        # Pulsing effect: sin(t) oscillates between -1 and 1, normalize to 0-1 for intensity
        pulse = (math.sin(time.time() * 10) + 1) / 2  # Range: 0 to 1, ~10 Hz oscillation
        
        # Display calibration countdown + progress bar
        cv2.putText(overlay, f"CALIBRATING... {calibration_time_remain:.1f}s", (w//2 - 120, h - 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, YELLOW, 2)
        
        # Draw progress bar (fills left-to-right as calibration completes)
        # Total calibration duration is typically 3.0s (from config.CALIBRATION_DURATION)
        bar_width = int(200 * (3.0 - calibration_time_remain) / 3.0) if calibration_time_remain > 0 else 200
        bar_width = max(0, min(200, bar_width))  # Clamp to [0, 200] pixels
        cv2.rectangle(overlay, (w//2 - 100, h - 20), (w//2 - 100 + bar_width, h - 10), YELLOW, -1)
    else:
        # Calibration complete: green checkmark indicator
        cv2.circle(overlay, (w//2 - 50, h - 25), 5, GREEN, -1)  # Filled circle
        cv2.putText(overlay, "CALIBRATED", (w//2 - 40, h - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, GREEN, 2)

    # Early exit if no hands detected
    if not landmarks_list:
        return overlay

    # Pre-fetch gesture and hand data for text display
    wrist_coords = []
    gestures_list = calculated_values.get('gestures', [])
    handedness_list = calculated_values.get('handedness', [])
    pinch_dists = calculated_values.get('pinch_dists', [])
    pinch_speeds = calculated_values.get('pinch_speeds', [])
    wrist_coords_norm = calculated_values.get('wrist_coords', [])  # (x, y) in [-1, 1] range

    # =============================================================================
    # LAYER 7: NORMALIZED COORDINATES DATA PANEL
    # =============================================================================
    # Semi-transparent panel displaying wrist position, pinch metrics, and gesture state
    # Provides at-a-glance quantitative data during testing.
    panel_w, panel_h = 280, 180
    
    # Only render panel if frame is large enough
    if w >= panel_w and h >= panel_h:
        # Overlay semi-transparent dark rectangle (blends existing frame with black)
        sub_img = overlay[0:panel_h, 0:panel_w]
        dark_rect = np.zeros(sub_img.shape, dtype=np.uint8)
        res = cv2.addWeighted(sub_img, 0.5, dark_rect, 0.5, 0)  # 50% fade
        overlay[0:panel_h, 0:panel_w] = res
        
        # Text positioning within panel
        y_offset = 25
        row_h = 22  # Pixel height per line
        
        # Use first hand information if available
        if len(landmarks_list) > 0:
            h_idx = 0  # First hand
            wrist_norm = wrist_coords_norm[h_idx] if h_idx < len(wrist_coords_norm) else (0, 0)
            p_dist = pinch_dists[h_idx] if h_idx < len(pinch_dists) else 0
            p_speed = pinch_speeds[h_idx] if h_idx < len(pinch_speeds) else 0
            gest = gestures_list[h_idx] if h_idx < len(gestures_list) else "NONE"
            
            # Joystick values derived from wrist coordinates (normalized to [-1, 1])
            joy_x, joy_y = wrist_norm
            
            # Data lines to display
            lines = [
                f"WRIST X: {joy_x:+.2f}",      # Left-right tilt (normalized)
                f"WRIST Y: {joy_y:+.2f}",      # Up-down tilt (normalized)
                f"PINCH DIST: {p_dist:.3f}",   # Distance thumb-to-index (0-1)
                f"PINCH SPEED: {p_speed:.3f}/f", # Change per frame
                f"GESTURE: {gest}",             # Detected gesture label
                f"JOYSTICK X: {joy_x:+.2f}",   # Duplicate for clarity
                f"JOYSTICK Y: {joy_y:+.2f}"    # Duplicate for clarity
            ]
            
            # Render each line: label in cyan, value in white
            for i, line in enumerate(lines):
                if ":" in line:
                    label, val = line.split(":", 1)
                    cv2.putText(overlay, label + ":", (10, y_offset + i*row_h), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.45, CYAN, 1)
                    cv2.putText(overlay, val, (10 + 130, y_offset + i*row_h), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.45, WHITE, 1)
                else:
                    cv2.putText(overlay, line, (10, y_offset + i*row_h), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.45, WHITE, 1)

    # =============================================================================
    # LAYERS 1-8: PER-HAND VISUALIZATION (both hands rendered)
    # =============================================================================
    for i, landmarks in enumerate(landmarks_list):
        # =============================================================================
        # LAYER 5: HAND BOUNDING BOX
        # =============================================================================
        # Calculate axis-aligned bounding box from all landmarks
        x_min, y_min = w, h  # Initialize to frame size
        x_max, y_max = 0, 0
        pixels = []  # Cache pixel coords to avoid recomputing below
        
        for lm in landmarks:
            px, py = to_pixel(lm, shapes)
            pixels.append((px, py))
            # Update bounding box extents
            if px < x_min: x_min = px
            if px > x_max: x_max = px
            if py < y_min: y_min = py
            if py > y_max: y_max = py
        
        # Draw bounding box with 10px padding
        cv2.rectangle(overlay, (x_min - 10, y_min - 10), (x_max + 10, y_max + 10), WHITE, 1)
        
        # Label "LEFT" or "RIGHT" above bounding box
        hand_label = handedness_list[i] if i < len(handedness_list) else "?"
        cv2.putText(overlay, hand_label, (x_min - 10, y_min - 20), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, WHITE, 1)

        # =============================================================================
        # LAYERS 1-2: LANDMARK NUMBERS AND FINGER LABELS
        # =============================================================================
        for idx, lm in enumerate(landmarks):
            px, py = pixels[idx]
            
            # Landmark index number (0-20)
            cv2.putText(overlay, str(idx), (px + 5, py), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.3, WHITE, 1)
            
            # Dot at landmark position
            color = FINGER_COLOR_MAP.get(idx, WHITE)
            cv2.circle(overlay, (px, py), 3, color, -1)  # Filled circle
            
            # Finger tip label (only at tips: 4, 8, 12, 16, 20)
            if idx in FINGER_TIPS:
                cv2.putText(overlay, FINGER_TIPS[idx], (px - 10, py - 10), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

        # =============================================================================
        # LAYER 3: PINCH DISTANCE LINE (Thumb tip 4 → Index tip 8)
        # =============================================================================
        # Visual indicator for pinch gesture detection.
        # Line color and thickness encode pinch distance magnitude:
        #   - RED + thick = pinch active (distance < 0.05)
        #   - ORANGE = pinch imminent (distance 0.05-0.10)
        #   - GREEN + thin = hand open (distance > 0.10)
        # This helps developers see pinch thresholds triggering in real-time.
        
        thumb_tip = pixels[4]
        index_tip = pixels[8]
        dist_val = pinch_dists[i] if i < len(pinch_dists) else 0
        
        # Choose color based on distance magnitude
        if dist_val < 0.05:
            line_color = RED      # Pinch detected
        elif dist_val < 0.10:
            line_color = ORANGE   # Pinch threshold approaching
        else:
            line_color = GREEN    # Hand open
        
        # Line thickness correlates with proximity to pinch threshold
        # Thicker line = closer to activation (visual feedback for calibration)
        thickness = max(1, int(10 * (0.2 - dist_val))) if dist_val < 0.2 else 1
        
        cv2.line(overlay, thumb_tip, index_tip, line_color, thickness)
        
        # Label: distance value at midpoint
        mx, my = (thumb_tip[0] + index_tip[0]) // 2, (thumb_tip[1] + index_tip[1]) // 2
        cv2.putText(overlay, f"pinch: {dist_val:.3f}", (mx, my - 10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, line_color, 1)

        # =============================================================================
        # LAYER 4: WRIST VECTOR ARROW (Wrist 0 → Middle MCP 9)
        # =============================================================================
        # Arrow pointing from wrist center to middle finger MCP joint.
        # Indicates hand tilt direction (used to compute joystick X-axis).
        # Cyan color chosen to stand out from finger landmark colors.
        wrist = pixels[0]
        middle_mcp = pixels[9]
        cv2.arrowedLine(overlay, wrist, middle_mcp, CYAN, 2)  # Line width 2px

        # =============================================================================
        # LAYER 6: INTER-FINGER DISTANCE LINES
        # =============================================================================
        # Grey skeleton lines connecting finger tips: index→middle→ring→pinky
        # Shows hand shape and spread. Useful for detecting open-hand vs closed-fist states.
        pairs = [(8, 12), (12, 16), (16, 20)]  # (index_tip, middle_tip), etc.
        for p1, p2 in pairs:
            pt1 = pixels[p1]
            pt2 = pixels[p2]
            cv2.line(overlay, pt1, pt2, GREY, 1)  # Grey, thin line
            
            # Distance label at line midpoint
            lm1 = landmarks[p1]
            lm2 = landmarks[p2]
            d = math.sqrt((lm1.x - lm2.x)**2 + (lm1.y - lm2.y)**2)  # Normalized distance
            
            mx, my = (pt1[0] + pt2[0]) // 2, (pt1[1] + pt2[1]) // 2
            cv2.putText(overlay, f"{d:.3f}", (mx, my), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.3, GREY, 1)

        # Cache wrist pixel position for two-hand spread visualization
        wrist_coords.append(pixels[0])

    # =============================================================================
    # LAYER 8: TWO-HAND SPREAD LINE
    # =============================================================================
    # Magenta line connecting wrists when both hands are detected.
    # Distance metric used to trigger two-hand interactions
    # (e.g., pinch-both to activate special mode).
    if len(wrist_coords) == 2:
        pt1 = wrist_coords[0]
        pt2 = wrist_coords[1]
        cv2.line(overlay, pt1, pt2, MAGENTA, 2)  # Magenta, width 2px
        
        # Distance label at midpoint
        lm1 = landmarks_list[0][0]  # Wrist of first hand
        lm2 = landmarks_list[1][0]  # Wrist of second hand
        spread_val = math.sqrt((lm1.x - lm2.x)**2 + (lm1.y - lm2.y)**2)  # Normalized
        
        mx, my = (pt1[0] + pt2[0]) // 2, (pt1[1] + pt2[1]) // 2
        cv2.putText(overlay, f"SPREAD: {spread_val:.3f}", (mx, my - 10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, MAGENTA, 1)

    return overlay
