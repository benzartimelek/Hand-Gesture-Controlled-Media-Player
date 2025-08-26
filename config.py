# config.py

import cv2

# Configurable parameters
CAMERA_INDEX = 0
FRAME_WIDTH = 960
FRAME_HEIGHT = 540

# Gesture thresholds
PINCH_DIST_PX = 50              # thumb-index tip distance to enter pinch mode (will be scaled by image width)
SWIPE_HISTORY = 6               # frames to look back for swipe
SWIPE_MIN_PIXELS = 80          # min wrist delta X for swipe
SWIPE_COOLDOWN_S = 0.7
PALM_COOLDOWN_S = 0.8
PINCH_SMOOTHING = 0.8           # EMA smoothing for volume changes
VOL_PER_100PX = 10           # change in volume (0-100) per 100px vertical movement while pinching

# UI
FONT = cv2.FONT_HERSHEY_SIMPLEX