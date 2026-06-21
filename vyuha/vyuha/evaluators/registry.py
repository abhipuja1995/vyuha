"""Evaluator registry — maps string names to classes, enables /evaluators API."""
from __future__ import annotations

from typing import Any, Type
from vyuha.evaluators.base import BaseEvaluator

_REGISTRY: dict[str, Type[BaseEvaluator]] = {}


def register(cls: Type[BaseEvaluator]) -> Type[BaseEvaluator]:
    _REGISTRY[cls.name] = cls
    return cls


def get(name: str) -> Type[BaseEvaluator] | None:
    return _REGISTRY.get(name)


def list_all() -> list[dict[str, Any]]:
    return [
        {
            "name": cls.name,
            "description": cls.description,
            "required_keys": cls.required_keys,
        }
        for cls in _REGISTRY.values()
    ]


def _auto_register() -> None:
    """Register all evaluators on import."""
    from vyuha.evaluators import heuristic, similarity, audio, agent, retrieval, safety, llm_judge, classification, code
    modules = [heuristic, similarity, audio, agent, retrieval, safety, llm_judge, classification, code]
    for mod in modules:
        for attr in dir(mod):
            obj = getattr(mod, attr)
            try:
                if (
                    isinstance(obj, type)
                    and issubclass(obj, BaseEvaluator)
                    and obj is not BaseEvaluator
                    and hasattr(obj, "name")
                    and obj.name != "base"
                ):
                    _REGISTRY[obj.name] = obj
            except Exception:
                pass


class EvalRegistry:
    @staticmethod
    def get(name: str) -> Type[BaseEvaluator] | None:
        if not _REGISTRY:
            _auto_register()
        return _REGISTRY.get(name)

    @staticmethod
    def list_all() -> list[dict[str, Any]]:
        if not _REGISTRY:
            _auto_register()
        return list_all()

    @staticmethod
    def run(name: str, **kwargs: Any):
        if not _REGISTRY:
            _auto_register()
        cls = _REGISTRY.get(name)
        if cls is None:
            raise ValueError(f"Unknown evaluator: '{name}'. Available: {list(_REGISTRY.keys())}")
        return cls().run(**kwargs)
