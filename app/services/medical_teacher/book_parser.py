"""Book Parser — AI Medical Teacher Module 2.

Splits extracted text into chapters/topics and detects medical content signals.
Uses heuristic analysis first (works offline). Optionally enriches with Gemini/OpenAI
while clearly labeling AI-inferred vs document-extracted fields.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from app.extensions import db
from app.models.book_model import (
  BOOK_STATUS_EXTRACTED,
  BOOK_STATUS_FAILED,
  BOOK_STATUS_PARSED,
  BOOK_STATUS_PARSING,
  Book,
  Chapter,
)
from app.services.medical_teacher.ai_client import TeacherAIClient
from app.utils import utc_now

logger = logging.getLogger(__name__)

CHAPTER_HEADING_RE = re.compile(
  r"(?im)^(?:\s*(?:chapter|unit|module|section|lesson|part)\s+(\d+[A-Za-z]?)\s*[\.:)\-–]?\s+(.+)"
  r"|\s*(\d{1,2})[\.\)]\s+([A-Z][^\n]{3,80})"
  r"|\s*#{1,3}\s+(.+))\s*$"
)
PAGE_MARKER_RE = re.compile(r"===== PAGE (\d+) =====")
DEFINITION_RE = re.compile(
  r"(?im)^\s*([A-Z][A-Za-z0-9 \-/]{2,60}?)\s+(?:is defined as|refers to|means)\s+(.{10,200})$"
  r"|^\s*([A-Z][A-Za-z0-9 \-/]{2,40}?)\s*:\s+(.{15,200})$"
)
AUTHOR_RE = re.compile(
  r"(?im)^\s*(?:author|authors|by|written by)\s*[:\-–]\s*(.+)$"
)
SUBJECT_HINTS = (
  ("cardiology", ("heart", "cardiac", "coronary", "ecg", "hypertension", "myocardial")),
  ("nursing fundamentals", ("vital signs", "nursing", "patient care", "medication administration")),
  ("pharmacology", ("drug", "dose", "medication", "pharmacolog", "antibiotic")),
  ("neurology", ("stroke", "seizure", "neuro", "brain", "cns")),
  ("pediatrics", ("infant", "child", "pediatric", "neonat")),
  ("emergency medicine", ("trauma", "triage", "emergency", "resuscitation", "bls", "acls")),
  ("infection control", ("infection", "sepsis", "antiseptic", "sterile", "pathogen")),
  ("laboratory medicine", ("hemoglobin", "wbc", "lab value", "reference range", "cbc")),
)

AI_SYSTEM_PROMPT = (
  "You are a medical education content analyst for nursing/medical students. "
  "You receive text EXTRACTED FROM AN UPLOADED DOCUMENT. "
  "Use ONLY information supported by that text. Do NOT invent diseases, drugs, doses, "
  "or clinical facts that are not present. If something is unclear or missing, omit it "
  "or mark it as unknown. "
  "Respond ONLY with valid JSON matching the requested schema. "
  "Clearly keep educational paraphrases minimal; prefer phrases found in the source."
)


@dataclass
class ParsedChapterDraft:
  title: str
  content: str
  order_index: int
  page_start: int | None = None
  page_end: int | None = None
  topics: list[str] = field(default_factory=list)
  subtopics: list[str] = field(default_factory=list)
  key_concepts: list[str] = field(default_factory=list)
  learning_objectives: list[str] = field(default_factory=list)
  summary: str | None = None
  source: str = "document"


@dataclass
class BookParseResult:
  success: bool
  book: Book | None = None
  chapters: list[Chapter] = field(default_factory=list)
  analysis: dict[str, Any] = field(default_factory=dict)
  parse_method: str = "heuristic"
  message: str = ""
  error_code: str | None = None

  def to_dict(self) -> dict:
    return {
      "success": self.success,
      "parse_method": self.parse_method,
      "message": self.message,
      "error_code": self.error_code,
      "analysis": self.analysis,
      "book": self.book.to_dict(include_analysis=True, include_chapters=True) if self.book else None,
      "chapters": [c.to_dict() for c in self.chapters],
    }


class BookParser:
  """Parse extracted book text into chapters and medical content analysis."""

  MAX_AI_CHARS = 24000

  @classmethod
  def parse_book(cls, book_id: int, user_id: int | None = None, use_ai: bool = True) -> BookParseResult:
    query = Book.query.filter_by(id=book_id)
    if user_id is not None:
      query = query.filter_by(user_id=user_id)
    book = query.first()
    if not book:
      return BookParseResult(success=False, message="Book not found.", error_code="not_found")

    if not (book.extracted_text or "").strip():
      return BookParseResult(
        success=False,
        book=book,
        message="Book has no extracted text. Run document extraction first.",
        error_code="not_extracted",
      )

    if book.status not in (
      BOOK_STATUS_EXTRACTED,
      BOOK_STATUS_PARSED,
      BOOK_STATUS_FAILED,
      BOOK_STATUS_PARSING,
    ):
      # Allow re-parse after extract; also allow uploaded if text somehow present
      if book.status != BOOK_STATUS_EXTRACTED and not book.extracted_text:
        return BookParseResult(
          success=False,
          book=book,
          message=f"Book status '{book.status}' is not ready for parsing.",
          error_code="invalid_status",
        )

    book.status = BOOK_STATUS_PARSING
    book.error_message = None
    book.updated_at = utc_now()
    db.session.commit()

    try:
      drafts, heuristic_analysis = cls._heuristic_parse(book)
      parse_method = "heuristic"
      analysis = heuristic_analysis

      if use_ai:
        ai_data, provider = cls._ai_enrich(book, drafts, heuristic_analysis)
        if ai_data and provider != "none":
          drafts, analysis = cls._merge_ai(drafts, heuristic_analysis, ai_data)
          parse_method = "hybrid" if provider else "heuristic"
          if provider in ("gemini", "openai"):
            parse_method = "hybrid"

      # Replace chapters
      Chapter.query.filter_by(book_id=book.id).delete()
      saved: list[Chapter] = []
      for draft in drafts:
        chapter = Chapter(
          book_id=book.id,
          order_index=draft.order_index,
          title=draft.title[:300],
          summary=draft.summary,
          content=draft.content,
          page_start=draft.page_start,
          page_end=draft.page_end,
          word_count=len(re.findall(r"\b\w+\b", draft.content or "")),
          topics=draft.topics[:30],
          subtopics=draft.subtopics[:40],
          key_concepts=draft.key_concepts[:40],
          learning_objectives=draft.learning_objectives[:20],
          source=draft.source,
        )
        db.session.add(chapter)
        saved.append(chapter)

      # Update book metadata from analysis (prefer document-backed values)
      meta = analysis.get("metadata") or {}
      if meta.get("title") and cls._looks_better_title(meta["title"], book.title):
        book.title = str(meta["title"])[:300]
      if meta.get("author"):
        book.author = str(meta["author"])[:200]
      if meta.get("medical_subject"):
        book.medical_subject = str(meta["medical_subject"])[:150]
      if meta.get("description"):
        book.description = str(meta["description"])[:2000]

      book.analysis_json = analysis
      book.parse_method = parse_method
      book.chapter_count = len(saved)
      book.parsed_at = utc_now()
      book.status = BOOK_STATUS_PARSED
      book.error_message = None
      book.updated_at = utc_now()
      db.session.commit()

      return BookParseResult(
        success=True,
        book=book,
        chapters=saved,
        analysis=analysis,
        parse_method=parse_method,
        message=f"Parsed {len(saved)} chapter(s) using {parse_method} analysis.",
      )
    except Exception as exc:
      logger.exception("Book parse failed for book_id=%s", book_id)
      db.session.rollback()
      book = Book.query.get(book_id)
      if book:
        book.status = BOOK_STATUS_FAILED
        book.error_message = f"Book parsing failed: {exc}"
        book.updated_at = utc_now()
        db.session.commit()
      return BookParseResult(
        success=False,
        book=book,
        message=str(exc),
        error_code="parse_failed",
      )

  # ------------------------------------------------------------------ heuristic

  @classmethod
  def _heuristic_parse(cls, book: Book) -> tuple[list[ParsedChapterDraft], dict[str, Any]]:
    text = book.extracted_text or ""
    structure = book.structure_json or {}
    drafts = cls._split_chapters(text, structure)
    if not drafts:
      drafts = [
        ParsedChapterDraft(
          title=book.title or "Full Document",
          content=text.strip(),
          order_index=1,
          page_start=1,
          page_end=book.page_count,
          source="document",
        )
      ]

    for draft in drafts:
      draft.topics = cls._extract_topics(draft.content)
      draft.subtopics = cls._extract_subtopics(draft.content, draft.topics)
      draft.key_concepts = cls._extract_key_concepts(draft.content)
      draft.learning_objectives = cls._extract_objectives(draft.content)
      draft.summary = cls._make_summary(draft.content)

    book_level = cls._analyze_document(book, text, drafts)
    return drafts, book_level

  @classmethod
  def _split_chapters(cls, text: str, structure: dict) -> list[ParsedChapterDraft]:
    # 1) Prefer explicit Chapter/Unit/Module headings in the full text
    regex_drafts = cls._split_by_regex_headings(text)
    if len(regex_drafts) >= 2:
      return regex_drafts

    # 2) Module 1 structure headings that look like real chapters/sections
    heading_candidates: list[str] = []
    for page in structure.get("pages") or []:
      for h in page.get("headings") or []:
        if h and h.strip() and h.strip() not in heading_candidates:
          heading_candidates.append(h.strip())

    strong = [h for h in heading_candidates if cls._is_strong_chapter_heading(h)]
    if len(strong) >= 2:
      drafts = cls._split_by_titles(text, strong)
      if len(drafts) >= 2:
        return drafts

    # 3) Fallback: page groups
    page_splits = list(PAGE_MARKER_RE.finditer(text))
    if len(page_splits) >= 4:
      chunk_size = max(2, len(page_splits) // 3)
      drafts = []
      for i in range(0, len(page_splits), chunk_size):
        start = page_splits[i].start()
        end = page_splits[i + chunk_size].start() if i + chunk_size < len(page_splits) else len(text)
        page_no = int(page_splits[i].group(1))
        end_page = int(page_splits[min(i + chunk_size - 1, len(page_splits) - 1)].group(1))
        content = text[start:end].strip()
        drafts.append(
          ParsedChapterDraft(
            title=f"Pages {page_no}–{end_page}",
            content=content,
            order_index=len(drafts) + 1,
            page_start=page_no,
            page_end=end_page,
            source="document",
          )
        )
      return drafts

    return []

  @classmethod
  def _split_by_regex_headings(cls, text: str) -> list[ParsedChapterDraft]:
    matches = list(CHAPTER_HEADING_RE.finditer(text))
    titles: list[tuple[int, str]] = []
    for m in matches:
      start = m.start()
      if m.group(2):
        title = f"Chapter {m.group(1)}: {m.group(2).strip()}"
      elif m.group(4):
        # Avoid treating every numbered list item as a chapter
        candidate = f"{m.group(3)}. {m.group(4).strip()}"
        if not cls._is_strong_chapter_heading(candidate) and not re.match(
          r"(?i)^(chapter|unit|module|section|lesson|part)\b", candidate
        ):
          # Only keep numbered headings that look sectional (short title words)
          if len(m.group(4).split()) > 8:
            continue
        title = candidate
      else:
        title = (m.group(5) or m.group(0)).strip()
      # Skip markdown headings that are too generic / note banners
      if cls._is_noise_heading(title):
        continue
      titles.append((start, title[:300]))

    filtered: list[tuple[int, str]] = []
    for start, title in titles:
      if filtered and start - filtered[-1][0] < 40:
        continue
      # Prefer chapter/unit style; drop bare numbered list noise when chapter markers exist
      filtered.append((start, title))

    chapter_like = [
      t for t in filtered
      if re.match(r"(?i)^(chapter|unit|module|section|lesson|part)\b", t[1])
      or t[1].startswith("#")
    ]
    if len(chapter_like) >= 2:
      filtered = chapter_like
    elif len(filtered) < 2:
      return []

    drafts = []
    for i, (start, title) in enumerate(filtered):
      end = filtered[i + 1][0] if i + 1 < len(filtered) else len(text)
      content = text[start:end].strip()
      drafts.append(
        ParsedChapterDraft(
          title=title.lstrip("# ").strip(),
          content=content,
          order_index=i + 1,
          page_start=cls._page_at(text, start),
          page_end=cls._page_at(text, end - 1 if end > start else start),
          source="document",
        )
      )
    return drafts

  @staticmethod
  def _is_noise_heading(heading: str) -> bool:
    h = heading.strip().lstrip("# ").strip().lower()
    noise = {
      "important notes",
      "note",
      "notes",
      "warning",
      "caution",
      "summary",
      "introduction",
      "references",
      "table of contents",
      "contents",
      "index",
      "appendix",
    }
    return h in noise

  @classmethod
  def _split_by_titles(cls, text: str, titles: list[str]) -> list[ParsedChapterDraft]:
    positions: list[tuple[int, str]] = []
    lower_text = text.lower()
    search_from = 0
    for title in titles:
      idx = lower_text.find(title.lower(), search_from)
      if idx < 0:
        idx = lower_text.find(title.lower())
      if idx < 0:
        continue
      positions.append((idx, title))
      search_from = idx + len(title)

    if len(positions) < 2:
      return []

    drafts = []
    for i, (start, title) in enumerate(positions):
      end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
      drafts.append(
        ParsedChapterDraft(
          title=title,
          content=text[start:end].strip(),
          order_index=i + 1,
          page_start=cls._page_at(text, start),
          page_end=cls._page_at(text, end - 1 if end > start else start),
          source="document",
        )
      )
    return drafts

  @staticmethod
  def _is_strong_chapter_heading(heading: str) -> bool:
    h = heading.strip()
    if not h or BookParser._is_noise_heading(h):
      return False
    if re.match(r"(?i)^(chapter|unit|module|section|lesson|part)\b", h):
      return True
    if re.match(r"^\d{1,2}[\.\)]\s+[A-Z].{3,60}$", h) and len(h.split()) <= 8:
      return True
    # ALL CAPS section titles — only if short and not a banner/note
    if h.isupper() and 8 <= len(h) <= 60 and any(c.isalpha() for c in h):
      return True
    return False

  @classmethod
  def _extract_definitions(cls, text: str) -> list[dict[str, str]]:
    out = []
    seen = set()
    skip_terms = {
      "author",
      "authors",
      "by",
      "written by",
      "medications",
      "symptoms",
      "diagnostic methods",
      "learning objectives",
      "objectives",
      "common symptom",
    }
    for m in DEFINITION_RE.finditer(text):
      if m.group(1):
        term, definition = m.group(1), m.group(2)
      else:
        term, definition = m.group(3), m.group(4)
      term = (term or "").strip(" :-–")
      definition = (definition or "").strip()
      key = term.lower()
      if key in seen or key in skip_terms or len(term) < 3 or "\n" in term:
        continue
      seen.add(key)
      out.append({"term": term, "definition": definition, "source": "document"})
    return out

  @classmethod
  def _extract_key_concepts(cls, content: str) -> list[str]:
    concepts = []
    for item in cls._extract_definitions(content):
      term = item["term"]
      if term not in concepts:
        concepts.append(term)
    for m in re.finditer(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b", content):
      phrase = m.group(1)
      if phrase not in concepts and len(concepts) < 25:
        concepts.append(phrase)
    return concepts[:25]
  @staticmethod
  def _page_at(text: str, pos: int) -> int | None:
    last = None
    for m in PAGE_MARKER_RE.finditer(text):
      if m.start() <= pos:
        last = int(m.group(1))
      else:
        break
    return last

  @classmethod
  def _extract_topics(cls, content: str) -> list[str]:
    topics = []
    for line in content.splitlines():
      line = line.strip()
      if not line or len(line) > 100:
        continue
      if cls._is_strong_chapter_heading(line) or re.match(r"^#{1,3}\s+", line):
        clean = line.lstrip("# ").strip()
        if clean and clean not in topics:
          topics.append(clean)
      elif re.match(r"^\d+(\.\d+)+\s+\S", line):
        topics.append(line)
    return topics[:20]

  @classmethod
  def _extract_subtopics(cls, content: str, topics: list[str]) -> list[str]:
    subs = []
    for line in content.splitlines():
      line = line.strip()
      if re.match(r"^[•\-–*]\s+\S", line) or re.match(r"^[a-z][\.)]\s+\S", line, re.I):
        item = re.sub(r"^[•\-–*\w\.\)]\s*", "", line).strip()
        if 3 < len(item) < 120 and item not in topics and item not in subs:
          subs.append(item)
    return subs[:30]

  @classmethod
  def _extract_objectives(cls, content: str) -> list[str]:
    objectives = []
    capture = False
    for line in content.splitlines():
      stripped = line.strip()
      if re.search(r"(?i)learning\s+objectives?|objectives?:|by the end of", stripped):
        capture = True
        continue
      if capture:
        if not stripped or cls._is_strong_chapter_heading(stripped):
          capture = False
          continue
        if re.match(r"^[•\-–*\d]", stripped) or stripped.lower().startswith(("to ", "understand", "describe", "explain", "identify")):
          objectives.append(re.sub(r"^[•\-–*\d\.\)\s]+", "", stripped))
    return objectives[:15]

  @staticmethod
  def _make_summary(content: str, max_sentences: int = 3) -> str:
    cleaned = PAGE_MARKER_RE.sub(" ", content)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    sentences = [p.strip() for p in parts if 40 < len(p.strip()) < 300]
    return " ".join(sentences[:max_sentences]) if sentences else cleaned[:280]

  @classmethod
  def _analyze_document(
    cls,
    book: Book,
    text: str,
    drafts: list[ParsedChapterDraft],
  ) -> dict[str, Any]:
    definitions = cls._extract_definitions(text)
    medical_terms = [d["term"] for d in definitions]
    for draft in drafts:
      for c in draft.key_concepts:
        if c not in medical_terms:
          medical_terms.append(c)

    subject = cls._infer_subject(text) or book.medical_subject
    author = cls._extract_author(text) or book.author

    diseases = cls._extract_labeled_terms(text, ("disease", "disorder", "syndrome", "condition"))
    treatments = cls._extract_labeled_terms(text, ("treatment", "therapy", "management", "intervention"))
    medicines = cls._extract_medicine_candidates(text)
    symptoms = cls._extract_labeled_terms(text, ("symptom", "sign", "presents with", "complaint"))
    procedures = cls._extract_labeled_terms(text, ("procedure", "technique", "assessment", "protocol"))
    diagnostics = cls._extract_labeled_terms(text, ("diagnos", "test", "screening", "imaging", "lab"))

    analysis = {
      "metadata": {
        "title": book.title,
        "author": author,
        "medical_subject": subject,
        "description": cls._make_summary(text, max_sentences=2),
        "source": "document",
      },
      "key_concepts": cls._unique(sum((d.key_concepts for d in drafts), []))[:40],
      "medical_terms": cls._unique(medical_terms)[:40],
      "definitions": definitions[:40],
      "clinical_procedures": procedures[:30],
      "diseases": diseases[:30],
      "treatments": treatments[:30],
      "medicines": medicines[:30],
      "symptoms": symptoms[:30],
      "diagnostic_methods": diagnostics[:30],
      "learning_objectives": cls._unique(sum((d.learning_objectives for d in drafts), []))[:30],
      "chapters_outline": [{"order": d.order_index, "title": d.title, "topics": d.topics} for d in drafts],
      "analysis_mode": "heuristic",
      "provenance": {
        "document_extracted": [
          "chapters",
          "topics",
          "definitions",
          "key_concepts",
          "lists_and_headings",
        ],
        "ai_inferred": [],
        "safety_note": (
          "Heuristic fields are derived from the uploaded document text/structure. "
          "They may be incomplete. AI enrichment (if enabled) is labeled separately."
        ),
      },
    }
    return analysis

  @staticmethod
  def _extract_author(text: str) -> str | None:
    # Only scan early portion
    head = text[:2500]
    m = AUTHOR_RE.search(head)
    if m:
      return m.group(1).strip()[:200]
    return None

  @staticmethod
  def _infer_subject(text: str) -> str | None:
    lower = text.lower()
    scores = []
    for label, keywords in SUBJECT_HINTS:
      score = sum(lower.count(k) for k in keywords)
      if score:
        scores.append((score, label))
    if not scores:
      return None
    scores.sort(reverse=True)
    return scores[0][1].title() if scores[0][0] >= 2 else None

  @classmethod
  def _extract_labeled_terms(cls, text: str, cues: tuple[str, ...]) -> list[str]:
    found = []
    for line in text.splitlines():
      low = line.lower()
      if not any(c in low for c in cues):
        continue
      # grab capitalized phrases on the line
      for m in re.finditer(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b", line):
        term = m.group(1)
        if term.lower() not in {c.lower() for c in cues} and term not in found:
          found.append(term)
    return found[:30]

  @classmethod
  def _extract_medicine_candidates(cls, text: str) -> list[str]:
    meds = []
    patterns = (
      r"(?i)\b([A-Z][a-z]+(?:cillin|mycin|olol|pril|sartan|statin|pine|azole|pam|lam))\b",
      r"(?i)\b(aspirin|metformin|insulin|warfarin|heparin|morphine|paracetamol|ibuprofen|amoxicillin)\b",
    )
    for pat in patterns:
      for m in re.finditer(pat, text):
        name = m.group(1)
        pretty = name[0].upper() + name[1:]
        if pretty not in meds:
          meds.append(pretty)
    return meds[:30]

  @staticmethod
  def _unique(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
      key = (item or "").strip().lower()
      if not key or key in seen:
        continue
      seen.add(key)
      out.append(item.strip())
    return out

  @staticmethod
  def _looks_better_title(candidate: str, current: str) -> bool:
    c = (candidate or "").strip()
    cur = (current or "").strip()
    if not c or c.lower() in {"untitled", "untitled medical document"}:
      return False
    if not cur or cur.lower() in {"untitled", "untitled medical document"}:
      return True
    # Prefer titles that are not just filenames
    if "_" in cur and " " in c:
      return True
    return False

  # ------------------------------------------------------------------ AI

  @classmethod
  def _ai_enrich(
    cls,
    book: Book,
    drafts: list[ParsedChapterDraft],
    heuristic: dict[str, Any],
  ) -> tuple[dict[str, Any] | None, str]:
    outline = [{"order": d.order_index, "title": d.title, "summary": d.summary} for d in drafts]
    excerpt = (book.extracted_text or "")[: cls.MAX_AI_CHARS]
    user_prompt = (
      "Analyze this uploaded medical teaching document.\n"
      "Return JSON with schema:\n"
      "{\n"
      '  "metadata": {"title": "", "author": "", "medical_subject": "", "description": ""},\n'
      '  "chapters": [{"order": 1, "title": "", "topics": [], "subtopics": [], '
      '"key_concepts": [], "learning_objectives": [], "summary": ""}],\n'
      '  "key_concepts": [], "medical_terms": [], '
      '"definitions": [{"term": "", "definition": ""}],\n'
      '  "clinical_procedures": [], "diseases": [], "treatments": [], '
      '"medicines": [], "symptoms": [], "diagnostic_methods": [], '
      '"learning_objectives": [],\n'
      '  "unsupported_or_unclear": []\n'
      "}\n\n"
      f"Heuristic outline (from document structure):\n{outline}\n\n"
      f"Document text (may be truncated):\n{excerpt}"
    )
    return TeacherAIClient.complete_json(AI_SYSTEM_PROMPT, user_prompt)

  @classmethod
  def _merge_ai(
    cls,
    drafts: list[ParsedChapterDraft],
    heuristic: dict[str, Any],
    ai_data: dict[str, Any],
  ) -> tuple[list[ParsedChapterDraft], dict[str, Any]]:
    """Merge AI suggestions onto heuristic baseline; mark AI fields in provenance."""
    merged = dict(heuristic)
    ai_inferred: list[str] = []

    meta_h = dict(merged.get("metadata") or {})
    meta_ai = ai_data.get("metadata") or {}
    for key in ("title", "author", "medical_subject", "description"):
      if meta_ai.get(key) and not meta_h.get(key):
        meta_h[key] = meta_ai[key]
        ai_inferred.append(f"metadata.{key}")
      elif meta_ai.get(key) and key in ("author", "medical_subject") and not meta_h.get(key):
        meta_h[key] = meta_ai[key]
        ai_inferred.append(f"metadata.{key}")
    # Prefer AI title only if heuristic title looks like a filename
    if meta_ai.get("title") and cls._looks_better_title(meta_ai["title"], meta_h.get("title") or ""):
      meta_h["title"] = meta_ai["title"]
      if "metadata.title" not in ai_inferred:
        ai_inferred.append("metadata.title")
    meta_h["source"] = "hybrid" if ai_inferred else "document"
    merged["metadata"] = meta_h

    list_fields = (
      "key_concepts",
      "medical_terms",
      "clinical_procedures",
      "diseases",
      "treatments",
      "medicines",
      "symptoms",
      "diagnostic_methods",
      "learning_objectives",
    )
    for field_name in list_fields:
      base = list(merged.get(field_name) or [])
      extra = ai_data.get(field_name) or []
      if isinstance(extra, list) and extra:
        before = len(base)
        base = cls._unique(base + [str(x) for x in extra if x])
        if len(base) > before:
          ai_inferred.append(field_name)
        merged[field_name] = base[:40]

    defs = list(merged.get("definitions") or [])
    for item in ai_data.get("definitions") or []:
      if not isinstance(item, dict):
        continue
      term = str(item.get("term") or "").strip()
      definition = str(item.get("definition") or "").strip()
      if not term or not definition:
        continue
      if any(d.get("term", "").lower() == term.lower() for d in defs):
        continue
      defs.append({"term": term, "definition": definition, "source": "ai_assisted"})
      if "definitions" not in ai_inferred:
        ai_inferred.append("definitions")
    merged["definitions"] = defs[:40]

    # Enrich chapter drafts by order/title match
    ai_chapters = ai_data.get("chapters") or []
    for draft in drafts:
      match = None
      for ch in ai_chapters:
        if not isinstance(ch, dict):
          continue
        if int(ch.get("order") or -1) == draft.order_index:
          match = ch
          break
        if str(ch.get("title") or "").strip().lower() == draft.title.lower():
          match = ch
          break
      if not match:
        continue
      for attr, key in (
        ("topics", "topics"),
        ("subtopics", "subtopics"),
        ("key_concepts", "key_concepts"),
        ("learning_objectives", "learning_objectives"),
      ):
        extra = match.get(key) or []
        if isinstance(extra, list) and extra:
          current = getattr(draft, attr) or []
          setattr(draft, attr, cls._unique(current + [str(x) for x in extra])[:30])
          draft.source = "hybrid"
      if match.get("summary") and (not draft.summary or len(draft.summary) < 40):
        draft.summary = str(match["summary"])[:1000]
        draft.source = "hybrid"

    merged["analysis_mode"] = "hybrid"
    provenance = dict(merged.get("provenance") or {})
    provenance["ai_inferred"] = cls._unique(list(provenance.get("ai_inferred") or []) + ai_inferred)
    provenance["unsupported_or_unclear"] = ai_data.get("unsupported_or_unclear") or []
    merged["provenance"] = provenance
    return drafts, merged
