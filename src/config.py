"""VisionInput configuration constants.

"""

# WebSocket
WEBSOCKET_ENABLED = False  # Set to True to enable WebSocket server for real-time telemetry , Keep False unless you are actively using websocket clients.
WEBSOCKET_HOST = "localhost" #
WEBSOCKET_PORT = 8765
MAX_WEBSOCKET_CLIENTS = 5

# Joystick Control
SENSITIVITY = 2.0
TILT_GAIN = 4.0
NEUTRAL_Y_OFFSET = 0.65
EMA_ALPHA = 0.3
DEAD_ZONE = 0.15  # Applied in smoothing/output layer

# Preprocessing
PREPROCESS_CONTRAST_ENABLED = False
PREPROCESS_ALPHA = 1
PREPROCESS_BETA = 10

# Gesture Detection Thresholds
PINCH_INDEX = 0.05
PINCH_MIDDLE = 0.06
PINCH_RING = 0.07
PINCH_PINKY = 0.08

# Startup
CALIBRATION_DURATION = 3.0

# Logging
LOG_LATENCY_DEFAULT = False
LATENCY_TRIALS = 200
LATENCY_LOG_DIR = "logs/latency"
LATENCY_LOG_FILE = "latency_log.csv"
BENCHMARK_LOG_DIR = "logs/benchmark"
BENCHMARK_LOG_FILE = "benchmark_runs.csv"

# MediaPipe
DETECTION_CONFIDENCE = 0.5
TRACKING_CONFIDENCE = 0.5

# Camera
CAMERA_REQUEST_FPS = 60
CAMERA_REQUEST_WIDTH = 1920
CAMERA_REQUEST_HEIGHT = 1080

# Two-hand control
INTER_HAND_NEUTRAL_EPSILON = 0.05
ANGLE_NORMALIZATION = 0.628  # pi/5
