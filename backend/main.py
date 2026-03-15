"""FastAPI application for document parsing with text extraction and translation."""
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from services.pdf_extractor import extract_text
from services.translator import translate_text, SUPPORTED_LANGUAGES
from services.summarizer import summarize_text
from config import get_settings

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
    filename: str
    extracted_text: str
    extraction_method: str


class TranslateRequest(BaseModel):
    text: str
    target_language: str


class TranslateResponse(BaseModel):
    target_language: str
    translated_text: str


class LanguagesResponse(BaseModel):
    languages: dict[str, str]


class SummarizeRequest(BaseModel):
    text: str


class SummarizeResponse(BaseModel):
    summary: str


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


@app.get("/api/languages", response_model=LanguagesResponse)
def get_languages():
    """Return supported target languages for translation."""
    return LanguagesResponse(languages=SUPPORTED_LANGUAGES)


@app.post("/api/upload", response_model=ExtractedTextResponse)
async def upload_pdf(file: UploadFile = File(...)):
    """
    Upload a PDF file. Validates file type, extracts text using PyMuPDF/PyPDF2
    for text-based PDFs or pytesseract for image-based PDFs.
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

    return ExtractedTextResponse(
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

    if not body.text or not body.text.strip():
        raise HTTPException(status_code=400, detail="No text to translate")

    translated_text = translate_text(body.text, body.target_language)

    return TranslateResponse(
        target_language=body.target_language,
        translated_text=translated_text,
    )


@app.post("/api/summarize", response_model=SummarizeResponse)
async def summarize_endpoint(body: SummarizeRequest):
    """Summarize text using an LLM."""
    if not body.text or not body.text.strip():
        raise HTTPException(status_code=400, detail="No text to summarize")

    try:
        summary = summarize_text(body.text)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        msg = str(e) if str(e) else "Summarization failed. Check GROQ_API_KEY and try again."
        raise HTTPException(status_code=502, detail=msg)

    return SummarizeResponse(summary=summary)
