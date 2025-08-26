# Hand Gesture Controlled Media Player

A Python application that lets you control media playback using hand gestures detected from your webcam. Built with OpenCV, MediaPipe Hands, PyQt5 GUI, and python-vlc.

## Features

- **Open palm (≥4 fingers extended):** Toggle Play/Pause
- **Point right:** Next track
- **Point left:** Previous track
- **Pinch (thumb + index touching):** Volume mode (move hand up/down to change volume)

## Requirements

- Python 3.8+
- 64-bit VLC installed on your system ([Download VLC](https://www.videolan.org/vlc/))
- Webcam.

## Installation

1. Create a virtual environment and install dependencies:
    ```sh
    python -m venv .venv
    .venv/bin/pip install --upgrade pip
    pip install -r requirements.txt
    ```

2. Make sure VLC is installed at `C:\Program Files\VideoLAN\VLC\libvlc.dll` (or update the path in [`app.py`](app.py)).

## Usage

1. Place your media files (mp3, wav, mp4, etc.) in a folder, e.g. `media/`.
2. Run the application:
    ```sh
    python app.py media/
    ```
    or
    ```sh
    python app.py /path/to/your/media/folder
    ```

## File Structure

- [`app.py`](app.py): Main entry point.
- [`ui.py`](ui.py): PyQt5 GUI and gesture handling.
- [`video_thread.py`](video_thread.py): Camera capture and gesture detection thread.
- [`gestures.py`](gestures.py): Gesture recognition logic.
- [`media_player.py`](media_player.py): VLC-based media player.
- [`config.py`](config.py): Configuration parameters.
- [`requirements.txt`](requirements.txt): Python dependencies.

## Notes

- Tested with a single webcam at index 0. Change `CAMERA_INDEX` in [`config.py`](config.py) if needed.
- Supports common audio and video formats.

##