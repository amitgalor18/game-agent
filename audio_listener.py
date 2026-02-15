"""
Audio Listener — The Ear.
Records microphone input (with simple VAD) and transcribes via faster-whisper.
Supports push-to-talk: record while button/key held, then transcribe.
"""

from __future__ import annotations

import os
import threading
from typing import Optional

import speech_recognition as sr

# Lazy-load faster_whisper to avoid import cost until first use
_whisper_model = None

# Default CPU to avoid "cublas64_12.dll not found" when CUDA is missing or mismatched.
# Set env WHISPER_DEVICE=cuda or auto to use GPU.
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "cpu")
# Smaller/faster model: set WHISPER_MODEL=distil-large-v3 (or base, small) for speed.
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "large-v3-turbo")
# Offline bundle: set WHISPER_DOWNLOAD_ROOT to vendor/whisper_models so models load from there.
WHISPER_DOWNLOAD_ROOT = os.environ.get("WHISPER_DOWNLOAD_ROOT", None)

# PTT recording state
_ptt_chunks: list[bytes] = []
_ptt_stop = threading.Event()
_ptt_thread: Optional[threading.Thread] = None
_ptt_stream = None
SAMPLE_RATE = 16000
CHUNK = 1024


def _ptt_record_loop() -> None:
    """Run in thread: record chunks until _ptt_stop is set."""
    global _ptt_stream
    try:
        import pyaudio
        pa = pyaudio.PyAudio()
        _ptt_stream = pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=CHUNK,
        )
        while not _ptt_stop.is_set():
            try:
                data = _ptt_stream.read(CHUNK, exception_on_overflow=False)
                _ptt_chunks.append(data)
            except Exception:
                break
    except Exception:
        pass
    finally:
        if _ptt_stream is not None:
            try:
                _ptt_stream.stop_stream()
                _ptt_stream.close()
            except Exception:
                pass
            _ptt_stream = None
        try:
            pa.terminate()
        except Exception:
            pass


def start_ptt_recording() -> None:
    """Start recording audio (call when user presses PTT)."""
    global _ptt_chunks, _ptt_stop, _ptt_thread
    _ptt_chunks = []
    _ptt_stop.clear()
    _ptt_thread = threading.Thread(target=_ptt_record_loop, daemon=True)
    _ptt_thread.start()


def stop_ptt_recording() -> bytes:
    """Stop recording and return raw 16-bit mono 16 kHz audio bytes. Call when user releases PTT."""
    global _ptt_stop, _ptt_thread
    _ptt_stop.set()
    if _ptt_thread is not None:
        _ptt_thread.join(timeout=2.0)
    return b"".join(_ptt_chunks)


def transcribe_audio_bytes(
    raw_bytes: bytes,
    *,
    whisper_model: str | None = None,
    whisper_device: str | None = None,
    language: str | None = "en",
    beam_size: int = 1,
    best_of: int = 1,
) -> str:
    """Transcribe raw 16-bit mono 16 kHz audio bytes. Returns transcribed text or empty string.
    Use beam_size=1 and best_of=1 for speed; set WHISPER_MODEL=distil-large-v3 for faster model.
    """
    if not raw_bytes:
        return ""
    import numpy as np
    audio_np = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    model = _get_whisper_model(whisper_model or WHISPER_MODEL, device=whisper_device)
    segments, info = model.transcribe(
        audio_np,
        language=language or None,
        beam_size=beam_size,
        best_of=best_of,
        vad_filter=True,
    )
    return " ".join(s.text.strip() for s in segments).strip() or ""


def _get_whisper_model(
    model_size: str | None = None,
    device: str | None = None,
    compute_type: str | None = None,
):
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        size = model_size or WHISPER_MODEL
        dev = device if device is not None else WHISPER_DEVICE
        # int8 is much faster on CPU with minimal quality loss; use default on GPU.
        ct = compute_type if compute_type is not None else ("int8" if dev == "cpu" else "default")
        kwargs = {"device": dev, "compute_type": ct}
        if WHISPER_DOWNLOAD_ROOT and os.path.isdir(WHISPER_DOWNLOAD_ROOT):
            kwargs["download_root"] = WHISPER_DOWNLOAD_ROOT
        _whisper_model = WhisperModel(size, **kwargs)
    return _whisper_model


def listen_and_transcribe(
    *,
    energy_threshold: int = 300,
    pause_threshold: float = 0.8,
    phrase_threshold: float = 0.3,
    whisper_model: str = "large-v3-turbo",
    whisper_device: str | None = None,
    language: str | None = "en",
    sample_rate: int = 16000,
) -> str:
    """
    Record audio from the default microphone (wait for speech, then for silence),
    then transcribe with faster-whisper. Returns the transcribed text or empty string on failure.
    """
    recognizer = sr.Recognizer()
    with sr.Microphone(sample_rate=sample_rate) as source:
        recognizer.energy_threshold = energy_threshold
        recognizer.dynamic_energy_threshold = True
        recognizer.pause_threshold = pause_threshold
        recognizer.phrase_threshold = phrase_threshold
        try:
            audio_data = recognizer.listen(source, timeout=15, phrase_time_limit=10)
        except sr.WaitTimeoutError:
            return ""
        except OSError as e:
            return f"[Audio error: {e}]"

    raw = audio_data.get_raw_data()
    # faster-whisper expects float32 mono at 16 kHz (fixed internally). It does not accept sample_rate.
    import numpy as np
    audio_np = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    # Requesting sample_rate=16000 above; if your mic returns something else, resample or use a 16 kHz device.

    model = _get_whisper_model(whisper_model or WHISPER_MODEL, device=whisper_device)
    segments, info = model.transcribe(
        audio_np,
        language=language or None,
        beam_size=1,
        best_of=1,
        vad_filter=True,
    )
    text = " ".join(s.text.strip() for s in segments).strip()
    return text or ""
