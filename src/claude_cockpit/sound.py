"""有消息时的提示音。所有异常都吞掉,绝不让 UI 崩。

play() 播随包自带的 assets/guagua.mp3(从 desk-buddy 搬来,本项目自带、不依赖小青蛙);
QMediaPlayer/音频输出不可用或播放失败时,回退 Windows 默认「叮」声。
"""
from __future__ import annotations

from pathlib import Path

# 内置提示音,随包发布
_SOUND = Path(__file__).parent / "assets" / "guagua.mp3"

# QMediaPlayer 与其音频输出需在播放期间保持引用,否则会被 GC、声音被截断。
_player = None
_audio_output = None


def _beep() -> None:
    import winsound
    winsound.MessageBeep()


def _play_file(path: str) -> None:
    global _player, _audio_output
    from PySide6.QtCore import QUrl
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

    if _player is None:
        _player = QMediaPlayer()
        _audio_output = QAudioOutput()
        _player.setAudioOutput(_audio_output)
    _player.setSource(QUrl.fromLocalFile(path))
    _player.play()


def play() -> None:
    """播一声提示音;任何失败都回退系统叮声,再失败就静默。"""
    try:
        if _SOUND.is_file():
            _play_file(str(_SOUND))
        else:
            _beep()
    except Exception:
        try:
            _beep()
        except Exception:
            pass
