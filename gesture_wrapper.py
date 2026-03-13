import sys
import os
import asyncio

# Ensure src is in python path
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(current_dir, 'src')
sys.path.append(src_dir)

try:
    import gesture_test
except ImportError as e:
    print(f"Error importing src/gesture_test.py: {e}")
    sys.exit(1)

if __name__ == "__main__":
    print(f"Starting VisionInput Wrapper from {src_dir}...")
    try:
        asyncio.run(gesture_test.main())
    except KeyboardInterrupt:
        print("\nProgram stopped by user.")
    except Exception as e:
        print(f"Runtime error: {e}")
