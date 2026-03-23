"""Traditional RAG pipeline helpers for PDF question answering."""

from __future__ import annotations

import os
import re
import shutil
import uuid
from collections import Counter
from functools import lru_cache
from pathlib import Path

try:
    from groq import Groq
except ImportError:  # pragma: no cover - handled at runtime
    Groq = None  # type: ignore[assignment]

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import FieldCondition, Filter, MatchValue
except ImportError:  # pragma: no cover - handled at runtime
    QdrantClient = None  # type: ignore[assignment]
    FieldCondition = Filter = MatchValue = None  # type: ignore[assignment]

from config import get_settings

settings = get_settings()
BASE_DIR = Path(__file__).resolve().parents[1]
VECTOR_DB_DIR = (
    Path(settings.rag_vector_db_path).expanduser().resolve()
    if settings.rag_vector_db_path
    else (BASE_DIR / ".cache" / "qdrant")
)
EMBED_CACHE_DIR = (
    Path(settings.rag_embedding_cache_dir).expanduser().resolve()
    if settings.rag_embedding_cache_dir
    else (BASE_DIR / ".cache" / "fastembed")
)
MAX_CONTEXT_CHARS = 10_000
TOKEN_PATTERN = re.compile(r"\b\w+\b")
FALLBACK_INDEX: dict[str, list[dict[str, object]]] = {}


def prepare_rag_directories() -> None:
    """Create local cache directories used by the embedded vector store."""
    VECTOR_DB_DIR.mkdir(parents=True, exist_ok=True)
    EMBED_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def reset_rag_store() -> None:
    """Clear the local vector store so it stays in sync with the in-memory app state."""
    FALLBACK_INDEX.clear()
    if VECTOR_DB_DIR.exists():
        shutil.rmtree(VECTOR_DB_DIR, ignore_errors=True)
    VECTOR_DB_DIR.mkdir(parents=True, exist_ok=True)
    get_qdrant_client.cache_clear()


@lru_cache(maxsize=1)
def get_qdrant_client():
    """Return a local Qdrant client configured with a free embedding model."""
    if QdrantClient is None:
        raise RuntimeError("qdrant-client is not installed in the current environment.")
    prepare_rag_directories()
    os.environ.setdefault("FASTEMBED_CACHE_PATH", str(EMBED_CACHE_DIR))
    client = QdrantClient(path=str(VECTOR_DB_DIR))
    client.set_model(
        settings.rag_embedding_model,
        cache_dir=str(EMBED_CACHE_DIR),
        threads=1,
    )
    return client


def split_text_into_chunks(text: str) -> list[str]:
    """Split extracted document text into overlapping word chunks."""
    words = text.split()
    if not words:
        return []

    chunk_size = max(settings.rag_chunk_size_words, 50)
    overlap = min(settings.rag_chunk_overlap_words, chunk_size - 1)
    step = max(chunk_size - overlap, 1)

    chunks: list[str] = []
    for start in range(0, len(words), step):
        piece = " ".join(words[start:start + chunk_size]).strip()
        if len(piece) >= settings.rag_min_chunk_chars:
            chunks.append(piece)
        if start + chunk_size >= len(words):
            break

    if not chunks:
        whole_text = text.strip()
        return [whole_text] if whole_text else []

    return chunks


def _tokenize(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text.lower())


def _store_fallback_chunks(document_id: str, filename: str, chunks: list[str]) -> None:
    FALLBACK_INDEX[document_id] = [
        {
            "text": chunk,
            "chunk_index": idx,
            "filename": filename,
            "tokens": Counter(_tokenize(chunk)),
        }
        for idx, chunk in enumerate(chunks)
    ]


def _retrieve_fallback_chunks(document_id: str, question: str) -> list[dict[str, object]]:
    question_tokens = Counter(_tokenize(question))
    if not question_tokens:
        return []

    chunks = FALLBACK_INDEX.get(document_id, [])
    scored: list[dict[str, object]] = []
    for chunk in chunks:
        chunk_tokens = chunk["tokens"]
        overlap = sum(min(question_tokens[token], chunk_tokens.get(token, 0)) for token in question_tokens)
        if overlap <= 0:
            continue
        score = overlap / max(sum(question_tokens.values()), 1)
        scored.append(
            {
                "text": chunk["text"],
                "score": round(score, 4),
                "chunk_index": chunk["chunk_index"],
            }
        )

    scored.sort(key=lambda item: (-float(item["score"]), int(item["chunk_index"])))
    return scored[:settings.rag_top_k]


def index_document(document_id: str, filename: str, text: str) -> int:
    """Embed document chunks and store them in the local vector database."""
    chunks = split_text_into_chunks(text)
    if not chunks:
        return 0

    _store_fallback_chunks(document_id, filename, chunks)

    metadata = [
        {
            "document_id": document_id,
            "filename": filename,
            "chunk_index": idx,
        }
        for idx in range(len(chunks))
    ]
    ids = [str(uuid.uuid5(uuid.NAMESPACE_URL, f"{document_id}:{idx}")) for idx in range(len(chunks))]
    try:
        client = get_qdrant_client()
        client.add(
            collection_name=settings.rag_collection_name,
            documents=chunks,
            metadata=metadata,
            ids=ids,
        )
    except Exception:
        return len(chunks)
    return len(chunks)


def retrieve_chunks(document_id: str, question: str) -> list[dict[str, object]]:
    """Run similarity search over the current document's indexed chunks."""
    try:
        client = get_qdrant_client()
        matches = client.query(
            collection_name=settings.rag_collection_name,
            query_text=question,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match=MatchValue(value=document_id),
                    )
                ]
            ),
            limit=settings.rag_top_k,
        )
    except Exception:
        return _retrieve_fallback_chunks(document_id, question)

    retrieved: list[dict[str, object]] = []
    for match in matches:
        metadata = match.metadata or {}
        text = (match.document or "").strip()
        if not text:
            continue
        retrieved.append(
            {
                "text": text,
                "score": round(float(match.score or 0.0), 4),
                "chunk_index": metadata.get("chunk_index"),
            }
        )

    if retrieved:
        return retrieved

    return _retrieve_fallback_chunks(document_id, question)


def _get_groq_client():
    if Groq is None:
        raise RuntimeError("groq package not installed. Run: pip install groq")

    api_key = settings.groq_api_key or os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY not set. Add it to backend/.env or your deployment environment."
        )
    return Groq(api_key=api_key)


def answer_question(question: str, context_chunks: list[dict[str, object]]) -> str:
    """Answer a question using only retrieved document context."""
    if not context_chunks:
        return "I could not find enough relevant information in this PDF to answer that question."

    context_sections: list[str] = []
    current_length = 0
    for idx, chunk in enumerate(context_chunks, start=1):
        text = str(chunk["text"]).strip()
        section = f"[Chunk {idx}] {text}"
        if current_length + len(section) > MAX_CONTEXT_CHARS:
            break
        context_sections.append(section)
        current_length += len(section)

    context = "\n\n".join(context_sections)
    client = _get_groq_client()
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        temperature=0.2,
        max_tokens=220,
        messages=[
            {
                "role": "system",
                "content": (
                    "You answer questions using only the provided PDF context. "
                    "Respond as one short paragraph. "
                    "If the answer is not supported by the context, say that clearly."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Question: {question}\n\n"
                    f"Context:\n{context}\n\n"
                    "Write a concise grounded answer."
                ),
            },
        ],
    )

    if not response.choices:
        raise RuntimeError("No response from the LLM. Please try again.")

    return (response.choices[0].message.content or "").strip()
