"""Thin OpenAI client. Lazy-initialised so tests can run without the env var.
Every feature that calls OpenAI routes through here so we have a single choke
point for rate-limiting, logging, and feature-flag fallback."""
from __future__ import annotations

import os
from typing import Any

_client: Any = None

# Model pin — matches plan.md §"LLM integration". Override via env at Phase 5 prototype time.
DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")
VISION_MODEL = os.environ.get("OPENAI_VISION_MODEL", DEFAULT_MODEL)


def get_client():
    """Returns a live openai.OpenAI client. Raises if API key missing."""
    global _client
    if _client is not None:
        return _client
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set — cannot call OpenAI.")
    from openai import OpenAI  # defer import so pytest can run on a machine w/o network

    _client = OpenAI(api_key=api_key)
    return _client


def feature_flag(name: str, default: bool = False) -> bool:
    """Feature flags read from env: FEATURE_OCR, FEATURE_REVISION_LLM, etc.
    Truthy values: 1, true, yes, on (case-insensitive)."""
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")
