import sys
from unittest.mock import MagicMock
sys.modules['sounddevice'] = MagicMock()

import mediapipe as mp
print(f"Dir mp: {dir(mp)}")
try:
    import mediapipe.python.solutions as solutions
    print("Found mediapipe.python.solutions")
except ImportError:
    print("Could not import mediapipe.python.solutions")

try:
    import mediapipe.solutions as solutions
    print("Found mediapipe.solutions")
except ImportError:
    print("Could not import mediapipe.solutions")
