"""FastAPI application for document parsing with text extraction and translation."""
from pathlib import Path
import uuid
from dataclasses import dataclass

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from services.pdf_extractor import extract_text
from services.rag_service import (
    answer_question,
    index_document,
    prepare_rag_directories,
    reset_rag_store,
    retrieve_chunks,
)
from services.translator import translate_text, SUPPORTED_LANGUAGES
from services.summarizer import summarize_text
from config import get_settings

app = FastAPI(
    title="Document Parsing API",
    description="Upload PDF, extract text, and translate to target language",
    version="1.0.0",
)

settings = get_settings()
UPLOADS_DIR = Path(__file__).parent / "uploads"
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://127.0.0.1:3000", "http://127.0.0.1:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ExtractedTextResponse(BaseModel):
    document_id: str
    filename: str
    extracted_text: str
    extraction_method: str
    rag_ready: bool
    rag_chunk_count: int
    rag_error: str | None = None


class TranslateRequest(BaseModel):
    text: str
    target_language: str
    document_id: str | None = None


class TranslateResponse(BaseModel):
    target_language: str
    translated_text: str
    document_id: str | None = None


class LanguagesResponse(BaseModel):
    languages: dict[str, str]


class SummarizeRequest(BaseModel):
    text: str
    document_id: str | None = None


class SummarizeResponse(BaseModel):
    summary: str
    document_id: str | None = None


class DocumentResponse(BaseModel):
    id: str
    filename: str
    extraction_method: str
    extracted_text: str
    translated_language: str | None
    translated_text: str | None
    summary_text: str | None
    rag_ready: bool
    rag_chunk_count: int
    rag_error: str | None = None


class QuestionAnswerRequest(BaseModel):
    document_id: str
    question: str


class QuestionAnswerResponse(BaseModel):
    document_id: str
    question: str
    answer: str
    retrieved_chunks: list[str]


@dataclass
class Document:
    id: str
    filename: str
    content_type: str | None
    file_bytes: bytes
    extraction_method: str
    extracted_text: str
    translated_language: str | None = None
    translated_text: str | None = None
    summary_text: str | None = None
    rag_ready: bool = False
    rag_chunk_count: int = 0
    rag_error: str | None = None


# Simple in-memory document store (resets on app restart).
document_store: dict[str, Document] = {}


def validate_pdf(file: UploadFile) -> None:
    """Validate that uploaded file is PDF. Raises HTTPException if not."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    ext = Path(file.filename).suffix.lower()
    if ext != ".pdf":
        raise HTTPException(status_code=400, detail="Upload .pdf file only")


def fetch_doc_or_404(document_id: str) -> Document:
    doc = document_store.get(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@app.get("/")
def root():
    return {"message": "Document Parsing API", "docs": "/docs"}


@app.on_event("startup")
def _startup() -> None:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    prepare_rag_directories()
    reset_rag_store()
    document_store.clear()


@app.get("/api/languages", response_model=LanguagesResponse)
def get_languages():
    """Return supported target languages for translation."""
    # Keep a small set of common choices at the top for UX, then include the rest.
    preferred_order = [
        "en",  # English
        "hi",  # Hindi
        # Indian languages
        "bn",  # Bengali
        "kn",  # Kannada
        "te",  # Telugu
        "ta",  # Tamil
        "ml",  # Malayalam
        "mr",  # Marathi
        "gu",  # Gujarati
        "pa",  # Punjabi
        "ur",  # Urdu
        "as",  # Assamese
        "ne",  # Nepali
    ]

    languages: dict[str, str] = {}
    for code in preferred_order:
        name = SUPPORTED_LANGUAGES.get(code)
        if name:
            languages[code] = name

    for code, name in SUPPORTED_LANGUAGES.items():
        if code not in languages:
            languages[code] = name

    return LanguagesResponse(languages=languages)


@app.post("/api/upload", response_model=ExtractedTextResponse)
async def upload_pdf(file: UploadFile = File(...)):
    """
    Upload a PDF file. Validates file type, extracts text using PyMuPDF/PyPDF2
    for text-based PDFs or PaddleOCR for image-based PDFs.
    """
    validate_pdf(file)

    content = await file.read()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=400,
            detail="add a .pdf file less than 10MB.",
        )

    extracted_text, extraction_method = extract_text(content, file.filename)

    doc = Document(
        id=str(uuid.uuid4()),
        filename=file.filename,
        content_type=file.content_type,
        file_bytes=content,
        extracted_text=extracted_text,
        extraction_method=extraction_method,
    )
    # Persist the uploaded PDF to disk for easy access.
    safe_name = Path(file.filename).name  # strip any path info
    file_path = UPLOADS_DIR / f"{doc.id}_{safe_name}"
    with open(file_path, "wb") as f:
        f.write(content)

    try:
        doc.rag_chunk_count = index_document(doc.id, doc.filename, extracted_text)
        doc.rag_ready = doc.rag_chunk_count > 0
        if not doc.rag_ready:
            doc.rag_error = "The PDF did not contain enough extracted text to build a RAG index."
    except Exception as exc:
        doc.rag_ready = False
        doc.rag_chunk_count = 0
        doc.rag_error = str(exc)

    document_store[doc.id] = doc

    return ExtractedTextResponse(
        document_id=doc.id,
        filename=file.filename,
        extracted_text=extracted_text,
        extraction_method=extraction_method,
        rag_ready=doc.rag_ready,
        rag_chunk_count=doc.rag_chunk_count,
        rag_error=doc.rag_error,
    )


@app.post("/api/translate", response_model=TranslateResponse)
async def translate_endpoint(body: TranslateRequest):
    """Translate text to the target language."""
    if body.target_language not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported language. Supported: {list(SUPPORTED_LANGUAGES.keys())}",
        )

    text = body.text
    if (not text or not text.strip()) and body.document_id:
        doc = fetch_doc_or_404(body.document_id)
        text = doc.extracted_text

    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="No text to translate")

    translated_text = translate_text(text, body.target_language)

    if body.document_id:
        doc = fetch_doc_or_404(body.document_id)
        doc.translated_language = body.target_language
        doc.translated_text = translated_text
        document_store[doc.id] = doc

    return TranslateResponse(
        target_language=body.target_language,
        translated_text=translated_text,
        document_id=body.document_id,
    )


@app.post("/api/summarize", response_model=SummarizeResponse)
async def summarize_endpoint(body: SummarizeRequest):
    """Summarize text using an LLM."""
    text = body.text
    if (not text or not text.strip()) and body.document_id:
        doc = fetch_doc_or_404(body.document_id)
        text = doc.extracted_text

    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="No text to summarize")

    try:
        summary = summarize_text(text)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        msg = str(e) if str(e) else "Summarization failed. Check GROQ_API_KEY and try again."
        raise HTTPException(status_code=502, detail=msg)

    if body.document_id:
        doc = fetch_doc_or_404(body.document_id)
        doc.summary_text = summary
        document_store[doc.id] = doc

    return SummarizeResponse(summary=summary, document_id=body.document_id)


@app.get("/api/documents/{document_id}", response_model=DocumentResponse)
def get_document(document_id: str):
    doc = fetch_doc_or_404(document_id)
    return DocumentResponse(
        id=doc.id,
        filename=doc.filename,
        extraction_method=doc.extraction_method,
        extracted_text=doc.extracted_text,
        translated_language=doc.translated_language,
        translated_text=doc.translated_text,
        summary_text=doc.summary_text,
        rag_ready=doc.rag_ready,
        rag_chunk_count=doc.rag_chunk_count,
        rag_error=doc.rag_error,
    )


@app.post("/api/ask", response_model=QuestionAnswerResponse)
async def ask_document_question(body: QuestionAnswerRequest):
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    doc = fetch_doc_or_404(body.document_id)
    if not doc.rag_ready:
        if doc.extracted_text.strip():
            try:
                doc.rag_chunk_count = index_document(doc.id, doc.filename, doc.extracted_text)
                doc.rag_ready = doc.rag_chunk_count > 0
                doc.rag_error = None if doc.rag_ready else "No searchable chunks were created for this PDF."
            except Exception as exc:
                doc.rag_error = str(exc)
        if not doc.rag_ready:
            raise HTTPException(
                status_code=503,
                detail=doc.rag_error or "This PDF is not ready for question answering yet.",
            )

    chunks = retrieve_chunks(doc.id, question)
    try:
        answer = answer_question(question, chunks)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        detail = str(exc) if str(exc) else "Question answering failed. Check GROQ_API_KEY and try again."
        raise HTTPException(status_code=502, detail=detail)

    return QuestionAnswerResponse(
        document_id=doc.id,
        question=question,
        answer=answer,
        retrieved_chunks=[str(chunk["text"]) for chunk in chunks],
    )
