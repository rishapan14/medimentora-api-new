"""Provider-neutral embedding clients for grounded document retrieval."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

from flask import current_app


class EmbeddingProvider(Protocol):
  name: str
  model: str
  dimension: int

  def embed_texts(self, texts: list[str]) -> list[list[float]]: ...


class LocalHashEmbeddingProvider:
  """Deterministic offline lexical embeddings used by default and in tests."""

  name = "local_hash"

  def __init__(self, model: str, dimension: int):
    self.model = model
    self.dimension = max(64, min(4096, int(dimension)))

  def embed_texts(self, texts: list[str]) -> list[list[float]]:
    return [self._embed(text) for text in texts]

  def _embed(self, text: str) -> list[float]:
    tokens = re.findall(r"[a-z0-9]+", (text or "").casefold())
    features = tokens + [f"{left}_{right}" for left, right in zip(tokens, tokens[1:])]
    vector = [0.0] * self.dimension
    for feature in features:
      digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
      index = int.from_bytes(digest[:4], "big") % self.dimension
      sign = 1.0 if digest[4] & 1 else -1.0
      vector[index] += sign
    norm = math.sqrt(math.fsum(value * value for value in vector))
    return [value / norm for value in vector] if norm else vector


class OpenAIEmbeddingProvider:
  name = "openai"

  def __init__(self, model: str, dimension: int | None = None):
    api_key = str(current_app.config.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
      raise RuntimeError("OPENAI_API_KEY is required for OpenAI embeddings.")
    from openai import OpenAI

    self.model = model
    self.dimension = int(dimension or 0)
    self._client = OpenAI(api_key=api_key)

  def embed_texts(self, texts: list[str]) -> list[list[float]]:
    if not texts:
      return []
    response = self._client.embeddings.create(model=self.model, input=texts)
    vectors = [list(item.embedding) for item in sorted(response.data, key=lambda item: item.index)]
    if vectors:
      self.dimension = len(vectors[0])
    return vectors


def get_embedding_provider(
  provider_name: str | None = None,
  model: str | None = None,
  dimension: int | None = None,
) -> EmbeddingProvider:
  name = str(provider_name or current_app.config.get("TEACHER_EMBEDDING_PROVIDER", "local_hash")).strip().lower()
  if name == "local_hash":
    return LocalHashEmbeddingProvider(
      model or str(current_app.config.get("TEACHER_EMBEDDING_MODEL", "medimentora-hash-v1")),
      dimension or int(current_app.config.get("TEACHER_EMBEDDING_DIMENSION", 256)),
    )
  if name == "openai":
    return OpenAIEmbeddingProvider(
      model or str(current_app.config.get("TEACHER_OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")),
      dimension,
    )
  raise ValueError(f"Unsupported embedding provider: {name}.")
