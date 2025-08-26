"""
Hand Gesture Controlled Media Player
====================================
Python + OpenCV + MediaPipe Hands + PyQt5 GUI + python-vlc

Gestures (right hand):
- Open palm (>=4 fingers extended)  -> Toggle Play/Pause
- Point right                       -> Next track
- Point left                        -> Previous track
- Pinch (thumb+index touching)      -> Volume mode: move hand up/down to change volume

Notes
-----
- Requires 64-bit VLC installed on your system (python-vlc binds to it).
- Tested with a single webcam at index 0. Change CAMERA_INDEX if needed.

Install
-------
python -m venv .venv && .venv/bin/pip install --upgrade pip
pip install opencv-python mediapipe PyQt5 python-vlc numpy

Run
---
.venv/bin/python gesture_media_player.py /path/to/media/folder

"""

import os, ctypes
import sys
import time
import math
from collections import deque
from dataclasses import dataclass
from typing import Deque, List, Optional, Tuple

import cv2
import numpy as np

# GUI
from PyQt5 import QtCore, QtGui, QtWidgets

# Media control 
import vlc

# Manually load libvlc.dll
vlc_dll_path = r"C:\Program Files\VideoLAN\VLC\libvlc.dll"
if os.path.exists(vlc_dll_path):
    ctypes.CDLL(vlc_dll_path)
else:
    raise FileNotFoundError("VLC not found, install it and update vlc_dll_path")


# MediaPipe Hands
import mediapipe as mp

# -------------------------------
# Configurable parameters
# -------------------------------
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
VOL_PER_100PX = 10              # change in volume (0-100) per 100px vertical movement while pinching

# UI
FONT = cv2.FONT_HERSHEY_SIMPLEX


@dataclass
class GestureEvent:
    name: str
    data: Optional[float] = None


class MediaPlayer:
    """Simple playlist wrapper around VLC"""
    def __init__(self, media_paths: List[str]):
        if not media_paths:
            raise ValueError("No media files found.")
        self.instance = vlc.Instance()
        self.player = self.instance.media_list_player_new()
        self.list_inst = self.instance.media_list_new()
        for p in media_paths:
            self.list_inst.add_media(self.instance.media_new(p))
        self.player.set_media_list(self.list_inst)
        self._is_playing = False

    def play_pause(self):
        if self._is_playing:
            self.player.pause()
            self._is_playing = False
        else:
            # If nothing started yet, play()
            if self.player.get_state() in (vlc.State.NothingSpecial, vlc.State.Stopped):
                self.player.play()
            else:
                self.player.pause()
            self._is_playing = True

    def next(self):
        self.player.next()
        self._is_playing = True

    def previous(self):
        self.player.previous()
        self._is_playing = True

    def set_volume(self, vol: int):
        vol = max(0, min(100, int(vol)))
        # set_volume on media_list_player delegates to underlying player(s)
        # Create a normal player and set audio volume when available
        mlp = self.player.get_media_player()
        if mlp:
            mlp.audio_set_volume(vol)

    def get_volume(self) -> int:
        mlp = self.player.get_media_player()
        if mlp:
            v = mlp.audio_get_volume()
            return 0 if v < 0 else v
        return 0

    def title(self) -> str:
        mdp = self.player.get_media_player()
        if mdp and mdp.get_media():
            return mdp.get_media().get_mrl().split('/')[-1]
        return ""


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
        self.wave_history: Deque[Tuple[float, float]] = deque(maxlen=10)  # (x,time) for wave detection
        self.last_palm_time = 0.0
        self.last_point_time = 0.0
        self.last_wave_time = 0.0
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
    
    def _detect_wave(self, lms) -> bool:
        # Wave detection: open hand moving left-right repeatedly
        fingers = self._count_fingers(lms)
        if fingers < 4:  # Need open hand for wave
            self.wave_history.clear()  # Reset if not open hand
            return False
            
        # Track wrist horizontal position over time
        wx, _ = self._np2px(lms[0])
        current_time = time.time()
        self.wave_history.append((wx, current_time))
        
        # Need enough history to detect wave pattern
        if len(self.wave_history) < 8:
            return False
            
        # Check for oscillating horizontal movement (wave pattern)
        positions = [pos for pos, _ in self.wave_history]
        times = [t for _, t in self.wave_history]
        
        # Must be within recent timeframe (2 seconds)
        if current_time - times[0] > 2.0:
            return False
        
        # Calculate total horizontal range of movement
        min_pos = min(positions)
        max_pos = max(positions)
        total_range = max_pos - min_pos
        
        # Must have significant horizontal movement
        if total_range < 80:  # at least 80px total range
            return False
            
        # Look for direction changes (peaks and valleys)
        direction_changes = 0
        for i in range(1, len(positions) - 1):
            # Check if this is a local maximum or minimum
            if (positions[i] > positions[i-1] and positions[i] > positions[i+1]) or \
               (positions[i] < positions[i-1] and positions[i] < positions[i+1]):
                direction_changes += 1
        
        # Wave detected if we have multiple direction changes
        is_wave = direction_changes >= 3
        
        # Debug info
        if len(self.wave_history) >= 8:
            print(f"Wave debug - fingers: {fingers}, range: {total_range}, changes: {direction_changes}, is_wave: {is_wave}")
        
        return is_wave
    
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
            # Wave detection for exit
            if self._detect_wave(lms) and (time.time() - self.last_wave_time) > 2.0:
                event = GestureEvent('wave_exit')
                self.last_wave_time = time.time() 

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
            self.wave_history.clear()
            self.pinch_mode = False
            self.pinch_ref_y = None
            self.pinch_vol_ref = None

        return annotated, event


class VideoThread(QtCore.QThread):
    frame_ready = QtCore.pyqtSignal(np.ndarray)
    gesture_event = QtCore.pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cap = None
        self.detector = GestureDetector(FRAME_WIDTH, FRAME_HEIGHT)
        self._running = True

    def run(self):
        self.cap = cv2.VideoCapture(CAMERA_INDEX)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
        if not self.cap.isOpened():
            print("ERROR: Camera not available")
            return
        while self._running:
            ok, frame = self.cap.read()
            if not ok:
                continue
            frame = cv2.flip(frame, 1)  # mirror for natural interaction
            annotated, event = self.detector.process(frame)
            self.frame_ready.emit(annotated)
            if event:
                self.gesture_event.emit(event)
        self.cap.release()

    def stop(self):
        self._running = False
        self.wait(500)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, media_dir: str):
        super().__init__()
        self.setWindowTitle("Hand Gesture Media Player")
        self.setGeometry(100, 100, FRAME_WIDTH + 300, FRAME_HEIGHT + 80)

        # Collect media files
        self.media_paths = self._scan_media(media_dir)
        self.player = MediaPlayer(self.media_paths)

        # UI widgets
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QHBoxLayout(central)

        # Video preview
        self.video_label = QtWidgets.QLabel()
        self.video_label.setFixedSize(FRAME_WIDTH, FRAME_HEIGHT)
        self.video_label.setStyleSheet("background:#000;")
        layout.addWidget(self.video_label)

        # Side panel
        side = QtWidgets.QVBoxLayout()
        layout.addLayout(side)

        self.title_lbl = QtWidgets.QLabel("Title: ")
        self.title_lbl.setWordWrap(True)
        self.title_lbl.setStyleSheet("font-size:16px;font-weight:bold;")
        side.addWidget(self.title_lbl)

        self.status_lbl = QtWidgets.QLabel("Status: Idle")
        side.addWidget(self.status_lbl)

        self.gesture_lbl = QtWidgets.QLabel("Gesture: -")
        side.addWidget(self.gesture_lbl)

        self.vol_slider = QtWidgets.QSlider(QtCore.Qt.Vertical)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(50)
        self.vol_slider.valueChanged.connect(self._on_slider)
        side.addWidget(self.vol_slider)

        # Instructions
        help_text = (
            "Gestures:\n"
            " - Open palm: Play/Pause\n"
            " - Swipe Right/Left: Next/Previous\n"
            " - Pinch + move Up/Down: Volume\n"
        )
        self.help_lbl = QtWidgets.QLabel(help_text)
        side.addWidget(self.help_lbl)
        side.addStretch(1)

        # Thread for camera
        self.thread = VideoThread()
        self.thread.frame_ready.connect(self.update_frame)
        self.thread.gesture_event.connect(self.on_gesture)
        self.thread.start()

        # Internal volume tracking for pinch EMA
        self.cur_volume = 50
        self.player.set_volume(self.cur_volume)
        self._last_vol_ts = time.time()

    # --- UI helpers ---
    def _scan_media(self, root: str) -> List[str]:
        exts = {'.mp3', '.wav', '.mp4', '.m4a', '.aac', '.flac', '.avi', '.mkv', '.mov'}
        paths = []
        for dirpath, _, filenames in os.walk(root):
            for f in filenames:
                if os.path.splitext(f)[1].lower() in exts:
                    paths.append(os.path.join(dirpath, f))
        if not paths:
            raise SystemExit("No media files found in " + root)
        return paths

    @QtCore.pyqtSlot()
    def _on_slider(self):
        self.cur_volume = self.vol_slider.value()
        self.player.set_volume(self.cur_volume)
        self.status_lbl.setText(f"Status: Volume {self.cur_volume}")

    @QtCore.pyqtSlot(np.ndarray)
    def update_frame(self, frame: np.ndarray):
        # Convert BGR to RGB and set to QLabel
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QtGui.QImage(rgb.data, w, h, ch * w, QtGui.QImage.Format_RGB888)
        pix = QtGui.QPixmap.fromImage(qimg)
        self.video_label.setPixmap(pix)

    @QtCore.pyqtSlot(object)
    def on_gesture(self, event: GestureEvent):
        name = event.name
        self.gesture_lbl.setText(f"Gesture: {name}")

        if name == 'toggle_play':
            self.player.play_pause()
            self.status_lbl.setText("Status: Play/Pause")

        elif name == "next":
            self.player.next()
            self.title_lbl.setText("Title: " + self.player.title())
            self.status_lbl.setText("Status: Next")

        elif name == "previous":
            self.player.previous()
            self.title_lbl.setText("Title: " + self.player.title())
            self.status_lbl.setText("Status: Previous")
        
        elif name == 'wave_exit':
            self.status_lbl.setText("Status: Wave detected - Exiting...")
            QtCore.QTimer.singleShot(500, self.close)  # Exit after 500ms delay

        elif name == 'volume_delta' and event.data is not None:
            # Convert dy (pixels) to volume change
            dy = float(event.data)
            dv = (dy / 100.0) * VOL_PER_100PX
            # Smooth
            new_vol = self.cur_volume + dv
            self.cur_volume = max(0, min(100, int(round((1-PINCH_SMOOTHING)*new_vol + PINCH_SMOOTHING*self.cur_volume))))
            self.player.set_volume(self.cur_volume)
            self.vol_slider.blockSignals(True)
            self.vol_slider.setValue(self.cur_volume)
            self.vol_slider.blockSignals(False)
            self.status_lbl.setText(f"Status: Volume {self.cur_volume}")

    def closeEvent(self, e: QtGui.QCloseEvent):
        self.thread.stop()
        return super().closeEvent(e)


def main():
    if len(sys.argv) < 2:
        print("Usage: python gesture_media_player.py <media_folder>")
        sys.exit(1)
    media_dir = sys.argv[1]
    if not os.path.isdir(media_dir):
        print("Not a directory:", media_dir)
        sys.exit(1)

    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow(media_dir)
    win.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
