from __future__ import annotations

import io
import random
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from pydub import AudioSegment
from pydub.effects import normalize

from vyuha.models.test_case import NoiseProfile

# Noise assets live under assets/noise/ relative to project root
_ASSETS_DIR = Path(__file__).parent.parent.parent / "assets" / "noise"


@dataclass
class NoiseParams:
    snr_db_range: tuple[float, float]          # (min, max) SNR in dB
    reverb_amount: float = 0.0                 # 0-1
    echo_amount: float = 0.0                   # 0-1
    packet_loss_rate: float = 0.0              # 0-1 probability of packet loss per frame
    codec_artifacts: bool = False
    noise_file_glob: str = ""                  # glob pattern for noise audio files


_PROFILE_PARAMS: dict[NoiseProfile, NoiseParams] = {
    NoiseProfile.QUIET_INDOOR: NoiseParams(
        snr_db_range=(25.0, 40.0),
        noise_file_glob="quiet_indoor*.wav",
    ),
    NoiseProfile.MODERATE_INDOOR: NoiseParams(
        snr_db_range=(12.0, 20.0),
        noise_file_glob="cafe*.wav",
    ),
    NoiseProfile.BUSY_OUTDOOR: NoiseParams(
        snr_db_range=(5.0, 12.0),
        noise_file_glob="street_market*.wav",
    ),
    NoiseProfile.CALL_CENTRE: NoiseParams(
        snr_db_range=(8.0, 15.0),
        noise_file_glob="call_centre*.wav",
    ),
    NoiseProfile.MOBILE_DEGRADED: NoiseParams(
        snr_db_range=(15.0, 25.0),
        packet_loss_rate=0.05,              # 3-8% loss, midpoint
        codec_artifacts=True,
        noise_file_glob="mobile*.wav",
    ),
    NoiseProfile.SPEAKERPHONE: NoiseParams(
        snr_db_range=(15.0, 25.0),
        reverb_amount=0.4,
        echo_amount=0.3,
        noise_file_glob="",
    ),
}


def _mix_at_snr(speech: AudioSegment, noise: AudioSegment, target_snr_db: float) -> AudioSegment:
    """Mix noise into speech at the specified SNR."""
    # Loop noise to match speech length
    if len(noise) < len(speech):
        loops = (len(speech) // len(noise)) + 1
        noise = noise * loops
    noise = noise[: len(speech)]

    speech_rms = speech.rms or 1
    noise_rms = noise.rms or 1
    desired_noise_rms = speech_rms / (10 ** (target_snr_db / 20))
    gain_db = 20 * np.log10(desired_noise_rms / noise_rms) if noise_rms > 0 else -60
    noise = noise.apply_gain(gain_db)
    return speech.overlay(noise)


def _apply_packet_loss(audio: AudioSegment, loss_rate: float, frame_ms: int = 20) -> AudioSegment:
    """Simulate packet loss by zeroing random frames."""
    frames = [audio[i : i + frame_ms] for i in range(0, len(audio), frame_ms)]
    for i, frame in enumerate(frames):
        if random.random() < loss_rate:
            frames[i] = AudioSegment.silent(duration=len(frame), frame_rate=frame.frame_rate)
    return sum(frames, AudioSegment.empty())


def _apply_reverb(audio: AudioSegment, amount: float) -> AudioSegment:
    """Simple reverb via delayed ghost copy."""
    delay_ms = int(50 * amount)
    ghost = audio - int(12 * (1 - amount))
    return audio.overlay(ghost, position=delay_ms)


def _simulate_codec_artifacts(audio: AudioSegment) -> AudioSegment:
    """Simulate G.711 codec compression artifacts (8kHz downsample + upsample)."""
    downsampled = audio.set_frame_rate(8000)
    return downsampled.set_frame_rate(audio.frame_rate)


class NoiseInjector:
    """
    Applies environmental noise profiles to synthesized audio.
    Deterministic when seed is provided.
    """

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self._np_rng = np.random.default_rng(seed)

    def apply(self, audio_bytes: bytes, profile: NoiseProfile, sample_rate: int = 16000) -> bytes:
        params = _PROFILE_PARAMS[profile]
        audio = AudioSegment.from_raw(
            io.BytesIO(audio_bytes),
            sample_width=2,
            frame_rate=sample_rate,
            channels=1,
        )

        # Mix background noise if noise files exist
        noise_files = sorted(_ASSETS_DIR.glob(params.noise_file_glob)) if params.noise_file_glob else []
        if noise_files:
            noise_file = self._rng.choice(noise_files)
            noise = AudioSegment.from_file(noise_file).set_frame_rate(sample_rate).set_channels(1)
            target_snr = self._rng.uniform(*params.snr_db_range)
            audio = _mix_at_snr(audio, noise, target_snr)

        # Reverb
        if params.reverb_amount > 0:
            audio = _apply_reverb(audio, params.reverb_amount)

        # Packet loss
        if params.packet_loss_rate > 0:
            actual_loss = self._rng.uniform(0.03, 0.08)
            audio = _apply_packet_loss(audio, actual_loss)

        # Codec artifacts
        if params.codec_artifacts:
            audio = _simulate_codec_artifacts(audio)

        return audio.raw_data
