"""Grounded document-structure detection for uploaded learning material.

Phase 3 deliberately detects a hierarchy without creating course/module/topic
database entities. Every detected item is copied from the extracted document
and carries page-level provenance for later phases.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.extensions import db
from app.models.book_model import Book
from app.utils import utc_now


SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class HeadingCandidate:
  kind: str
  level: int
  title: str
  page_number: int
  confidence: float


class DocumentStructureDetector:
  """Detect only structure explicitly supported by extracted page content."""

  _MODULE_RE = re.compile(r"(?i)^(?:module|unit|part)\s+(?:\d+|[ivxlcdm]+)?\s*[:.\-)–]?\s*\S.*$")
  _CHAPTER_RE = re.compile(r"(?i)^chapter\s+(?:\d+|[ivxlcdm]+)?\s*[:.\-)–]?\s*\S.*$")
  _TOPIC_RE = re.compile(r"(?i)^(?:topic|section|lesson)\s+(?:\d+(?:\.\d+)*|[ivxlcdm]+)?\s*[:.\-)–]?\s*\S.*$")
  _SUBTOPIC_RE = re.compile(r"(?i)^subtopic\s+(?:\d+(?:\.\d+)*)?\s*[:.\-)–]?\s*\S.*$")
  _NUMBERED_RE = re.compile(r"^(\d+(?:\.\d+)+)\s*[:.\-)–]?\s+(.{2,120})$")
  _SINGLE_NUMBER_RE = re.compile(r"^\d{1,3}[.)]\s+(.{3,100})$")
  _DEFINITION_RE = re.compile(
    r"(?i)^\s*([A-Z][A-Za-z0-9 /\-]{2,60}?)\s+(?:is defined as|refers to|means)\s+(.{8,260})$"
    r"|^\s*([A-Z][A-Za-z0-9 /\-]{2,50}?)\s*:\s+(.{10,260})$"
  )
  _OBJECTIVE_MARKER_RE = re.compile(r"(?i)^(?:learning\s+)?objectives?|learning outcomes?|by the end of")
  _OBJECTIVE_VERB_RE = re.compile(
    r"(?i)^(?:to\s+)?(?:define|describe|discuss|differentiate|explain|identify|list|outline|recognize|understand|apply|compare|demonstrate|evaluate)\b"
  )
  _EXAMPLE_RE = re.compile(r"(?i)^(?:example|worked example|case example|clinical example|for example)\s*[:.\-]")
  _CLINICAL_CUES = (
    "clinical",
    "patient",
    "symptom",
    "diagnosis",
    "treatment",
    "assessment",
    "nursing intervention",
  )
  _EXAM_CUES = (
    "exam",
    "important",
    "key point",
    "remember",
    "high yield",
    "frequently asked",
  )
  _NOISE_HEADINGS = {
    "contents",
    "table of contents",
    "index",
    "references",
    "bibliography",
    "notes",
    "note",
    "warning",
    "summary",
  }

  @classmethod
  def detect(cls, book: Book) -> dict[str, Any]:
    extraction = book.structure_json or {}
    pages = cls._normalized_pages(book, extraction)
    headings = cls._heading_candidates(pages)
    hierarchy = cls._build_hierarchy(book, headings, len(pages) or book.page_count or 1)

    objectives: list[dict[str, Any]] = []
    definitions: list[dict[str, Any]] = []
    examples: list[dict[str, Any]] = []
    clinical: list[dict[str, Any]] = []
    exam_relevant: list[dict[str, Any]] = []
    important: list[dict[str, Any]] = []

    for page in pages:
      number = page["page_number"]
      text = page["text"]
      objectives.extend(cls._extract_objectives(book.id, number, text))
      page_definitions = cls._extract_definitions(book.id, number, text)
      definitions.extend(page_definitions)
      examples.extend(cls._extract_prefixed_lines(book.id, number, text, cls._EXAMPLE_RE, "example"))
      clinical.extend(cls._extract_cued_lines(book.id, number, text, cls._CLINICAL_CUES, "clinical_concept"))
      exam_relevant.extend(cls._extract_cued_lines(book.id, number, text, cls._EXAM_CUES, "exam_relevant"))
      for item in page_definitions:
        important.append(
          {
            "title": item["term"],
            "category": "definition",
            "source": item["source"],
          }
        )

    for heading in headings:
      if heading.kind in ("topic", "subtopic"):
        important.append(
          {
            "title": heading.title,
            "category": "document_heading",
            "source": cls._source(book.id, heading.page_number, heading.title),
          }
        )

    course_title, course_source = cls._course_identity(book, pages, headings)
    counts = cls._counts(hierarchy)
    counts.update(
      {
        "learning_objectives": len(cls._unique_evidence(objectives, "text")),
        "important_concepts": len(cls._unique_evidence(important, "title")),
        "definitions": len(cls._unique_evidence(definitions, "term")),
        "examples": len(cls._unique_evidence(examples, "text")),
        "clinical_concepts": len(cls._unique_evidence(clinical, "text")),
        "exam_relevant_concepts": len(cls._unique_evidence(exam_relevant, "text")),
      }
    )

    warnings = []
    if counts["modules"] == 0:
      warnings.append("No explicit module or unit headings were found; modules were not invented.")
    if counts["chapters"] == 0:
      warnings.append("No explicit chapter headings were found; chapters were not invented.")
    if not hierarchy:
      warnings.append("The document did not contain reliable structural headings.")

    return {
      "schema_version": SCHEMA_VERSION,
      "method": "deterministic_heuristic",
      "document_id": book.id,
      "detected_at": utc_now().isoformat(),
      "course": {
        "title": course_title,
        "source": course_source,
      },
      "hierarchy": hierarchy,
      "learning_objectives": cls._unique_evidence(objectives, "text")[:100],
      "important_concepts": cls._unique_evidence(important, "title")[:150],
      "definitions": cls._unique_evidence(definitions, "term")[:100],
      "examples": cls._unique_evidence(examples, "text")[:100],
      "clinical_concepts": cls._unique_evidence(clinical, "text")[:100],
      "exam_relevant_concepts": cls._unique_evidence(exam_relevant, "text")[:100],
      "counts": counts,
      "warnings": warnings,
      "grounding": {
        "source_policy": "uploaded_document_only",
        "ai_generated": False,
        "note": "Detected labels are copied from extracted document text and retain page references.",
      },
    }

  @staticmethod
  def _normalized_pages(book: Book, extraction: dict) -> list[dict[str, Any]]:
    pages = []
    for index, raw in enumerate(extraction.get("pages") or []):
      if not isinstance(raw, dict):
        continue
      text = str(raw.get("text") or "").strip()
      headings = [str(value).strip() for value in raw.get("headings") or [] if str(value).strip()]
      pages.append(
        {
          "page_number": int(raw.get("page_number") or index + 1),
          "text": text,
          "headings": headings,
        }
      )
    if not pages and (book.extracted_text or "").strip():
      pages.append({"page_number": 1, "text": book.extracted_text.strip(), "headings": []})
    return pages

  @classmethod
  def _heading_candidates(cls, pages: list[dict[str, Any]]) -> list[HeadingCandidate]:
    candidates: list[HeadingCandidate] = []
    seen = set()
    for page in pages:
      text = page["text"]
      if cls._is_contents_page(text):
        continue
      page_number = page["page_number"]
      styled = page["headings"]
      raw_candidates = [(value, True) for value in styled]
      raw_candidates.extend((line.strip(), False) for line in text.splitlines() if line.strip())
      for raw, is_styled in raw_candidates:
        classified = cls._classify_heading(raw, is_styled=is_styled)
        if not classified:
          continue
        kind, level, confidence = classified
        title = cls._clean_line(raw)
        key = (page_number, kind, title.casefold())
        if key in seen:
          continue
        seen.add(key)
        candidates.append(HeadingCandidate(kind, level, title, page_number, confidence))
    return candidates[:500]

  @classmethod
  def _classify_heading(cls, raw: str, *, is_styled: bool) -> tuple[str, int, float] | None:
    text = cls._clean_line(raw)
    low = text.casefold().rstrip(":")
    if not text or len(text) > 140 or low in cls._NOISE_HEADINGS:
      return None
    if cls._OBJECTIVE_MARKER_RE.match(text):
      return None
    if cls._MODULE_RE.match(text):
      return "module", 1, 0.99
    if cls._CHAPTER_RE.match(text):
      return "chapter", 2, 0.99
    if cls._SUBTOPIC_RE.match(text):
      return "subtopic", 4, 0.98
    if cls._TOPIC_RE.match(text):
      return "topic", 3, 0.98
    numbered = cls._NUMBERED_RE.match(text)
    if numbered:
      depth = numbered.group(1).count(".") + 1
      return ("subtopic", 4, 0.9) if depth >= 3 else ("topic", 3, 0.9)
    if is_styled and cls._SINGLE_NUMBER_RE.match(text):
      return "topic", 3, 0.82
    if is_styled and 2 <= len(text.split()) <= 14 and not text.endswith(('.', '?', '!')):
      return "topic", 3, 0.72
    return None

  @classmethod
  def _build_hierarchy(
    cls,
    book: Book,
    headings: list[HeadingCandidate],
    last_page: int,
  ) -> list[dict[str, Any]]:
    roots: list[dict[str, Any]] = []
    stack: list[tuple[int, dict[str, Any]]] = []
    sequence: list[tuple[HeadingCandidate, dict[str, Any]]] = []
    kind_counts = {"module": 0, "chapter": 0, "topic": 0, "subtopic": 0}

    for heading in headings:
      kind_counts[heading.kind] += 1
      node = {
        "id": f"{heading.kind}-{kind_counts[heading.kind]}",
        "type": heading.kind,
        "title": heading.title,
        "order_index": kind_counts[heading.kind],
        "page_start": heading.page_number,
        "page_end": heading.page_number,
        "confidence": heading.confidence,
        "source": cls._source(book.id, heading.page_number, heading.title),
        "children": [],
      }
      while stack and stack[-1][0] >= heading.level:
        stack.pop()
      if stack:
        stack[-1][1]["children"].append(node)
      else:
        roots.append(node)
      stack.append((heading.level, node))
      sequence.append((heading, node))

    for index, (heading, node) in enumerate(sequence):
      end_page = last_page
      for next_heading, _ in sequence[index + 1 :]:
        if next_heading.level <= heading.level:
          end_page = max(heading.page_number, next_heading.page_number - 1)
          break
      node["page_end"] = end_page
      node["source"]["page_end"] = end_page
      node["source"]["page_numbers"] = list(range(heading.page_number, end_page + 1))[:100]
    return roots

  @classmethod
  def _extract_objectives(cls, document_id: int, page_number: int, text: str) -> list[dict[str, Any]]:
    out = []
    capturing = False
    for raw in text.splitlines():
      line = cls._clean_line(raw)
      if not line:
        continue
      if cls._OBJECTIVE_MARKER_RE.match(line):
        capturing = True
        continue
      cleaned = re.sub(r"^[•\-*–\d.)\s]+", "", line).strip()
      if capturing and (cls._OBJECTIVE_VERB_RE.match(cleaned) or raw.lstrip().startswith(("•", "-", "*", "–"))):
        out.append({"text": cleaned, "source": cls._source(document_id, page_number, line)})
        if len(out) >= 20:
          break
        continue
      if capturing and (cls._classify_heading(line, is_styled=False) or len(line) > 220):
        capturing = False
      elif cls._OBJECTIVE_VERB_RE.match(cleaned) and "objective" in text[: max(0, text.find(raw))].lower()[-300:]:
        out.append({"text": cleaned, "source": cls._source(document_id, page_number, line)})
    return out

  @classmethod
  def _extract_definitions(cls, document_id: int, page_number: int, text: str) -> list[dict[str, Any]]:
    out = []
    for raw in text.splitlines():
      line = cls._clean_line(raw)
      if cls._classify_heading(line, is_styled=False):
        continue
      match = cls._DEFINITION_RE.match(line)
      if not match:
        continue
      term = (match.group(1) or match.group(3) or "").strip()
      definition = (match.group(2) or match.group(4) or "").strip()
      term_key = term.casefold()
      if term_key in {"objectives", "learning objectives", "example", "note"} or term_key.startswith(
        ("clinical example", "worked example", "important", "key point", "remember")
      ):
        continue
      out.append(
        {
          "term": term,
          "definition": definition,
          "source": cls._source(document_id, page_number, line),
        }
      )
    return out

  @classmethod
  def _extract_prefixed_lines(
    cls,
    document_id: int,
    page_number: int,
    text: str,
    pattern: re.Pattern,
    category: str,
  ) -> list[dict[str, Any]]:
    out = []
    for raw in text.splitlines():
      line = cls._clean_line(raw)
      if pattern.match(line) and 10 <= len(line) <= 400:
        out.append({"text": line, "category": category, "source": cls._source(document_id, page_number, line)})
    return out

  @classmethod
  def _extract_cued_lines(
    cls,
    document_id: int,
    page_number: int,
    text: str,
    cues: tuple[str, ...],
    category: str,
  ) -> list[dict[str, Any]]:
    out = []
    for raw in text.splitlines():
      line = cls._clean_line(raw)
      low = line.casefold()
      if 12 <= len(line) <= 400 and any(cue in low for cue in cues):
        out.append({"text": line, "category": category, "source": cls._source(document_id, page_number, line)})
    return out

  @staticmethod
  def _course_identity(
    book: Book,
    pages: list[dict[str, Any]],
    headings: list[HeadingCandidate],
  ) -> tuple[str, dict[str, Any]]:
    first_page = pages[0]["page_number"] if pages else 1
    for heading in headings:
      if heading.page_number == first_page and heading.kind == "topic" and heading.confidence < 0.9:
        return heading.title, DocumentStructureDetector._source(book.id, first_page, heading.title)
    return (
      book.title,
      {
        "document_id": book.id,
        "page_numbers": [],
        "page_start": None,
        "page_end": None,
        "excerpt": book.title,
        "source_kind": "upload_metadata",
      },
    )

  @staticmethod
  def _source(document_id: int, page_number: int, excerpt: str) -> dict[str, Any]:
    return {
      "document_id": document_id,
      "page_numbers": [page_number],
      "page_start": page_number,
      "page_end": page_number,
      "excerpt": excerpt[:500],
      "source_kind": "uploaded_document",
    }

  @classmethod
  def _unique_evidence(cls, values: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    out = []
    seen = set()
    for value in values:
      key = re.sub(r"\W+", " ", str(value.get(field) or "").casefold()).strip()
      if not key or key in seen:
        continue
      seen.add(key)
      out.append(value)
    return out

  @staticmethod
  def _counts(hierarchy: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"modules": 0, "chapters": 0, "topics": 0, "subtopics": 0}

    def visit(nodes):
      for node in nodes:
        key = f"{node['type']}s"
        counts[key] += 1
        visit(node.get("children") or [])

    visit(hierarchy)
    return counts

  @staticmethod
  def _is_contents_page(text: str) -> bool:
    head = " ".join(text.splitlines()[:8]).casefold()
    return "table of contents" in head or head.strip().startswith("contents")

  @staticmethod
  def _clean_line(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lstrip("# ").strip()


class DocumentStructureService:
  """Persist and retrieve Phase 3 structure while enforcing book ownership."""

  @classmethod
  def detect_for_book(cls, book_id: int, user_id: int | None = None) -> dict[str, Any]:
    query = Book.query.filter_by(id=book_id)
    if user_id is not None:
      query = query.filter_by(user_id=user_id)
    book = query.first()
    if not book:
      raise LookupError("Book not found.")
    if not (book.extracted_text or "").strip():
      raise ValueError("Document text must be extracted before structure detection.")

    detected = DocumentStructureDetector.detect(book)
    extraction = dict(book.structure_json or {})
    extraction["structure_schema_version"] = SCHEMA_VERSION
    extraction["detected_structure"] = detected
    book.structure_json = extraction
    book.updated_at = utc_now()
    db.session.commit()
    return detected

  @staticmethod
  def get_for_book(book: Book) -> dict[str, Any] | None:
    return (book.structure_json or {}).get("detected_structure")
