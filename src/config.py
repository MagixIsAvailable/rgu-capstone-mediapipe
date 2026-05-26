"""VisionInput configuration constants.

How to tune safely:
1) Change one setting at a time.
2) Re-run with --visualise and test.
3) Keep notes of what improved/worsened.
"""

# WebSocket
# Use only when a browser/client needs live telemetry.
# Keep disabled for normal controller-only usage.
WEBSOCKET_ENABLED = True
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
CALIBRATION_DURATION = 0.5  # seconds (short warmup before gesture detection)

# Activation (burst) settings
ACTIVATION_BURSTS_REQUIRED = 3
ACTIVATION_MIN_GAP_S = 0.3  # minimum gap between bursts to debounce
DEACTIVATION_BURSTS_REQUIRED = 3
ACTIVATION_BIMANUAL_WINDOW_S = 10.0  # time window for both hands to complete bursts

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

# Finger bend detection
# Threshold angle (degrees) at PIP joint above which finger is considered 'bent'
FINGER_BEND_ANGLE_DEG = 30.0

# Window behaviour (OpenCV window flags)
WINDOW_ALWAYS_ON_TOP = True

# Activation reset: if bursts are not completed within this window, reset count
ACTIVATION_RESET_S = 5.0

# -------------------------
# Runtime-loadable JSON config
# -------------------------
import json
import os

# Path to editable JSON config (project-root relative)
_THIS_DIR = os.path.dirname(__file__)
_PROJECT_ROOT = os.path.abspath(os.path.join(_THIS_DIR, os.pardir))
GESTURE_CONFIG_PATH = os.path.join(_PROJECT_ROOT, 'config', 'gesture_config.json')


def _apply_json_overrides(cfg: dict):
	"""Apply values from loaded JSON onto module-level globals where applicable."""
	global FINGER_BEND_ANGLE_DEG, PINCH_INDEX, PINCH_MIDDLE, PINCH_RING, PINCH_PINKY
	global EMA_ALPHA, DEAD_ZONE, ACTIVATION_BURSTS_REQUIRED, DEACTIVATION_BURSTS_REQUIRED
	global CALIBRATION_DURATION

	if not isinstance(cfg, dict):
		return

	if 'finger_bend_angle_deg' in cfg:
		try:
			FINGER_BEND_ANGLE_DEG = float(cfg['finger_bend_angle_deg'])
		except Exception:
			pass

	pt = cfg.get('pinch_thresholds') or {}
	try:
		PINCH_INDEX = float(pt.get('index', PINCH_INDEX))
		PINCH_MIDDLE = float(pt.get('middle', PINCH_MIDDLE))
		PINCH_RING = float(pt.get('ring', PINCH_RING))
		PINCH_PINKY = float(pt.get('pinky', PINCH_PINKY))
	except Exception:
		pass

	if 'smoothing_alpha' in cfg:
		try:
			EMA_ALPHA = float(cfg['smoothing_alpha'])
		except Exception:
			pass

	if 'dead_zone' in cfg:
		try:
			DEAD_ZONE = float(cfg['dead_zone'])
		except Exception:
			pass

	if 'activation_bursts_required' in cfg:
		try:
			ACTIVATION_BURSTS_REQUIRED = int(cfg['activation_bursts_required'])
		except Exception:
			pass

	if 'deactivation_bursts_required' in cfg:
		try:
			DEACTIVATION_BURSTS_REQUIRED = int(cfg['deactivation_bursts_required'])
		except Exception:
			pass

	if 'calibration_duration' in cfg:
		try:
			CALIBRATION_DURATION = float(cfg['calibration_duration'])
		except Exception:
			pass


def load_gesture_config(path: str = None) -> dict:
	"""Load gesture configuration from JSON file and apply overrides.

	Returns the parsed config dict (or empty dict on error).
	"""
	p = path or GESTURE_CONFIG_PATH
	try:
		with open(p, 'r', encoding='utf-8') as f:
			cfg = json.load(f)
		_apply_json_overrides(cfg)
		return cfg
	except Exception:
		return {}


def save_gesture_config(cfg: dict, path: str = None) -> bool:
	"""Atomically save gesture config JSON. Returns True on success."""
	p = path or GESTURE_CONFIG_PATH
	try:
		os.makedirs(os.path.dirname(p), exist_ok=True)
		# backup existing
		if os.path.exists(p):
			bak = p + '.bak.' + time.strftime('%Y%m%dT%H%M%S')
			try:
				os.replace(p, bak)
			except Exception:
				# best-effort backup
				pass
		tmp = p + '.tmp'
		with open(tmp, 'w', encoding='utf-8') as f:
			json.dump(cfg, f, indent=2)
		os.replace(tmp, p)
		# apply after save
		_apply_json_overrides(cfg)
		return True
	except Exception:
		return False


# Attempt to load config at import time (silent failure keeps defaults)
_ = load_gesture_config()
