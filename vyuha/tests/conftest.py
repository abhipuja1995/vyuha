"""
conftest.py: module-level stubs for heavy optional dependencies.

The runner tests mock UserSimulator entirely; these stubs prevent import errors
on packages that are not installed in the lightweight test venv
(pydub, scipy, soundfile, celery, etc.). Stubs are applied before test collection.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock


def _make_pkg(name: str) -> MagicMock:
    """Create a plain MagicMock that acts as a package. No spec so any attribute works."""
    m = MagicMock()
    m.__name__ = name
    m.__package__ = name
    m.__path__ = []
    m.__loader__ = None
    m.__spec__ = None
    return m


# Top-level heavy packages — must be stubbed before any sub-module import
_TOP_LEVEL = [
    "pydub", "scipy", "soundfile", "redis", "celery",
    "httpx", "sqlalchemy", "asyncpg", "alembic", "ulid",
    "tenacity", "streamlit", "plotly", "fastapi",
    "uvicorn", "multipart",
    # asr subpackage heavy deps (llm_client, normalizer)
    "joblib", "tqdm", "jsonlines",
    "indicnlp", "transformers",
    "google", "google.auth", "google.oauth2", "google.oauth2.service_account",
    "google.auth.transport", "google.auth.transport.requests",
    "vertexai", "vertexai.generative_models",
]

for _mod in _TOP_LEVEL:
    if _mod not in sys.modules:
        sys.modules[_mod] = _make_pkg(_mod)

# Sub-modules that are explicitly imported (e.g. `from pydub.effects import normalize`)
_SUB_MODULES = [
    "pydub.effects",
    "pydub.generators",
    "scipy.signal",
    "sqlalchemy.ext",
    "sqlalchemy.ext.asyncio",
    "sqlalchemy.orm",
    "sqlalchemy.dialects",
    "celery.utils",
    "celery.utils.log",
    "fastapi.middleware",
    "fastapi.responses",
    "fastapi.staticfiles",
    "indicnlp.normalize",
    "indicnlp.normalize.indic_normalize",
    "google.auth.transport.requests",
]

for _sub in _SUB_MODULES:
    if _sub not in sys.modules:
        pkg = _sub.split(".")[0]
        m = _make_pkg(_sub)
        # Attach as attribute of parent
        parent_name = ".".join(_sub.split(".")[:-1])
        if parent_name in sys.modules:
            setattr(sys.modules[parent_name], _sub.split(".")[-1], m)
        sys.modules[_sub] = m


def pytest_configure(config):
    """Suppress PytestCollectionWarning for pydantic classes named TestCase/TestCategory."""
    config.addinivalue_line(
        "filterwarnings",
        "ignore::pytest.PytestCollectionWarning",
    )
