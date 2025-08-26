# video_thread.py

from PyQt5 import QtCore
import cv2
import numpy as np
from gestures import GestureDetector, GestureEvent
from config import CAMERA_INDEX, FRAME_WIDTH, FRAME_HEIGHT

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

