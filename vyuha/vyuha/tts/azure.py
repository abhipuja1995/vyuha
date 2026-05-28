from __future__ import annotations

import io
import structlog

from vyuha.config import settings
from vyuha.models.test_case import Language, Emotion
from vyuha.tts.base import TTSProvider, TTSRequest, TTSResult

log = structlog.get_logger()

# Azure Neural voices for Indian languages — best available per language
_AZURE_VOICE_MAP: dict[Language, str] = {
    Language.HINDI: "hi-IN-SwaraNeural",
    Language.TAMIL: "ta-IN-PallaviNeural",
    Language.TELUGU: "te-IN-ShrutiNeural",
    Language.KANNADA: "kn-IN-SapnaNeural",
    Language.MALAYALAM: "ml-IN-SobhanaNeural",
    Language.MARATHI: "mr-IN-AarohiNeural",
    Language.BENGALI: "bn-IN-TanishaaNeural",
    Language.ENGLISH_INDIAN: "en-IN-NeerjaNeural",
    Language.ENGLISH: "en-US-JennyNeural",
    # Odia is not natively supported — fallback to Hindi
    Language.ODIA: "hi-IN-SwaraNeural",
}

_EMOTION_TO_STYLE: dict[Emotion, str] = {
    Emotion.NEUTRAL: "general",
    Emotion.FRUSTRATED: "angry",
    Emotion.ANXIOUS: "fearful",
    Emotion.URGENT: "excited",
    Emotion.CALM: "calm",
    Emotion.DISTRESSED: "sad",
}

_AZURE_LANGS: set[Language] = {
    Language.HINDI, Language.TAMIL, Language.TELUGU, Language.KANNADA,
    Language.MALAYALAM, Language.MARATHI, Language.BENGALI,
    Language.ENGLISH_INDIAN, Language.ENGLISH,
}


class AzureTTSProvider(TTSProvider):
    """
    Azure Neural TTS — enterprise fallback.
    Used when Sarvam is unavailable or for Odia (not natively supported by Sarvam).
    """

    def __init__(self, api_key: str | None = None, region: str | None = None) -> None:
        self._api_key = api_key or settings.azure_speech_key
        self._region = region or settings.azure_speech_region

    @property
    def name(self) -> str:
        return "azure"

    def supports_language(self, language: Language) -> bool:
        return language in _AZURE_LANGS

    async def synthesize(self, request: TTSRequest) -> TTSResult:
        try:
            import azure.cognitiveservices.speech as speechsdk
        except ImportError:
            raise RuntimeError("Install azure-cognitiveservices-speech for Azure TTS support")

        voice = request.voice_id or _AZURE_VOICE_MAP.get(request.language, "en-IN-NeerjaNeural")
        style = _EMOTION_TO_STYLE.get(request.emotion, "general")
        rate_pct = int((request.speaking_rate - 1.0) * 100)
        rate_str = f"+{rate_pct}%" if rate_pct >= 0 else f"{rate_pct}%"

        ssml = f"""<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis"
                         xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="en-US">
            <voice name="{voice}">
                <mstts:express-as style="{style}">
                    <prosody rate="{rate_str}">{request.text}</prosody>
                </mstts:express-as>
            </voice>
        </speak>"""

        config = speechsdk.SpeechConfig(subscription=self._api_key, region=self._region)
        config.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Riff16Khz16BitMonoPcm
        )

        stream = speechsdk.audio.AudioOutputStream.create_pull_audio_output_stream()
        audio_config = speechsdk.audio.AudioOutputConfig(stream=stream)
        synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=config, audio_config=audio_config
        )

        result = synthesizer.speak_ssml_async(ssml).get()
        if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
            raise RuntimeError(f"Azure TTS failed: {result.cancellation_details}")

        audio_bytes = result.audio_data
        sample_rate = 16000
        return TTSResult(
            audio_bytes=audio_bytes,
            sample_rate=sample_rate,
            duration_seconds=len(audio_bytes) / (sample_rate * 2),
            provider=self.name,
        )

    async def list_voices(self, language: Language) -> list[dict]:
        voice = _AZURE_VOICE_MAP.get(language)
        return [{"voice_id": voice, "name": voice}] if voice else []
