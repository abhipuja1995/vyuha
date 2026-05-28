from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

import websockets
import structlog

from vyuha.config import settings
from vyuha.models.scoring import TurnResult
from vyuha.models.test_case import ConversationGraph, ConversationNode, PersonaConfig, Language
from vyuha.noise.profiles import NoiseInjector
from vyuha.tts.base import TTSRequest
from vyuha.tts.factory import tts_factory

log = structlog.get_logger()

_DEVIATION_PROMPT = """
You are simulating a caller with this persona: {persona_backstory}
Language: {language}. Emotion: {emotion}.

The conversation so far:
{transcript}

The current node in the conversation script says: "{utterance_template}"

Generate the caller's next utterance. Stay in character. You may deviate slightly from the
exact template to sound natural, but do NOT change the core intent or information being conveyed.
Respond with only the utterance text, no quotes or labels.
"""


class ConversationState:
    def __init__(self, graph: ConversationGraph) -> None:
        self.graph = graph
        self.current_node_id = graph.start_node
        self.turns: list[TurnResult] = []
        self.tool_calls_made: list[str] = []

    @property
    def current_node(self) -> ConversationNode | None:
        return self.graph.get_node(self.current_node_id)

    def advance(self, agent_response: str) -> bool:
        """Determine which edge to follow based on agent response. Returns False if terminal."""
        node = self.current_node
        if node is None or node.is_terminal:
            return False

        edges = [e for e in self.graph.edges if e.from_node == self.current_node_id]
        if not edges:
            return False

        for edge in edges:
            if edge.condition.lower() in agent_response.lower():
                self.current_node_id = edge.to_node
                return True

        # Default: follow first edge
        self.current_node_id = edges[0].to_node
        return True


class UserSimulator:
    """
    Bot-to-Bot User Simulator.
    Follows the conversation graph, synthesizes speech with the configured persona,
    injects noise, and sends audio (or text) to the VAUT via WebSocket.
    """

    def __init__(
        self,
        vaut_url: str | None = None,
        seed: int | None = None,
    ) -> None:
        self._vaut_url = vaut_url or settings.vaut_websocket_url
        self._noise_injector = NoiseInjector(seed=seed)
        self._seed = seed

    async def _synthesize_utterance(
        self,
        text: str,
        persona: PersonaConfig,
        audio_file: str | None = None,
    ) -> bytes | None:
        """
        Returns audio bytes or None (caller falls back to text mode).
        Priority: uploaded file → TTS providers → None.
        """
        from pathlib import Path as _Path

        # 1. Pre-uploaded audio takes precedence over TTS
        if audio_file:
            path = _Path(settings.audio_storage_path) / audio_file
            if path.exists():
                return self._noise_injector.apply(path.read_bytes(), persona.noise_profile)
            log.warning("audio_file_missing", audio_file=audio_file)

        # 2. TTS providers (Sarvam if key configured, Azure fallback)
        try:
            if persona.code_switch and self._should_code_switch(persona):
                audio_bytes = await self._synthesize_code_switched(text, persona)
            else:
                req = TTSRequest(
                    text=text,
                    language=persona.language,
                    emotion=persona.emotion,
                    speaking_rate=persona.speaking_rate,
                    voice_id=persona.tts_voice_id,
                    seed=self._seed,
                )
                result = await tts_factory.synthesize(req)
                audio_bytes = result.audio_bytes
            return self._noise_injector.apply(audio_bytes, persona.noise_profile)
        except Exception as exc:
            log.warning("tts_unavailable_falling_back_to_text", error=str(exc))
            return None

    def _should_code_switch(self, persona: PersonaConfig) -> bool:
        if not persona.code_switch:
            return False
        import random
        rng = random.Random(self._seed)
        return rng.random() < persona.code_switch.switch_probability

    async def _synthesize_code_switched(self, text: str, persona: PersonaConfig) -> bytes:
        """Interleave segments between primary and secondary language."""
        from vyuha.tts.sarvam import SarvamTTSProvider
        sarvam = SarvamTTSProvider()
        cs = persona.code_switch
        if cs is None:
            req = TTSRequest(text=text, language=persona.language)
            result = await tts_factory.synthesize(req)
            return result.audio_bytes

        # Simple split: first half primary, second half secondary
        words = text.split()
        mid = len(words) // 2
        segments = [
            (" ".join(words[:mid]), cs.primary_language),
            (" ".join(words[mid:]), cs.secondary_language),
        ]
        result = await sarvam.synthesize_code_switched(
            segments,
            emotion=persona.emotion,
            speaking_rate=persona.speaking_rate,
            voice_id=persona.tts_voice_id,
        )
        return result.audio_bytes

    async def run(
        self,
        graph: ConversationGraph,
        persona: PersonaConfig,
        test_id: str,
        mode: str = "text",  # "text" | "audio"
    ) -> list[TurnResult]:
        """
        Execute the conversation against the VAUT.
        Returns ordered list of TurnResult for scoring.
        """
        state = ConversationState(graph)
        run_id = str(uuid.uuid4())

        log.info("simulator_run_start", test_id=test_id, run_id=run_id, mode=mode)

        async with websockets.connect(self._vaut_url) as ws:
            turn_index = 0
            while state.current_node and not state.current_node.is_terminal:
                node = state.current_node
                utterance = node.utterance_template

                # Send audio or text to VAUT
                if mode == "audio":
                    audio_bytes = await self._synthesize_utterance(utterance, persona, node.audio_file)
                    if audio_bytes is not None:
                        await ws.send(audio_bytes)
                    else:
                        # No audio source available — send as text
                        await ws.send(json.dumps({"text": utterance, "turn": turn_index}))
                else:
                    payload = json.dumps({"text": utterance, "turn": turn_index})
                    await ws.send(payload)

                t_start = time.monotonic()
                try:
                    raw_response = await asyncio.wait_for(ws.recv(), timeout=10.0)
                except asyncio.TimeoutError:
                    log.warning("vaut_timeout", turn=turn_index, test_id=test_id)
                    break

                latency_ms = (time.monotonic() - t_start) * 1000

                if isinstance(raw_response, bytes):
                    agent_text = raw_response.decode("utf-8", errors="replace")
                else:
                    try:
                        parsed = json.loads(raw_response)
                        agent_text = parsed.get("text", raw_response)
                    except json.JSONDecodeError:
                        agent_text = raw_response

                turn = TurnResult(
                    turn_index=turn_index,
                    user_utterance=utterance,
                    agent_response=agent_text,
                    latency_ms=latency_ms,
                    tool_calls_made=[],
                    tool_calls_expected=[],
                )
                state.turns.append(turn)
                turn_index += 1

                if not state.advance(agent_text):
                    break

        log.info("simulator_run_complete", test_id=test_id, turns=len(state.turns))
        return state.turns
