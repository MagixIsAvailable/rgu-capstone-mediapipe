"""VisionInput configuration constants.

How to tune safely:
1) Change one setting at a time.
2) Re-run with --visualise and test.
3) Keep notes of what improved/worsened.
"""

# WebSocket
# Use only when a browser/client needs live telemetry.
# Keep disabled for normal controller-only usage.
WEBSOCKET_ENABLED = False
# Host and port used when websocket is enabled.
WEBSOCKET_HOST = "localhost"
WEBSOCKET_PORT = 8765
# Safety cap for connected websocket clients.
MAX_WEBSOCKET_CLIENTS = 5

# Joystick Control
# Higher = less physical movement required.
SENSITIVITY = 2.0
# Higher = faster/more aggressive stick response.
TILT_GAIN = 4.0
# Compensates Y drift at rest (single-hand fallback path).
NEUTRAL_Y_OFFSET = 0.65
# Smoothing factor: lower is smoother (but adds lag), higher is snappier.
EMA_ALPHA = 0.3
# Neutral cut-off to suppress jitter around center.
DEAD_ZONE = 0.15

# Preprocessing
# Enable only if tracking is unstable in poor lighting.
PREPROCESS_CONTRAST_ENABLED = False
# Contrast gain when preprocessing is enabled.
PREPROCESS_ALPHA = 1
# Brightness offset when preprocessing is enabled.
PREPROCESS_BETA = 10

# Gesture Detection Thresholds
# Pinch thresholds by finger; increase if pinch is hard to trigger,
# decrease if false pinches occur.
PINCH_INDEX = 0.05
PINCH_MIDDLE = 0.06
PINCH_RING = 0.07
PINCH_PINKY = 0.08

# Startup
# Time window before controller output activates.
CALIBRATION_DURATION = 3.0

# Logging
# If True, latency logging starts without requiring --log-latency.
LOG_LATENCY_DEFAULT = False
# Number of non-neutral samples to capture before auto-stop.
LATENCY_TRIALS = 100
# Output location for latency CSV files.
LATENCY_LOG_DIR = "logs/latency"
LATENCY_LOG_FILE = "latency_log.csv"
# Output location for benchmark CSV files.
BENCHMARK_LOG_DIR = "logs/benchmark"
BENCHMARK_LOG_FILE = "benchmark_runs.csv"

# MediaPipe
# Raise for stricter detection/tracking (fewer false positives, more misses).
# Lower for permissive behavior (more robust in hard scenes, more noise).
DETECTION_CONFIDENCE = 0.5
TRACKING_CONFIDENCE = 0.5

# Camera
# Requested capture mode; actual negotiated mode depends on camera/driver.
CAMERA_REQUEST_FPS = 60
CAMERA_REQUEST_WIDTH = 1920
CAMERA_REQUEST_HEIGHT = 1080

# Two-hand control
# Neutral tolerance for tiny inter-hand deltas.
INTER_HAND_NEUTRAL_EPSILON = 0.05
# Scales inter-hand angle to joystick Y response.
ANGLE_NORMALIZATION = 0.628  # approximately pi/5
