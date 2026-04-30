from typing import Any, Dict, List

from configs.settings import VOICE_ENABLED, VOICE_NAME, VOICE_RATE, VOICE_VOLUME

try:
    import pyttsx3
except ImportError:
    pyttsx3 = None


class VoiceEngine:
    def __init__(
        self,
        enabled: bool = VOICE_ENABLED,
        rate: int = VOICE_RATE,
        volume: float = VOICE_VOLUME,
        voice_name: str = VOICE_NAME,
    ):
        self.enabled = enabled
        self.rate = rate
        self.volume = volume
        self.voice_name = voice_name

    def speak(self, text: str) -> Dict[str, Any]:
        text = text.strip()
        if not text:
            return {"status": "skipped", "message": "No speech text was provided."}

        if not self.enabled:
            return {"status": "disabled", "message": "Voice output is disabled."}

        if pyttsx3 is None:
            return {
                "status": "unavailable",
                "message": "Install pyttsx3 to enable local text-to-speech.",
            }

        try:
            engine = pyttsx3.init()
            engine.setProperty("rate", self.rate)
            engine.setProperty("volume", self.volume)
            selected_voice = self._select_voice(engine)
            if selected_voice:
                engine.setProperty("voice", selected_voice)

            engine.say(text)
            engine.runAndWait()
            engine.stop()
        except Exception as error:
            return {"status": "fail", "message": f"Voice playback failed: {error}"}

        return {
            "status": "success",
            "message": "Speech completed.",
            "voice": self.voice_name or "default",
        }

    def available_voices(self) -> Dict[str, Any]:
        if pyttsx3 is None:
            return {
                "status": "unavailable",
                "voices": [],
                "message": "Install pyttsx3 to list local voices.",
            }

        try:
            engine = pyttsx3.init()
            voices = [
                {
                    "id": voice.id,
                    "name": getattr(voice, "name", ""),
                    "languages": [str(language) for language in getattr(voice, "languages", [])],
                }
                for voice in engine.getProperty("voices")
            ]
            engine.stop()
        except Exception as error:
            return {"status": "fail", "voices": [], "message": str(error)}

        return {"status": "success", "voices": voices}

    def _select_voice(self, engine: Any) -> str:
        if not self.voice_name:
            return ""

        search = self.voice_name.lower()
        voices: List[Any] = engine.getProperty("voices")
        for voice in voices:
            name = str(getattr(voice, "name", "")).lower()
            voice_id = str(getattr(voice, "id", "")).lower()
            if search in name or search in voice_id:
                return voice.id

        return ""
