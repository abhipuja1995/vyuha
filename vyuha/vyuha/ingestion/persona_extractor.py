from __future__ import annotations

import json
from typing import Any

import structlog

from vyuha.config import settings
from vyuha.ingestion.models import FailedCallRecord, ExtractedPersona
from vyuha.models.test_case import Language, Emotion, NoiseProfile

log = structlog.get_logger()

_SNR_TO_NOISE_PROFILE = [
    (25.0, NoiseProfile.QUIET_INDOOR),
    (12.0, NoiseProfile.MODERATE_INDOOR),
    (8.0, NoiseProfile.CALL_CENTRE),
    (5.0, NoiseProfile.BUSY_OUTDOOR),
    (0.0, NoiseProfile.MOBILE_DEGRADED),
]

_PERSONA_EXTRACT_PROMPT = """
Analyze this call transcript and extract persona characteristics.

Transcript:
{transcript}

Metadata:
- Detected language: {language}
- Call duration: {duration_seconds}s
- Final sentiment score: {final_sentiment}

Extract and return JSON:
{{
  "accent_variant": "city/region name, e.g. Bihari, Chennai, Andhra Pradesh — or empty if unclear",
  "speaking_rate": <float, 0.5-2.0 relative to normal pace>,
  "emotion": "neutral|frustrated|anxious|urgent|calm|distressed",
  "code_switch_detected": <bool>,
  "secondary_language": "BCP-47 code if code-switching detected, else null",
  "noise_profile": "quiet_indoor|moderate_indoor|busy_outdoor|call_centre|mobile_degraded|speakerphone",
  "estimated_snr_db": <float or null>
}}
"""


class PersonaExtractor:
    """
    Extracts persona configuration from a failed production call.
    Combines transcript analysis (LLM) with audio feature detection.
    """

    async def extract(self, record: FailedCallRecord) -> ExtractedPersona:
        llm_persona = await self._extract_from_transcript(record)

        # If audio is available, refine with acoustic features
        if record.audio_path:
            try:
                acoustic = self._analyze_audio(record.audio_path)
                llm_persona = self._merge_acoustic(llm_persona, acoustic)
            except Exception as exc:
                log.warning("audio_analysis_failed", call_id=record.call_id, error=str(exc))

        return llm_persona

    async def _extract_from_transcript(self, record: FailedCallRecord) -> ExtractedPersona:
        transcript_text = "\n".join(
            f"{t['role'].upper()}: {t['text']}" for t in record.transcript
        )
        duration = (record.ended_at - record.started_at).total_seconds()
        final_sentiment = record.sentiment_scores[-1] if record.sentiment_scores else 0.5

        prompt = _PERSONA_EXTRACT_PROMPT.format(
            transcript=transcript_text[:4000],
            language=record.language_detected,
            duration_seconds=int(duration),
            final_sentiment=final_sentiment,
        )
        system = "You are an expert in Indian language identification and call center analytics. Respond with valid JSON only."

        data: dict[str, Any] = {}
        # Try Anthropic → local Ollama → rule-based fallback
        if settings.anthropic_api_key:
            try:
                import anthropic
                from vyuha.utils.llm import parse_llm_json
                client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
                resp = await client.messages.create(
                    model=settings.default_judge_model,
                    max_tokens=512,
                    system=system,
                    messages=[{"role": "user", "content": prompt}],
                )
                data = parse_llm_json(resp.content[0].text)
            except Exception as exc:
                log.warning("persona_anthropic_failed", call_id=record.call_id, error=str(exc))

        if not data and settings.local_llm_url:
            try:
                from openai import AsyncOpenAI
                from vyuha.utils.llm import parse_llm_json
                client_oai = AsyncOpenAI(api_key="ollama", base_url=settings.local_llm_url)
                resp_oai = await client_oai.chat.completions.create(
                    model=settings.local_llm_model,
                    max_tokens=512,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                )
                data = parse_llm_json(resp_oai.choices[0].message.content or "{}")
                log.info("persona_extracted_via_local_llm", call_id=record.call_id)
            except Exception as exc:
                log.warning("persona_local_llm_failed", call_id=record.call_id, error=str(exc))

        if not data:
            log.info("persona_rule_based_fallback", call_id=record.call_id)
            data = self._rule_based_persona(record)

        emotion = data.get("emotion", "neutral")
        if final_sentiment < 0.25:
            emotion = "distressed"
        elif final_sentiment < 0.4:
            emotion = "frustrated"

        return ExtractedPersona(
            language=record.language_detected,
            accent_variant=data.get("accent_variant", ""),
            speaking_rate=float(data.get("speaking_rate", 1.0)),
            noise_profile=data.get("noise_profile", "quiet_indoor"),
            emotion=emotion,
            estimated_snr_db=data.get("estimated_snr_db"),
            code_switch_detected=bool(data.get("code_switch_detected", False)),
            secondary_language=data.get("secondary_language"),
        )

    def _rule_based_persona(self, record: FailedCallRecord) -> dict[str, Any]:
        """
        Deterministic persona extraction — used when no LLM is available.
        Derives emotion from sentiment scores, noise from call metadata.
        """
        final_sentiment = record.sentiment_scores[-1] if record.sentiment_scores else 0.5
        emotion = "neutral"
        if final_sentiment < 0.25:
            emotion = "distressed"
        elif final_sentiment < 0.4:
            emotion = "frustrated"
        elif final_sentiment < 0.55:
            emotion = "anxious"

        # Detect code-switching heuristically: look for mixed scripts in transcript
        has_latin = has_indic = False
        for turn in record.transcript:
            text = turn.get("text", "")
            if any(ord(c) < 128 and c.isalpha() for c in text):
                has_latin = True
            if any(0x0900 <= ord(c) <= 0x0DFF for c in text):
                has_indic = True

        return {
            "accent_variant": "",
            "speaking_rate": 1.0,
            "emotion": emotion,
            "code_switch_detected": has_latin and has_indic,
            "secondary_language": "en-IN" if (has_latin and has_indic) else None,
            "noise_profile": "quiet_indoor",
            "estimated_snr_db": None,
        }

    def _analyze_audio(self, audio_path: str) -> dict[str, Any]:
        """
        Extract acoustic features: estimated SNR, speaking rate from audio.
        Returns partial persona fields to merge with LLM extraction.
        """
        import numpy as np
        import soundfile as sf

        audio, sr = sf.read(audio_path)

        # Estimate SNR via active speech ratio
        frame_size = int(sr * 0.02)  # 20ms frames
        frames = [audio[i:i+frame_size] for i in range(0, len(audio), frame_size)]
        rms_values = [np.sqrt(np.mean(f**2)) for f in frames if len(f) == frame_size]
        if not rms_values:
            return {}

        rms_arr = np.array(rms_values)
        noise_floor = np.percentile(rms_arr, 10)
        signal_level = np.percentile(rms_arr, 90)
        snr_db = 20 * np.log10(signal_level / (noise_floor + 1e-10)) if noise_floor > 0 else 30.0

        return {"estimated_snr_db": float(snr_db)}

    def _merge_acoustic(self, persona: ExtractedPersona, acoustic: dict[str, Any]) -> ExtractedPersona:
        """Override transcript-derived estimates with measured acoustic values."""
        if "estimated_snr_db" in acoustic:
            snr = acoustic["estimated_snr_db"]
            persona.estimated_snr_db = snr
            # Override noise profile based on measured SNR
            for threshold, profile in _SNR_TO_NOISE_PROFILE:
                if snr >= threshold:
                    persona.noise_profile = profile.value
                    break
        return persona
