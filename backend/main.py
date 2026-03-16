"""FastAPI application for document parsing with text extraction and translation."""
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from services.pdf_extractor import extract_text
from services.translator import translate_text, SUPPORTED_LANGUAGES
from services.summarizer import summarize_text
from config import get_settings
from db import get_db, engine
from models import Base, Document

app = FastAPI(
    title="Document Parsing API",
    description="Upload PDF, extract text, and translate to target language",
    version="1.0.0",
)

settings = get_settings()
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


def validate_pdf(file: UploadFile) -> None:
    """Validate that uploaded file is PDF. Raises HTTPException if not."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    ext = Path(file.filename).suffix.lower()
    if ext != ".pdf":
        raise HTTPException(status_code=400, detail="Upload .pdf file only")


@app.get("/")
def root():
    return {"message": "Document Parsing API", "docs": "/docs"}


@app.on_event("startup")
def _startup() -> None:
    # Simple, migration-free setup for local development.
    Base.metadata.create_all(bind=engine)


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

    with get_db() as db:
        doc = Document(
            filename=file.filename,
            content_type=file.content_type,
            file_bytes=content,
            extracted_text=extracted_text,
            extraction_method=extraction_method,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

    return ExtractedTextResponse(
        document_id=doc.id,
        filename=file.filename,
        extracted_text=extracted_text,
        extraction_method=extraction_method,
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
        with get_db() as db:
            doc = db.get(Document, body.document_id)
            if not doc:
                raise HTTPException(status_code=404, detail="Document not found")
            text = doc.extracted_text

    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="No text to translate")

    translated_text = translate_text(text, body.target_language)

    if body.document_id:
        with get_db() as db:
            doc = db.get(Document, body.document_id)
            if not doc:
                raise HTTPException(status_code=404, detail="Document not found")
            doc.translated_language = body.target_language
            doc.translated_text = translated_text
            db.add(doc)
            db.commit()

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
        with get_db() as db:
            doc = db.get(Document, body.document_id)
            if not doc:
                raise HTTPException(status_code=404, detail="Document not found")
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
        with get_db() as db:
            doc = db.get(Document, body.document_id)
            if not doc:
                raise HTTPException(status_code=404, detail="Document not found")
            doc.summary_text = summary
            db.add(doc)
            db.commit()

    return SummarizeResponse(summary=summary, document_id=body.document_id)


@app.get("/api/documents/{document_id}", response_model=DocumentResponse)
def get_document(document_id: str):
    with get_db() as db:
        doc = db.get(Document, document_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        return DocumentResponse(
            id=doc.id,
            filename=doc.filename,
            extraction_method=doc.extraction_method,
            extracted_text=doc.extracted_text,
            translated_language=doc.translated_language,
            translated_text=doc.translated_text,
            summary_text=doc.summary_text,
        )
