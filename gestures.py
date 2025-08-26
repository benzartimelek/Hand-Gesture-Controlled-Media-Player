# gestures.py

from typing import Deque, Optional, Tuple
from collections import deque
import mediapipe as mp
import time
import math
import cv2
import numpy as np
from dataclasses import dataclass
from config import SWIPE_HISTORY, PINCH_DIST_PX, PALM_COOLDOWN_S, FONT


@dataclass
class GestureEvent:
    name: str
    data: Optional[float] = None


class GestureDetector:
    def __init__(self, frame_w: int, frame_h: int):
        self.frame_w = frame_w
        self.frame_h = frame_h

        self.hands = mp.solutions.hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=0.6,
            min_tracking_confidence=0.6,
            model_complexity=1,
        )
        self.drawer = mp.solutions.drawing_utils
        self.styles = mp.solutions.drawing_styles

        self.wrist_history: Deque[Tuple[float, float, float]] = deque(maxlen=SWIPE_HISTORY)  # (x,y,time)
        self.last_palm_time = 0.0
        self.last_point_time = 0.0
        self.point_cooldown = 0.7  # seconds
        self.pinch_mode = False
        self.pinch_ref_y = None  
        self.pinch_vol_ref = None
        self.vol_ema = None

    # Utility: convert normalized landmark to pixel coords
    def _np2px(self, lm) -> Tuple[int, int]:
        return int(lm.x * self.frame_w), int(lm.y * self.frame_h)

    def _count_fingers(self, lms) -> int:
        # Use simple heuristic vs wrist: for all fingers except thumb, tip.y < pip.y -> extended
        tips = [8, 12, 16, 20]
        pips = [6, 10, 14, 18]
        cnt = 0
        for t, p in zip(tips, pips):
            if lms[t].y < lms[p].y:
                cnt += 1
        # Thumb: tip.x < ip.x (for right hand; mirror later if left)
        # Without handedness, approximate by horizontal distance to index MCP
        if lms[4].x < lms[3].x:  # rough
            cnt += 1
        return cnt

    def _detect_pointing(self, lms) -> Optional[str]:
        # Count fingers (only index should be extended)
        tips = [8, 12, 16, 20]
        pips = [6, 10, 14, 18]
        extended = [lms[t].y < lms[p].y for t, p in zip(tips, pips)]
        
        # Only index extended
        if extended[0] and not any(extended[1:]):
            wrist_x, wrist_y = self._np2px(lms[0])
            index_x, index_y = self._np2px(lms[8])

            # Check horizontal distance
            horizontal_dist = abs(index_x - wrist_x)
            vertical_dist = abs(index_y - wrist_y)
            
            # Only trigger if pointing is more horizontal than vertical
            # and there's sufficient horizontal movement
            if horizontal_dist > 40 and horizontal_dist > vertical_dist * 1.5:
                if index_x > wrist_x:   # pointing right
                    return "point_right"
                elif index_x < wrist_x: # pointing left
                    return "point_left"
        return None

    def _get_pinch_distance(self, lms) -> float:
        # Calculate pixel distance between thumb tip (4) and index tip (8)
        x4, y4 = self._np2px(lms[4])
        x8, y8 = self._np2px(lms[8])
        return math.hypot(x8 - x4, y8 - y4)

    def _detect_pinch(self, lms) -> bool:
        # Check if pinch distance is below threshold
        return self._get_pinch_distance(lms) < PINCH_DIST_PX
    
    def _horizontal_motion(self) -> float:
        # return absolute horizontal displacement between oldest and newest wrist in history
        if len(self.wrist_history) < 2:
            return 0.0
        x0, _, _ = self.wrist_history[0]
        x1, _, _ = self.wrist_history[-1]
        return abs(x1 - x0)

    def process(self, frame_bgr: np.ndarray) -> Tuple[np.ndarray, Optional[GestureEvent]]:
        img_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        res = self.hands.process(img_rgb)
        event: Optional[GestureEvent] = None
        annotated = frame_bgr

        if res.multi_hand_landmarks:
            hand_lms = res.multi_hand_landmarks[0]
            # Draw
            self.drawer.draw_landmarks(
                annotated,
                hand_lms,
                mp.solutions.hands.HAND_CONNECTIONS,
                self.styles.get_default_hand_landmarks_style(),
                self.styles.get_default_hand_connections_style(),
            )

            lms = hand_lms.landmark
            # Update history for swipe
            wx, wy = self._np2px(lms[0])
            self.wrist_history.append((wx, wy, time.time()))
            
            # Pointing detection (uses cooldown)
            pointing = self._detect_pointing(lms)
            if pointing and (time.time() - self.last_point_time) > self.point_cooldown:
                self.last_point_time = time.time()
                if pointing == "point_right":
                    event = GestureEvent("next")
                else:
                    event = GestureEvent("previous")

            # Open palm -> toggle play/pause BUT only if hand is steady (not moving horizontally)
            fingers = self._count_fingers(lms)
            horiz_motion = self._horizontal_motion()
            motion_thresh = max(30, int(self.frame_w * 0.03))  # adapt to resolution
            if fingers >= 4 and horiz_motion < motion_thresh and (time.time() - self.last_palm_time) > PALM_COOLDOWN_S:
                event = GestureEvent('toggle_play')
                self.last_palm_time = time.time()

            # Pinch mode for volume
            is_pinch = self._detect_pinch(lms)
            
            if is_pinch and not self.pinch_mode:
                self.pinch_mode = True
                self.pinch_ref_y = self._np2px(lms[8])[1]  # Y position of index finger
                self.pinch_vol_ref = None  # set by caller when first volume seen
                cv2.putText(annotated, 'VOLUME MODE', (20, 60), FONT, 1.0, (0, 255, 255), 2)
            elif not is_pinch and self.pinch_mode:
                self.pinch_mode = False
                self.pinch_ref_y = None
                self.pinch_vol_ref = None

            if self.pinch_mode and self.pinch_ref_y is not None:
                idx_y = self._np2px(lms[8])[1]
                dy = (self.pinch_ref_y - idx_y)  # up is positive (screen coordinates)
                event = GestureEvent('volume_delta', data=dy)
                cv2.putText(annotated, f'ΔV raw={dy:.0f}px', (20, 90), FONT, 0.7, (0, 255, 255), 2)
        else:
            # reset histories if hand lost
            self.wrist_history.clear()
            self.pinch_mode = False
            self.pinch_ref_y = None
            self.pinch_vol_ref = None

        return annotated, event

