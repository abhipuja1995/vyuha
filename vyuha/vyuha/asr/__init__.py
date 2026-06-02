"""
vyuha.asr — ASR evaluation subpackage.

Integrates the Sarvam llm_wer and llm_intent_entity evaluation pipelines
directly into vyuha, providing:

  - WERScorer:          LLM-assisted Word/Character Error Rate with
                        semantic equivalence correction for Indic languages
  - IntentEntityScorer: LLM-as-Judge intent preservation and entity
                        accuracy scoring for ASR hypothesis/reference pairs

Both scorers share a common IndicNormalizer and ChatCompletionsAPI client.
"""
from vyuha.asr.wer_scorer import WERScorer
from vyuha.asr.intent_entity_scorer import IntentEntityScorer

__all__ = ["WERScorer", "IntentEntityScorer"]
