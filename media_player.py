# media_player.py

import vlc
from typing import List

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

    def duration(self) -> int:
        """Return duration in ms of current track"""
        mlp = self.player.get_media_player()
        if mlp:
            d = mlp.get_length()
            return d if d > 0 else 0
        return 0

    def position(self) -> int:
        """Return current position in ms of current track"""
        mlp = self.player.get_media_player()
        if mlp:
            p = mlp.get_time()
            return p if p > 0 else 0
        return 0

    def set_position(self, ms: int):
        """Seek to specific position (ms)"""
        mlp = self.player.get_media_player()
        if mlp:
            mlp.set_time(ms)

