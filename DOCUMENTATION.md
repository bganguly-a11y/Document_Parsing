# Document Parsing Application — Documentation

## Overview

The Document Parsing application allows users to upload PDF files, extract text from them, and translate the extracted text into a target language. The system automatically chooses the appropriate extraction method based on whether the PDF contains embedded text or scanned images.

---

## Architecture

```
┌─────────────────┐     ┌──────────────────┐
│  React Frontend │────▶│  FastAPI Backend │
│  (Port 3000)    │     │  (Port 8000)     │
└─────────────────┘     └──────────────────┘
         │                         │
         │                         ├── PyMuPDF / PyPDF2 (text-based PDFs)
         │                         └── PaddleOCR (image/scanned PDFs)
         │                         ├── deep-translator (translation)
         │                         └── Groq LLM (summarization)
```

---

## Features

### 1. File Upload & Validation
- **Client-side**: Only `.pdf` files can be selected. Non-PDF selections show: *"Upload .pdf file only"*.
- **Server-side**: Uploaded files are validated again. Invalid types receive a 400 response with the same message.

### 2. Text Extraction
The backend automatically selects the extraction method:

| PDF Type           | Condition                              | Extraction Method |
|--------------------|----------------------------------------|-------------------|
| Text-based PDF     | Extracted text length ≥ 50 characters  | **PyMuPDF**       |
| Image/scanned PDF  | Extracted text length &lt; 50 characters | **PaddleOCR** (OCR) |
| Fallback           | OCR fails                              | **PyPDF2**        |

### 3. Translation
- User selects a target language from the dropdown.
- Translation is performed via the **deep-translator** library (Google Translate backend).
- Long texts are split into chunks to respect API limits (~2000 chars per request).

### Supported Languages
The app loads a large list of supported languages from Google Translate via `deep-translator` (including many Indian languages like Bengali, Kannada, Telugu, Tamil, Malayalam, Marathi, Gujarati, Punjabi, Assamese, Urdu, Nepali, etc.).

### 4. Summarization
- User clicks the **Summary** button after extracting text.
- The extracted text is sent to an LLM (Groq / Llama 3.1) to generate a concise summary.
- The summary is displayed on the frontend.

---

## Project Structure

```
Parsing_Document_Application/
├── backend/
│   ├── main.py              # FastAPI app, routes
│   ├── config.py            # Settings (OCR, upload limits, etc.)
│   ├── requirements.txt
│   ├── .env.example
│   └── services/
│       ├── pdf_extractor.py # PDF text extraction logic
│       ├── translator.py    # Translation service
│       └── summarizer.py    # LLM summarization (Groq)
├── frontend/
│   ├── src/
│   │   ├── App.jsx          # Main UI component
│   │   ├── App.css
│   │   ├── api.js           # API client
│   │   ├── main.jsx
│   │   └── index.css
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
└── DOCUMENTATION.md         # This file
```

---

## Setup & Installation

### Prerequisites
- Python 3.11+
- Node.js 18+
- **PaddleOCR** (required for image-based/scanned PDFs; downloads models on first use)

#### Install PaddleOCR (backend dependency)
PaddleOCR is installed via `pip install -r requirements.txt`. On first OCR run it may download model files and can take a minute.

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create `.env`:

```env
# OCR (PaddleOCR)
PADDLEOCR_LANG=en

# Optional: where PaddleX/PaddleOCR stores models/cache.
# If unset, the backend uses `backend/.cache/paddlex`.
PADDLE_PDX_CACHE_HOME=

# Optional: skip connectivity check of model hosters (recommended in restricted networks).
PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=true
GROQ_API_KEY=your-groq-api-key     # Required for summarization; get free key at https://console.groq.com
```

Run the backend:

```bash
uvicorn main:app --reload --port 8000

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at http://localhost:3000 and proxies `/api` to the backend.

---

## API Reference

### `GET /api/languages`
Returns supported target languages.

**Response:**
```json
{
  "languages": {
    "en": "English",
    "es": "Spanish",
    ...
  }
}
```

### `POST /api/upload`
Upload a PDF and extract text.

**Request:** `multipart/form-data` with `file` (PDF only)

**Response:**
```json
{
  "filename": "sample.pdf",
  "extracted_text": "...",
  "extraction_method": "pymupdf"
}
```

**Errors:**
- `400`: Non-PDF file → `"Upload .pdf file only"`
- `400`: File too large

### `POST /api/translate`
Translate text to the target language.

**Request body:**
```json
{
  "text": "Text to translate",
  "target_language": "es"
}
```

**Response:**
```json
{
  "target_language": "es",
  "translated_text": "..."
}
```

### `POST /api/summarize`
Summarize text using an LLM (Groq / Llama 3.1).

**Request body:**
```json
{
  "text": "Text to summarize"
}
```

**Response:**
```json
{
  "summary": "Concise summary of the text..."
}
```

**Errors:**
- `400`: No text to summarize
- `503`: GROQ_API_KEY not set or LLM error

---

## Deployment Notes

1. **CORS**: Update `allow_origins` in `main.py` with your frontend URL.
2. **PaddleOCR models/cache**: Ensure the server can write to `PADDLE_PDX_CACHE_HOME` (or let it default to `backend/.cache/paddlex`) so model downloads and caching work.
3. **Groq API Key**: Set `GROQ_API_KEY` in `.env` for summarization (free tier at https://console.groq.com).
4. **Translation**: For heavy production use, consider a paid API (DeepL, Google Cloud Translation).

---

## License

MIT
