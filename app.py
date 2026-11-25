# Hand Gesture Controlled Media Player

import os, sys, ctypes, platform
from PyQt5 import QtWidgets
from ui import MainWindow

if platform.system() == "Windows":
    vlc_dll_path = r"C:\Program Files\VideoLAN\VLC\libvlc.dll"
    if os.path.exists(vlc_dll_path):
        ctypes.CDLL(vlc_dll_path)
    else:
        raise FileNotFoundError("VLC not found at the default path. Install 64-bit VLC or update vlc_dll_path.")



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
