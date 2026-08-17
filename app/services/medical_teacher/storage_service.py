"""Storage boundary for uploaded learning documents.

The local backend remains compatible with existing deployments.  Keeping all
filesystem operations behind this interface allows a persistent/object-storage
backend to be added without changing document-processing services.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from flask import current_app
from werkzeug.utils import secure_filename

from app.models.book_model import Book
from app.services.medical_teacher.document_validator import ValidatedDocument


@dataclass(frozen=True)
class StoredDocument:
  backend: str
  storage_key: str
  stored_filename: str
  local_path: str


class DocumentStorageBackend(Protocol):
  name: str

  def save(self, document: ValidatedDocument) -> StoredDocument: ...

  def resolve_local_path(self, book: Book) -> str: ...

  def delete_stored(self, document: StoredDocument) -> None: ...

  def delete(self, book: Book) -> None: ...


class LocalDocumentStorage:
  name = "local"

  def __init__(self, root: str):
    self.root = Path(root).resolve()
    self.root.mkdir(parents=True, exist_ok=True)

  def save(self, document: ValidatedDocument) -> StoredDocument:
    safe_name = secure_filename(document.filename) or f"document.{document.extension}"
    stored_filename = f"{uuid.uuid4().hex}_{safe_name}"
    destination = (self.root / stored_filename).resolve()
    if self.root not in destination.parents:
      raise ValueError("Invalid document storage path.")
    document.storage.save(str(destination))
    return StoredDocument(
      backend=self.name,
      storage_key=stored_filename,
      stored_filename=stored_filename,
      local_path=str(destination),
    )

  def resolve_local_path(self, book: Book) -> str:
    key = (book.storage_key or book.stored_filename or "").strip()
    if key:
      candidate = (self.root / key).resolve()
      if self.root in candidate.parents and candidate.is_file():
        return str(candidate)
    # Backward compatibility for rows created before storage_key existed.
    legacy = Path(book.file_path or "")
    if legacy.is_file():
      return str(legacy.resolve())
    raise FileNotFoundError("Stored document is unavailable.")

  def delete(self, book: Book) -> None:
    try:
      path = self.resolve_local_path(book)
    except FileNotFoundError:
      return
    try:
      os.remove(path)
    except FileNotFoundError:
      return

  def delete_stored(self, document: StoredDocument) -> None:
    try:
      os.remove(document.local_path)
    except FileNotFoundError:
      return


class DocumentStorage:
  """Resolve the configured storage backend for learning documents."""

  @staticmethod
  def backend(name: str | None = None) -> DocumentStorageBackend:
    selected = (name or current_app.config.get("TEACHER_STORAGE_BACKEND") or "local").lower()
    if selected == "local":
      return LocalDocumentStorage(current_app.config["TEACHER_UPLOAD_FOLDER"])
    raise RuntimeError(
      f"Unsupported TEACHER_STORAGE_BACKEND '{selected}'. Configure 'local' until a remote adapter is installed."
    )

  @classmethod
  def for_book(cls, book: Book) -> DocumentStorageBackend:
    return cls.backend(book.storage_backend or "local")
