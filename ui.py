# ui.py

import os, time
import urllib.parse
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
        self.setWindowTitle("Hand Gesture Media Player 🎶")
        self.setGeometry(100, 100, FRAME_WIDTH + 350, FRAME_HEIGHT + 100)

        # Collect media files
        self.media_paths = self._scan_media(media_dir)
        self.player = MediaPlayer(self.media_paths)

        
        # Central widget + layouts
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QHBoxLayout(central)

        # --- Video Preview Area ---
        video_frame = QtWidgets.QFrame()
        video_frame.setStyleSheet("background:#000; border:2px solid #444; border-radius:12px;")
        vbox_video = QtWidgets.QVBoxLayout(video_frame)

        self.video_label = QtWidgets.QLabel()
        self.video_label.setFixedSize(FRAME_WIDTH, FRAME_HEIGHT)
        vbox_video.addWidget(self.video_label)

        # Overlay label for gestures
        self.overlay_lbl = QtWidgets.QLabel("", self.video_label)
        self.overlay_lbl.setAlignment(QtCore.Qt.AlignCenter)
        self.overlay_lbl.setStyleSheet("""
            QLabel {
                background-color: rgba(0,0,0,120);
                color: #00e676;
                font-size: 22px;
                font-weight: bold;
                border-radius: 10px;
            }
        """)
        self.overlay_lbl.setGeometry(50, 30, 300, 50)
        self.overlay_lbl.hide()

        layout.addWidget(video_frame)

        # --- Side Panel ---
        side_panel = QtWidgets.QFrame()
        side_panel.setStyleSheet("QFrame { background-color:#2c2c2c; border-radius:12px; }")
        side_layout = QtWidgets.QVBoxLayout(side_panel)

        # Title
        self.title_lbl = QtWidgets.QLabel("Title: -")
        self.title_lbl.setObjectName("titleLabel")
        self.title_lbl.setWordWrap(True)
        side_layout.addWidget(self.title_lbl)

        # Status
        self.status_lbl = QtWidgets.QLabel("Status: Idle")
        self.status_lbl.setObjectName("statusLabel")
        side_layout.addWidget(self.status_lbl)

        # Gesture
        self.gesture_lbl = QtWidgets.QLabel("Gesture: -")
        self.gesture_lbl.setObjectName("gestureLabel")
        side_layout.addWidget(self.gesture_lbl)

        # Progress bar (seekable slider)
        self.progress = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.sliderReleased.connect(self.seek_track)
        side_layout.addWidget(self.progress)

        # Track time label (e.g., 01:23 / 04:56)
        self.time_lbl = QtWidgets.QLabel("00:00 / 00:00")
        self.time_lbl.setAlignment(QtCore.Qt.AlignCenter)
        self.time_lbl.setStyleSheet("font-size:14px; color:#bbb;")
        side_layout.addWidget(self.time_lbl)

        # Playback buttons (optional fallback)
        btn_layout = QtWidgets.QHBoxLayout()
        self.btn_prev = QtWidgets.QPushButton("⏮")
        self.btn_play = QtWidgets.QPushButton("⏯")
        self.btn_next = QtWidgets.QPushButton("⏭")
        for b in [self.btn_prev, self.btn_play, self.btn_next]:
            b.setFixedSize(50, 50)
            b.setStyleSheet("""
                QPushButton {
                    font-size: 22px; 
                    border-radius: 8px; 
                    background:#444; 
                    color:white;
                }
                QPushButton:pressed {
                    background:#00bcd4;  /* 🔹 Blue when pressed */
                }
            """)
            btn_layout.addWidget(b)
        side_layout.addLayout(btn_layout)

        # Hook up playback buttons
        self.btn_play.clicked.connect(self.player.play_pause)
        self.btn_next.clicked.connect(self.player.next)
        self.btn_prev.clicked.connect(self.player.previous)

        # Volume slider
        self.vol_slider = QtWidgets.QSlider(QtCore.Qt.Vertical)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(50)
        self.vol_slider.valueChanged.connect(self._on_slider)
        side_layout.addWidget(self.vol_slider) 
        
        # Instructions
        help_text = (
            "Gestures:\n"
            "🖐 Open palm → Play/Pause\n"
            "👉 Point Right → Next\n"
            "👈 Point Left → Previous\n"
            "👌 Pinch + Move Up/Down → Volume"
        )
        self.help_lbl = QtWidgets.QLabel(help_text)
        self.help_lbl.setStyleSheet("font-size:20px; color:#ccc;")
        side_layout.addWidget(self.help_lbl)

        side_layout.addStretch(1)
        layout.addWidget(side_panel)

        # Thread for camera
        self.thread = VideoThread()
        self.thread.frame_ready.connect(self.update_frame)
        self.thread.gesture_event.connect(self.on_gesture)
        self.thread.start()

        # Volume tracking
        self.cur_volume = 50
        self.player.set_volume(self.cur_volume)
        self._last_vol_ts = time.time()

        # Timer to update progress
        self.progress_timer = QtCore.QTimer(self)
        self.progress_timer.timeout.connect(self.update_progress)
        self.progress_timer.start(500)

        # Global stylesheet
        self.setStyleSheet("""
            QWidget { background-color: #1e1e1e; color: #f0f0f0; font-family: 'Segoe UI'; font-size: 16px; }
            QLabel#titleLabel { font-size: 22px; font-weight: bold; color: #00bcd4; }
            QLabel#statusLabel { font-size: 18px; color: #ff9800; }
            QLabel#gestureLabel { font-size: 18px; color: #8bc34a; }
            
            QSlider::groove:vertical {
                background: #00bcd4;  
                width: 8px;
                border-radius: 4px;
            }
            QSlider::handle:vertical {
                background: #666;     
                height: 20px;
                margin: -2px;
                border-radius: 6px;
            }
            QSlider::add-page:vertical { background: #00bcd4; }  /* 🔹 lower side */
            QSlider::sub-page:vertical { background: #666; }     /* 🔹 upper side */
        """)

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

    def update_progress(self):
        duration = self.player.duration()
        pos = self.player.position()
        if duration > 0:
            self.progress.setRange(0, duration)
            self.progress.setValue(pos)

            # Format mm:ss
            def fmt(ms):
                s = int(ms // 1000)
                m, s = divmod(s, 60)
                return f"{m:02}:{s:02}"

            self.time_lbl.setText(f"{fmt(pos)} / {fmt(duration)}")
        else:
            self.progress.setValue(0)
            self.time_lbl.setText("00:00 / 00:00")

    def seek_track(self):
        duration = self.player.duration()
        new_pos = self.progress.value()
        if duration > 0:
            self.player.set_position(new_pos)

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

        # Show overlay briefly
        self.overlay_lbl.setText(name.upper())
        self.overlay_lbl.show()
        QtCore.QTimer.singleShot(1000, self.overlay_lbl.hide)

        def press_button_temporarily(button):
            button.setDown(True)
            QtCore.QTimer.singleShot(200, lambda: button.setDown(False))  # release after 200ms

        if name == 'toggle_play':
            self.player.play_pause()
            self.title_lbl.setText("Title: " + urllib.parse.unquote(os.path.basename(self.player.title())))
            self.status_lbl.setText("Status: Play/Pause")
            press_button_temporarily(self.btn_play)

        elif name == "next":
            self.player.next()
            self.title_lbl.setText("Title: " + urllib.parse.unquote(os.path.basename(self.player.title())))
            self.status_lbl.setText("Status: Next")
            press_button_temporarily(self.btn_next)

        elif name == "previous":
            self.player.previous()
            self.title_lbl.setText("Title: " + urllib.parse.unquote(os.path.basename(self.player.title())))
            self.status_lbl.setText("Status: Previous")
            press_button_temporarily(self.btn_prev)

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

