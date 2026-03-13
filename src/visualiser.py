import cv2
import numpy as np
import math
import time

# Colors (BGR)
WHITE = (255, 255, 255)
RED = (0, 0, 255)
GREEN = (0, 255, 0)
BLUE = (255, 0, 0)
YELLOW = (0, 255, 255)
PURPLE = (255, 0, 255)
ORANGE = (0, 165, 255)
CYAN = (255, 255, 0)
MAGENTA = (255, 0, 255)
GREY = (128, 128, 128)
BLACK = (0, 0, 0)

FINGER_COLOR_MAP = {
    0: WHITE,  # Wrist
    1: RED,    # Thumb
    2: RED,
    3: RED,
    4: RED,
    5: GREEN,  # Index
    6: GREEN,
    7: GREEN,
    8: GREEN,
    9: BLUE,   # Middle
    10: BLUE,
    11: BLUE,
    12: BLUE,
    13: YELLOW, # Ring
    14: YELLOW,
    15: YELLOW,
    16: YELLOW,
    17: PURPLE, # Pinky
    18: PURPLE,
    19: PURPLE,
    20: PURPLE
}

FINGER_TIPS = {
    4: "THUMB",
    8: "INDEX",
    12: "MIDDLE",
    16: "RING",
    20: "PINKY"
}

def to_pixel(landmark, shape):
    return int(landmark.x * shape[1]), int(landmark.y * shape[0])

def draw_overlay(frame, landmarks_list, calculated_values):
    # frame: BGR image
    # landmarks_list: list of hand landmarks (each is a list of normalized landmarks)
    # calculated_values: dict containing 'fps', 'calibration_status', 'gestures', 'handedness', etc.

    # Work on a copy
    overlay = frame.copy()
    shapes = frame.shape
    h, w = shapes[0], shapes[1]
    
    # Unpack values
    fps = calculated_values.get('fps', 0)
    calibration_status = calculated_values.get('calibration_status', "calibrated") # "calibrating" or "calibrated"
    calibration_time_remain = calculated_values.get('calibration_time_remain', 0)
    
    # 9. FPS COUNTER
    fps_color = GREEN if fps > 24 else (ORANGE if fps > 15 else RED)
    cv2.putText(overlay, f"FPS: {fps:.1f}", (w - 150, 40), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, fps_color, 2)

    # 10. CALIBRATION INDICATOR
    if calibration_status == "calibrating":
        # Pulsing effect
        pulse = (math.sin(time.time() * 10) + 1) / 2 # 0 to 1
        # Interpolate color or brightness? Let's just use Yellow
        pulse_color = (0, 255 * pulse, 255)
        
        cv2.putText(overlay, f"CALIBRATING... {calibration_time_remain:.1f}s", (w//2 - 120, h - 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, YELLOW, 2)
        # Draw bar
        bar_width = int(200 * (3.0 - calibration_time_remain) / 3.0) if calibration_time_remain > 0 else 200
        bar_width = max(0, min(200, bar_width))
        cv2.rectangle(overlay, (w//2 - 100, h - 20), (w//2 - 100 + bar_width, h - 10), YELLOW, -1)
    else:
        cv2.circle(overlay, (w//2 - 50, h - 25), 5, GREEN, -1)
        cv2.putText(overlay, "CALIBRATED", (w//2 - 40, h - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, GREEN, 2)

    if not landmarks_list:
        return overlay

    # Process hands
    wrist_coords = []
    
    gestures_list = calculated_values.get('gestures', [])
    handedness_list = calculated_values.get('handedness', [])
    pinch_dists = calculated_values.get('pinch_dists', [])
    pinch_speeds = calculated_values.get('pinch_speeds', [])
    wrist_coords_norm = calculated_values.get('wrist_coords', []) # (x, y) normalized

    # 6. NORMALISED COORDINATES PANEL
    # Draw semi-transparent background
    panel_w, panel_h = 280, 180
    
    # Check if frame is big enough
    if w >= panel_w and h >= panel_h:
        sub_img = overlay[0:panel_h, 0:panel_w]
        dark_rect = np.zeros(sub_img.shape, dtype=np.uint8)
        res = cv2.addWeighted(sub_img, 0.5, dark_rect, 0.5, 0)
        overlay[0:panel_h, 0:panel_w] = res
        
        y_offset = 25
        row_h = 22
        
        # Use first hand info if available
        if len(landmarks_list) > 0:
            h_idx = 0
            wrist_norm = wrist_coords_norm[h_idx] if h_idx < len(wrist_coords_norm) else (0,0)
            p_dist = pinch_dists[h_idx] if h_idx < len(pinch_dists) else 0
            p_speed = pinch_speeds[h_idx] if h_idx < len(pinch_speeds) else 0
            gest = gestures_list[h_idx] if h_idx < len(gestures_list) else "NONE"
            
            # JOYSTICK X: +0.84 - Using the normalized wrist coords which map to joystick
            # In gesture_test, norm_x is joystick x.
            joy_x, joy_y = wrist_norm
            
            lines = [
                # Example: "WRIST X: +0.42"
                f"WRIST X: {joy_x:+.2f}",
                f"WRIST Y: {joy_y:+.2f}",
                # Example: "PINCH DIST: 0.043"
                f"PINCH DIST: {p_dist:.3f}",
                # Example: "PINCH SPEED: 0.002/f"
                f"PINCH SPEED: {p_speed:.3f}/f",
                # Example: "GESTURE: OPEN_PALM"
                f"GESTURE: {gest}",
                # Example: "JOYSTICK X: +0.84" - Assuming same as wrist for now as per logic
                f"JOYSTICK X: {joy_x:+.2f}",
                f"JOYSTICK Y: {joy_y:+.2f}"
            ]
            
            for i, line in enumerate(lines):
                if ":" in line:
                    label, val = line.split(":", 1)
                    cv2.putText(overlay, label + ":", (10, y_offset + i*row_h), cv2.FONT_HERSHEY_SIMPLEX, 0.45, CYAN, 1)
                    cv2.putText(overlay, val, (10 + 130, y_offset + i*row_h), cv2.FONT_HERSHEY_SIMPLEX, 0.45, WHITE, 1)
                else:
                    cv2.putText(overlay, line, (10, y_offset + i*row_h), cv2.FONT_HERSHEY_SIMPLEX, 0.45, WHITE, 1)

    for i, landmarks in enumerate(landmarks_list):
        # 5. HAND BOUNDING BOX
        x_min, y_min = w, h
        x_max, y_max = 0, 0
        pixels = []
        for lm in landmarks:
            px, py = to_pixel(lm, shapes)
            pixels.append((px, py))
            if px < x_min: x_min = px
            if px > x_max: x_max = px
            if py < y_min: y_min = py
            if py > y_max: y_max = py
        
        # Bounding box
        # Slightly transparent feel - draw lines with lower alpha? 
        # cv2.rectangle doesn't support alpha directly on same image usually without addWeighted.
        # But prompt says "slightly transparent feel".
        # We can implement a simple overlay for the rect.
        # Or just draw thin white lines.
        cv2.rectangle(overlay, (x_min - 10, y_min - 10), (x_max + 10, y_max + 10), WHITE, 1)
        
        # Label "LEFT" or "RIGHT"
        hand_label = handedness_list[i] if i < len(handedness_list) else "?"
        cv2.putText(overlay, hand_label, (x_min - 10, y_min - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, WHITE, 1)

        # 1. LANDMARK NUMBERS & 2. FINGER LABELS
        for idx, lm in enumerate(landmarks):
            px, py = pixels[idx]
            
            # Number
            cv2.putText(overlay, str(idx), (px + 5, py), cv2.FONT_HERSHEY_SIMPLEX, 0.3, WHITE, 1)
            
            # Dot
            color = FINGER_COLOR_MAP.get(idx, WHITE)
            cv2.circle(overlay, (px, py), 3, color, -1)
            
            # Label
            if idx in FINGER_TIPS:
                cv2.putText(overlay, FINGER_TIPS[idx], (px - 10, py - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

        # 3. PINCH DISTANCE LINE (Thumb 4 - Index 8)
        thumb_tip = pixels[4]
        index_tip = pixels[8]
        dist_val = pinch_dists[i] if i < len(pinch_dists) else 0
        
        line_color = GREEN
        if dist_val < 0.05: line_color = RED
        elif dist_val < 0.10: line_color = ORANGE
        
        thickness = max(1, int(10 * (0.2 - dist_val))) if dist_val < 0.2 else 1
        
        cv2.line(overlay, thumb_tip, index_tip, line_color, thickness)
        mx, my = (thumb_tip[0] + index_tip[0]) // 2, (thumb_tip[1] + index_tip[1]) // 2
        cv2.putText(overlay, f"pinch: {dist_val:.3f}", (mx, my - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, line_color, 1)

        # 4. WRIST VECTOR ARROW (0 to 9)
        wrist = pixels[0]
        middle_mcp = pixels[9]
        cv2.arrowedLine(overlay, wrist, middle_mcp, CYAN, 2)

        # 7. INTER-FINGER DISTANCE LINES
        # 8-12, 12-16, 16-20
        pairs = [(8, 12), (12, 16), (16, 20)]
        for p1, p2 in pairs:
            pt1 = pixels[p1]
            pt2 = pixels[p2]
            cv2.line(overlay, pt1, pt2, GREY, 1)
            
            lm1 = landmarks[p1]
            lm2 = landmarks[p2]
            d = math.sqrt((lm1.x - lm2.x)**2 + (lm1.y - lm2.y)**2)
            
            mx, my = (pt1[0] + pt2[0]) // 2, (pt1[1] + pt2[1]) // 2
            cv2.putText(overlay, f"{d:.3f}", (mx, my), cv2.FONT_HERSHEY_SIMPLEX, 0.3, GREY, 1)

        wrist_coords.append(pixels[0])

    # 8. TWO-HAND SPREAD LINE
    if len(wrist_coords) == 2:
        pt1 = wrist_coords[0]
        pt2 = wrist_coords[1]
        cv2.line(overlay, pt1, pt2, MAGENTA, 2)
        
        lm1 = landmarks_list[0][0]
        lm2 = landmarks_list[1][0]
        spread_val = math.sqrt((lm1.x - lm2.x)**2 + (lm1.y - lm2.y)**2)
        
        mx, my = (pt1[0] + pt2[0]) // 2, (pt1[1] + pt2[1]) // 2
        cv2.putText(overlay, f"SPREAD: {spread_val:.3f}", (mx, my - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, MAGENTA, 1)

    return overlay
