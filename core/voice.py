"""Voice input / output for FRIDAY.

Designed so that voice failures NEVER crash the assistant — if a mic or
TTS engine is missing, FRIDAY simply falls back to text mode and logs
the reason.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

log = logging.getLogger("friday.voice")


@dataclass
class VoiceConfig:
    rate: int = 185
    engine: str = "pyttsx3"      # 'pyttsx3' | 'gtts' | 'none'
    tts_lang_hint: str = "en-IN"
    wake_word: str = "friday"


class Voice:
    def __init__(self, cfg: VoiceConfig):
        self.cfg = cfg
        self._tts = None
        self._tts_lock = threading.Lock()
        self._recognizer = None
        self._init_tts()
        self._init_stt()

    # ---- TTS -----------------------------------------------------------

    def _init_tts(self) -> None:
        if self.cfg.engine == "none":
            return
        if self.cfg.engine == "pyttsx3":
            try:
                import pyttsx3
                eng = pyttsx3.init()
                eng.setProperty("rate", self.cfg.rate)
                # Prefer an Indian English voice if installed
                for v in eng.getProperty("voices"):
                    name = (v.name or "").lower()
                    if "india" in name or "hindi" in name or "ravi" in name:
                        eng.setProperty("voice", v.id)
                        break
                self._tts = eng
            except Exception as e:
                log.warning("pyttsx3 init failed: %s", e)
                self._tts = None

    def speak(self, text: str) -> None:
        if not text:
            return
        if self._tts is None and self.cfg.engine != "gtts":
            print(f"[Friday] {text}")
            return
        if self.cfg.engine == "gtts":
            self._speak_gtts(text)
            return
        with self._tts_lock:
            try:
                self._tts.say(text)
                self._tts.runAndWait()
            except Exception as e:
                log.warning("TTS failed: %s", e)
                print(f"[Friday] {text}")

    def _speak_gtts(self, text: str) -> None:
        try:
            import tempfile
            from gtts import gTTS
            from playsound import playsound
            tts = gTTS(text=text, lang=self.cfg.tts_lang_hint.split("-")[0])
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                tts.save(f.name)
                playsound(f.name)
        except Exception as e:
            log.warning("gTTS failed: %s", e)
            print(f"[Friday] {text}")

    # ---- STT -----------------------------------------------------------

    def _init_stt(self) -> None:
        try:
            import speech_recognition as sr
            self._recognizer = sr.Recognizer()
            self._sr = sr
        except Exception as e:
            log.warning("speech_recognition unavailable: %s", e)
            self._recognizer = None

    def listen(self, timeout: float = 6.0,
               phrase_time_limit: float = 12.0) -> str | None:
        """Capture one phrase from the mic and transcribe it.
        Returns None if mic / network unavailable."""
        if self._recognizer is None:
            return None
        try:
            with self._sr.Microphone() as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=0.4)
                audio = self._recognizer.listen(
                    source,
                    timeout=timeout,
                    phrase_time_limit=phrase_time_limit,
                )
        except Exception as e:
            log.warning("listen failed: %s", e)
            return None

        # Try Hindi first, then English — Google's free endpoint handles both.
        for lang in ("hi-IN", "en-IN"):
            try:
                return self._recognizer.recognize_google(audio, language=lang)
            except Exception:
                continue
        return None

    def wait_for_wake_word(self) -> bool:
        """Block until the wake word is heard. Returns False if STT is dead."""
        if self._recognizer is None:
            return False
        wake = self.cfg.wake_word.lower()
        while True:
            heard = self.listen(timeout=None, phrase_time_limit=4.0)
            if heard and wake in heard.lower():
                return True
