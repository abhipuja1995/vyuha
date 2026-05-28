from __future__ import annotations

import uuid
from enum import Enum
from typing import Any
from datetime import datetime

from pydantic import BaseModel, Field


class TestCategory(str, Enum):
    HAPPY_PATH = "HAPPY_PATH"
    EDGE_CASE = "EDGE_CASE"
    FAILURE_MODE = "FAILURE_MODE"
    CRITICAL = "CRITICAL"
    REGRESSION = "REGRESSION"


class Language(str, Enum):
    TELUGU = "te"
    TAMIL = "ta"
    HINDI = "hi"
    ODIA = "or"
    KANNADA = "kn"
    MALAYALAM = "ml"
    MARATHI = "mr"
    BENGALI = "bn"
    ENGLISH_INDIAN = "en-IN"
    ENGLISH = "en"


class Emotion(str, Enum):
    NEUTRAL = "neutral"
    FRUSTRATED = "frustrated"
    ANXIOUS = "anxious"
    URGENT = "urgent"
    CALM = "calm"
    DISTRESSED = "distressed"


class NoiseProfile(str, Enum):
    QUIET_INDOOR = "quiet_indoor"           # SNR > 25dB
    MODERATE_INDOOR = "moderate_indoor"     # SNR 12-20dB
    BUSY_OUTDOOR = "busy_outdoor"           # SNR 5-12dB
    CALL_CENTRE = "call_centre"             # SNR 8-15dB
    MOBILE_DEGRADED = "mobile_degraded"     # packet loss 3-8%, codec artefacts
    SPEAKERPHONE = "speakerphone"           # echo + reverb


class CodeSwitchConfig(BaseModel):
    primary_language: Language
    secondary_language: Language
    switch_probability: float = Field(ge=0.0, le=1.0, default=0.3)
    # e.g. "te-en" for Telugu-English code switching


class PersonaConfig(BaseModel):
    language: Language = Language.ENGLISH_INDIAN
    accent_variant: str = ""               # e.g. "Bihari", "Chennai", "Andhra Pradesh"
    noise_profile: NoiseProfile = NoiseProfile.QUIET_INDOOR
    emotion: Emotion = Emotion.NEUTRAL
    speaking_rate: float = Field(ge=0.5, le=2.0, default=1.0)  # relative to normal
    interruption_tendency: float = Field(ge=0.0, le=1.0, default=0.1)
    code_switch: CodeSwitchConfig | None = None
    backstory: str = ""
    tts_voice_id: str = ""                 # provider-specific voice ID
    derived_from_call_id: str | None = None  # production call this was cloned from


class ConversationNode(BaseModel):
    node_id: str
    utterance_template: str               # may contain {placeholders}
    is_terminal: bool = False
    expected_agent_intent: str = ""       # what we expect the agent to do here
    audio_file: str | None = None         # relative key for uploaded audio; bypasses TTS when set


class ConversationEdge(BaseModel):
    from_node: str
    to_node: str
    condition: str                         # e.g. "agent_asks_for_dob"
    user_action: str = ""                  # what user does when condition met


class ConversationGraph(BaseModel):
    start_node: str
    nodes: list[ConversationNode]
    edges: list[ConversationEdge]

    def get_node(self, node_id: str) -> ConversationNode | None:
        return next((n for n in self.nodes if n.node_id == node_id), None)


class ToolCallSpec(BaseModel):
    tool_name: str
    expected_args: dict[str, Any] = Field(default_factory=dict)
    mock_response: dict[str, Any] = Field(default_factory=dict)
    is_required: bool = True


class TestCase(BaseModel):
    test_id: str = Field(default_factory=lambda: f"TC-{uuid.uuid4().hex[:8].upper()}")
    title: str
    category: TestCategory
    user_goal: str
    persona_config: PersonaConfig
    conversation_graph: ConversationGraph
    tool_call_sequence: list[ToolCallSpec] = Field(default_factory=list)
    ground_truth_end_state: dict[str, Any] = Field(default_factory=dict)
    pass_criteria: str
    created_by: str = "AUTO_GENERATED"
    tags: list[str] = Field(default_factory=list)
    linked_production_call: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    version: int = 1

    @property
    def is_critical(self) -> bool:
        return self.category == TestCategory.CRITICAL
