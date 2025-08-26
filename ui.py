# ui.py

import os, time
import sys 
from typing import List
import numpy as np
import cv2
from PyQt5 import QtCore, QtGui, QtWidgets
from video_thread import VideoThread
from gestures import GestureEvent
from media_player import MediaPlayer
from config import FRAME_HEIGHT,FRAME_WIDTH, VOL_PER_100PX, PINCH_SMOOTHING

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

