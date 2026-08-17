"""Phase 6 tests for source-grounded chunks, embeddings, and retrieval."""

from __future__ import annotations

import io
import json
import uuid

from app.extensions import db
from app.models.book_model import Book, DocumentProcessingJob
from app.models.rag_model import ChunkEmbedding, DocumentChunk
from app.services.medical_teacher.chunking_service import DocumentChunkingService
from app.services.medical_teacher.embedding_service import LocalHashEmbeddingProvider
from app.services.medical_teacher.processing_job_service import DocumentProcessingJobService


def test_rag_models_keep_vectors_out_of_public_serializers():
  chunk = DocumentChunk(
    public_id="chunk-public-id",
    user_id=1,
    book_id=1,
    chunk_index=0,
    content="Alveoli exchange oxygen and carbon dioxide.",
    content_hash="a" * 64,
    char_count=44,
    word_count=7,
    page_start=2,
    page_end=2,
    source_json={"source_kind": "uploaded_document", "page_numbers": [2]},
  )
  embedding = ChunkEmbedding(provider="local_hash", model="test", dimension=3, vector_json=[1, 0, 0])

  assert chunk.to_dict()["source"]["page_numbers"] == [2]
  assert "embedding" not in chunk.to_dict()
  assert "vector_json" not in embedding.metadata_dict()


def test_local_embeddings_are_deterministic_and_rank_shared_terms():
  provider = LocalHashEmbeddingProvider("test-hash", 256)
  first, repeated, unrelated = provider.embed_texts([
    "mitochondria produce cellular ATP energy",
    "mitochondria produce cellular ATP energy",
    "renal filtration occurs in the glomerulus",
  ])

  assert first == repeated
  assert len(first) == 256
  assert sum(left * right for left, right in zip(first, repeated)) > sum(
    left * right for left, right in zip(first, unrelated)
  )


def test_chunk_split_preserves_configured_overlap():
  text = " ".join(f"token-{index}" for index in range(300))
  pieces = DocumentChunkingService._split(text, size=400, overlap=80)

  assert len(pieces) > 1
  assert any(word in pieces[1] for word in pieces[0].split()[-8:])
  assert all(len(piece) <= 400 for piece in pieces)


def test_rag_routes_require_authentication(client):
  assert client.post("/api/medical-teacher/books/1/index").status_code == 401
  assert client.get("/api/medical-teacher/books/1/index").status_code == 401
  assert client.post("/api/medical-teacher/books/1/search", json={"query": "heart"}).status_code == 401


def test_pipeline_indexes_and_searches_owned_source_passages(client, auth_headers, app):
  marker = uuid.uuid4().hex
  content = (
    "MODULE 1: Cellular Medicine\n"
    "CHAPTER 1: Cell Biology\n"
    "1.1 Mitochondrial Function\n"
    "Mitochondria generate adenosine triphosphate ATP through oxidative phosphorylation.\n"
    f"This cellular energy passage has source marker {marker}.\n"
    "1.2 Renal Filtration\n"
    "The renal glomerulus filters plasma before tubular reabsorption.\n"
  ).encode()
  uploaded = client.post(
    "/api/medical-teacher/books/upload-and-process",
    data={"files": (io.BytesIO(content), f"phase6-{marker}.txt")},
    headers=auth_headers,
    content_type="multipart/form-data",
  )
  assert uploaded.status_code == 202
  item = uploaded.get_json()["data"]["items"][0]
  book_id = item["book"]["id"]
  job_id = item["job"]["id"]
  chunk_ids: list[int] = []

  try:
    with app.app_context():
      job = DocumentProcessingJob.query.filter_by(public_id=job_id).first()
      assert job is not None
      job.status = "processing"
      job.stage = "starting"
      job.lease_token = uuid.uuid4().hex
      job.attempts = 1
      db.session.commit()
      completed = DocumentProcessingJobService.process_claimed(job)

      assert completed.status == "succeeded"
      assert completed.result_json["rag_ready"] is True
      assert completed.result_json["chunk_count"] >= 2
      assert completed.result_json["embedding_provider"] == "local_hash"
      book = db.session.get(Book, book_id)
      assert book is not None
      assert book.rag_status == "ready"
      chunks = DocumentChunk.query.filter_by(book_id=book_id).order_by(DocumentChunk.chunk_index).all()
      chunk_ids = [chunk.id for chunk in chunks]
      assert chunks
      assert all(chunk.source_json["document_id"] == book_id for chunk in chunks)
      assert all(chunk.source_json["page_numbers"] == [1] for chunk in chunks)
      assert ChunkEmbedding.query.filter(ChunkEmbedding.chunk_id.in_(chunk_ids)).count() == len(chunks)

    status = client.get(f"/api/medical-teacher/books/{book_id}/index", headers=auth_headers)
    assert status.status_code == 200
    assert status.get_json()["data"]["status"] == "ready"

    reused = client.post(
      f"/api/medical-teacher/books/{book_id}/index",
      json={"force": False},
      headers=auth_headers,
    )
    assert reused.status_code == 200
    assert reused.get_json()["data"]["reused"] is True

    searched = client.post(
      f"/api/medical-teacher/books/{book_id}/search",
      json={"query": "mitochondria ATP cellular energy", "limit": 5},
      headers=auth_headers,
    )
    assert searched.status_code == 200
    payload = searched.get_json()["data"]
    assert payload["grounding"]["answer_generated"] is False
    assert payload["matches"]
    assert any(marker in match["chunk"]["content"] for match in payload["matches"])
    assert payload["matches"][0]["chunk"]["source"]["page_numbers"] == [1]
    assert "vector_json" not in json.dumps(payload)

    invalid = client.post(
      f"/api/medical-teacher/books/{book_id}/search",
      json={"query": ""},
      headers=auth_headers,
    )
    assert invalid.status_code == 400
  finally:
    client.delete(f"/api/medical-teacher/books/{book_id}", headers=auth_headers)
    if chunk_ids:
      with app.app_context():
        assert DocumentChunk.query.filter(DocumentChunk.id.in_(chunk_ids)).count() == 0
        assert ChunkEmbedding.query.filter(ChunkEmbedding.chunk_id.in_(chunk_ids)).count() == 0
