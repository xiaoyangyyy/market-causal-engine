"""LLM API configuration for causal claim extraction."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_BASE_URL = "https://ai.azya.top/v1"
DEFAULT_MODEL = "qwen3.5"


@dataclass(frozen=True)
class LLMConfig:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    timeout: int = 120

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_llm_config(
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    timeout: int = 120,
    dotenv_path: str | Path | None = None,
) -> LLMConfig:
    root = Path(__file__).resolve().parent.parent.parent
    _load_dotenv(Path(dotenv_path) if dotenv_path else root / ".env")

    key = (
        api_key
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("ZHISUAN_API_KEY")
        or ""
    )
    base = (base_url or os.environ.get("OPENAI_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    mdl = model or os.environ.get("OPENAI_MODEL") or DEFAULT_MODEL
    return LLMConfig(api_key=key, base_url=base, model=mdl, timeout=timeout)
