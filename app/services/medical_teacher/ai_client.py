"""Thin AI client for Medical Teacher modules (Gemini preferred, OpenAI fallback).

Used for enrichment only. Heuristic parsers must work without any API key.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from flask import current_app

logger = logging.getLogger(__name__)


class TeacherAIClient:
  """Generate structured JSON for book analysis with provider fallback."""

  @classmethod
  def complete_json(cls, system_prompt: str, user_prompt: str) -> tuple[dict[str, Any] | None, str]:
    """
    Returns (parsed_json_or_None, provider_name).
    provider_name: gemini | openai | none
    """
    gemini_key = (current_app.config.get("GEMINI_API_KEY") or "").strip()
    if gemini_key:
      data = cls._gemini_json(system_prompt, user_prompt, gemini_key)
      if data is not None:
        return data, "gemini"

    openai_key = (current_app.config.get("OPENAI_API_KEY") or "").strip()
    if openai_key:
      data = cls._openai_json(system_prompt, user_prompt, openai_key)
      if data is not None:
        return data, "openai"

    return None, "none"

  @classmethod
  def _gemini_json(cls, system_prompt: str, user_prompt: str, api_key: str) -> dict[str, Any] | None:
    try:
      import google.generativeai as genai
    except ImportError:
      logger.warning("google-generativeai not installed; skipping Gemini")
      return None

    try:
      genai.configure(api_key=api_key)
      model_name = current_app.config.get("GEMINI_MODEL", "gemini-2.0-flash")
      model = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=system_prompt,
      )
      response = model.generate_content(
        user_prompt,
        generation_config={
          "temperature": 0.2,
          "response_mime_type": "application/json",
        },
      )
      text = getattr(response, "text", None) or ""
      return cls._parse_json_loose(text)
    except Exception:
      logger.exception("Gemini JSON completion failed")
      return None

  @classmethod
  def _openai_json(cls, system_prompt: str, user_prompt: str, api_key: str) -> dict[str, Any] | None:
    try:
      from openai import OpenAI
    except ImportError:
      return None

    try:
      client = OpenAI(api_key=api_key)
      response = client.chat.completions.create(
        model=current_app.config.get("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[
          {"role": "system", "content": system_prompt},
          {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
      )
      content = response.choices[0].message.content or ""
      return cls._parse_json_loose(content)
    except Exception:
      logger.exception("OpenAI JSON completion failed")
      return None

  @staticmethod
  def _parse_json_loose(text: str) -> dict[str, Any] | None:
    if not text:
      return None
    text = text.strip()
    try:
      data = json.loads(text)
      return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
      match = re.search(r"\{[\s\S]*\}", text)
      if not match:
        return None
      try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else None
      except json.JSONDecodeError:
        return None
