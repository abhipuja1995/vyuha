"""
vyuha.evaluators — Portable eval library ported from FutureAGI patterns.

Usage:
    from vyuha.evaluators import RougeScore, ContainsAny, ToolCallAccuracy, EvalRegistry

    result = RougeScore().run(output="hello world", expected="hello earth")
    # → EvalResult(value=0.667, reason="ROUGE-1 fmeasure: 0.667", passed=True)

    results = ContainsAny(keywords=["balance", "account"]).run_batch([
        {"output": "Your balance is 500"},
        {"output": "Goodbye"},
    ])
"""
from vyuha.evaluators.registry import EvalRegistry
from vyuha.evaluators.base import EvalResult, BaseEvaluator
from vyuha.evaluators.heuristic import (
    Contains, ContainsAny, ContainsAll, ContainsNone,
    Equals, StartsWith, EndsWith, Regex,
    LengthLessThan, LengthGreaterThan, LengthBetween, WordCountInRange,
    OneLine, IsJson, IsUrl, IsEmail, IsRefusal,
)
from vyuha.evaluators.similarity import (
    RougeScore, BleuScore, MeteorScore, F1Score,
    LevenshteinSimilarity, JaccardSimilarity, JaroWinklerSimilarity,
    FuzzyMatch, EmbeddingSimilarity,
)
from vyuha.evaluators.audio import (
    WordErrorRate, CharacterErrorRate, MatchErrorRate,
    WordInfoLost, WordInfoPreserved,
)
from vyuha.evaluators.agent import (
    ToolCallAccuracy, TrajectoryMatch, StepCount,
)
from vyuha.evaluators.retrieval import (
    RecallAtK, PrecisionAtK, NdcgAtK, MeanReciprocalRank, HitRate,
)
from vyuha.evaluators.safety import RegexPiiDetection, LatencyCheck

__all__ = [
    "EvalRegistry", "EvalResult", "BaseEvaluator",
    # Heuristic
    "Contains", "ContainsAny", "ContainsAll", "ContainsNone",
    "Equals", "StartsWith", "EndsWith", "Regex",
    "LengthLessThan", "LengthGreaterThan", "LengthBetween", "WordCountInRange",
    "OneLine", "IsJson", "IsUrl", "IsEmail", "IsRefusal",
    # Similarity
    "RougeScore", "BleuScore", "MeteorScore", "F1Score",
    "LevenshteinSimilarity", "JaccardSimilarity", "JaroWinklerSimilarity",
    "FuzzyMatch", "EmbeddingSimilarity",
    # Audio/ASR
    "WordErrorRate", "CharacterErrorRate", "MatchErrorRate",
    "WordInfoLost", "WordInfoPreserved",
    # Agent
    "ToolCallAccuracy", "TrajectoryMatch", "StepCount",
    # Retrieval
    "RecallAtK", "PrecisionAtK", "NdcgAtK", "MeanReciprocalRank", "HitRate",
    # Safety
    "RegexPiiDetection", "LatencyCheck",
]
