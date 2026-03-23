# Document Parsing Application Documentation

## Overview

This application lets users upload PDF files, extract text, translate the extracted content, summarize it, and ask grounded questions about the uploaded document using a traditional Retrieval-Augmented Generation (RAG) pipeline.

The current stack is:

- Frontend: React + Vite
- Backend: FastAPI + Python
- PDF extraction: PyMuPDF, PyPDF2, PaddleOCR
- Translation: `deep-translator`
- Summarization and question answering: Groq LLM
- Embeddings: `BAAI/bge-small-en`
- Vector database: embedded Qdrant local mode with FastEmbed

Only PDF files are allowed, and file size is limited to 10 MB.

---

## Architecture

```text
┌─────────────────┐     ┌──────────────────┐
│  React Frontend │────▶│  FastAPI Backend │
│  (Vite / Vercel)│     │ (Render / Local) │
└─────────────────┘     └──────────────────┘
         │                         │
         │                         ├── PyMuPDF / PyPDF2
         │                         ├── PaddleOCR
         │                         ├── deep-translator
         │                         ├── Groq LLM
         │                         ├── FastEmbed
         │                         └── Qdrant local vector store
```

### High-level flow

1. User uploads a PDF from the frontend.
2. Backend validates the file type and size.
3. Backend extracts text from the PDF.
4. Backend stores the uploaded file in `backend/uploads/`.
5. Backend chunks the extracted text.
6. Backend generates embeddings for the chunks.
7. Backend stores chunk embeddings in embedded Qdrant.
8. User can then:
   - translate the extracted text,
   - summarize the extracted text,
   - ask questions about the PDF.
9. For question answering, the backend:
   - embeds the question,
   - retrieves similar chunks from Qdrant,
   - sends question + retrieved context to the LLM,
   - returns a short grounded answer.

---

## Features

### 1. PDF upload and validation

- Only `.pdf` files are accepted.
- Maximum file size is 10 MB.
- Validation happens on both frontend and backend.
- Uploaded files are saved into `backend/uploads/`.

### 2. Text extraction

The backend automatically chooses the extraction strategy:

| PDF type | Condition | Extraction method |
|---|---|---|
| Text-based PDF | extracted text length >= 50 chars | `PyMuPDF` |
| Image/scanned PDF | extracted text length < 50 chars | `PaddleOCR` |
| OCR fallback failure | OCR throws error | `PyPDF2` |

### 3. Translation

- Translation is handled by `deep-translator`.
- The user selects the target language from the frontend dropdown.
- Existing translation functionality remains unchanged.

### 4. Summarization

- Summarization is handled through Groq.
- The backend sends extracted text to the LLM and returns a concise single-paragraph summary.
- Existing summarization functionality remains unchanged.

### 5. RAG-based question answering

After a PDF is uploaded:

- extracted text is split into overlapping chunks,
- embeddings are generated using `BAAI/bge-small-en`,
- embeddings are stored in embedded Qdrant,
- users can ask questions about that specific PDF,
- the backend retrieves the most relevant chunks,
- the LLM answers using only the retrieved context.

The response is designed to be a short, grounded paragraph.

---

## Why Qdrant for vector storage

The project uses Qdrant local mode instead of FAISS, Pinecone, or ChromaDB because it gives a strong balance of simplicity and production readiness.

- `Qdrant local mode` runs inside the app without another hosted service.
- It supports metadata filtering, which is useful for restricting retrieval to a single uploaded document.
- It has a smooth upgrade path to a managed Qdrant deployment later.
- It is free for the current deployment model.

For this project, Qdrant is a better fit than:

- `FAISS`: very fast, but lower-level and requires more manual work around metadata and filtering.
- `Pinecone`: managed and convenient, but adds external cost and service dependency.
- `ChromaDB`: reasonable option, but Qdrant offers a cleaner path to future scale and stronger retrieval semantics.

---

## Project structure

```text
Parsing_Document_Application/
├── backend/
│   ├── main.py
│   ├── config.py
│   ├── requirements.txt
│   ├── runtime.txt
│   ├── uploads/
│   └── services/
│       ├── pdf_extractor.py
│       ├── translator.py
│       ├── summarizer.py
│       └── rag_service.py
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── App.css
│   │   ├── api.js
│   │   ├── main.jsx
│   │   └── index.css
│   ├── index.html
│   ├── package.json
│   ├── package-lock.json
│   ├── vite.config.js
│   └── vercel.json
├── README.md
└── DOCUMENTATION.md
```

---

## Backend setup

### Prerequisites

- Python 3.11+
- Groq API key for summarization and RAG answers
- PaddleOCR model download access on first OCR run

### Install

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Environment variables

Create `backend/.env`:

```env
PADDLEOCR_LANG=en
PADDLE_PDX_CACHE_HOME=
PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=true
GROQ_API_KEY=your-groq-api-key

# Optional RAG tuning
RAG_EMBEDDING_MODEL=BAAI/bge-small-en
RAG_COLLECTION_NAME=document_chunks
RAG_CHUNK_SIZE_WORDS=220
RAG_CHUNK_OVERLAP_WORDS=40
RAG_TOP_K=4
RAG_MIN_CHUNK_CHARS=120
RAG_VECTOR_DB_PATH=
RAG_EMBEDDING_CACHE_DIR=
```

### Run backend

```bash
uvicorn main:app --reload --port 8000
```

The backend runs at `http://localhost:8000`.

---

## Frontend setup

```bash
cd frontend
npm install
npm run dev
```

The frontend runs locally through Vite and sends API calls to `/api`.

---

## API reference

### `GET /api/languages`

Returns supported languages for translation.

**Response**

```json
{
  "languages": {
    "en": "English",
    "hi": "Hindi"
  }
}
```

### `POST /api/upload`

Uploads a PDF, extracts text, stores the file, and prepares the RAG index.

**Request**

- `multipart/form-data`
- field: `file`

**Response**

```json
{
  "document_id": "8a17d36d-32f6-49c9-b1d9-d3e6596a2f11",
  "filename": "sample.pdf",
  "extracted_text": "Document text...",
  "extraction_method": "pymupdf",
  "rag_ready": true,
  "rag_chunk_count": 6,
  "rag_error": null
}
```

**Errors**

- `400`: invalid file type
- `400`: file larger than 10 MB

### `POST /api/translate`

Translates text or the uploaded document text into a target language.

**Request**

```json
{
  "text": "Text to translate",
  "target_language": "es",
  "document_id": "8a17d36d-32f6-49c9-b1d9-d3e6596a2f11"
}
```

**Response**

```json
{
  "target_language": "es",
  "translated_text": "Texto traducido",
  "document_id": "8a17d36d-32f6-49c9-b1d9-d3e6596a2f11"
}
```

### `POST /api/summarize`

Summarizes text using the LLM.

**Request**

```json
{
  "text": "Text to summarize",
  "document_id": "8a17d36d-32f6-49c9-b1d9-d3e6596a2f11"
}
```

**Response**

```json
{
  "summary": "A short summary of the document.",
  "document_id": "8a17d36d-32f6-49c9-b1d9-d3e6596a2f11"
}
```

### `POST /api/ask`

Answers a question about one uploaded PDF using the RAG pipeline.

**Request**

```json
{
  "document_id": "8a17d36d-32f6-49c9-b1d9-d3e6596a2f11",
  "question": "What are the key obligations in the document?"
}
```

**Response**

```json
{
  "document_id": "8a17d36d-32f6-49c9-b1d9-d3e6596a2f11",
  "question": "What are the key obligations in the document?",
  "answer": "The document says the vendor must maintain records for seven years and provide quarterly reporting.",
  "retrieved_chunks": [
    "Relevant chunk 1...",
    "Relevant chunk 2..."
  ]
}
```

**Errors**

- `400`: empty question
- `404`: document not found
- `503`: RAG index not ready or `GROQ_API_KEY` missing

### `GET /api/documents/{document_id}`

Returns stored document metadata plus extracted, translated, summarized, and RAG status data.

---

## Frontend behavior

After a PDF is uploaded:

- extracted text is displayed,
- user can click `Summary`,
- user can choose a language and click `Translate`,
- user can type a question in the RAG card and click `Ask PDF`.

The UI also shows:

- whether the document is `RAG ready`,
- how many chunks were indexed,
- any RAG indexing error if one occurred.

---

## Important implementation notes

### Storage model

This app does not currently use PostgreSQL anymore.

- uploaded PDFs are saved on disk in `backend/uploads/`
- document metadata is kept in memory
- RAG vectors are stored in local embedded Qdrant files under backend cache directories

Because document metadata is in memory:

- restarting the backend clears the in-memory document store
- uploaded PDF files remain on disk unless deleted
- vector data is reset on backend startup to stay aligned with the in-memory state

### RAG chunking

The text chunker uses:

- chunk size: 220 words
- overlap: 40 words
- minimum chunk length: 120 characters

These values are configurable through environment variables.

### LLM behavior

The RAG answer prompt instructs the LLM to:

- use only the retrieved PDF context
- answer in one small concise paragraph
- say clearly when the answer is not supported by the PDF

---

## Deployment notes

### Render backend

Make sure these are true:

- `GROQ_API_KEY` is set in Render environment variables
- the backend can write to:
  - `backend/uploads/`
  - `backend/.cache/`
- the first OCR request may download PaddleOCR models
- the first RAG request may download embedding model files

### Vercel frontend

Your frontend should continue sending API requests to `/api`, and Vercel should rewrite those requests to the Render backend.

Example `vercel.json`:

```json
{
  "rewrites": [
    {
      "source": "/api/(.*)",
      "destination": "https://your-render-backend.onrender.com/api/$1"
    }
  ]
}
```

### CORS

If you directly call the backend from a different frontend origin, update `allow_origins` in `backend/main.py`.

---

## Validation summary

The current application supports:

- PDF-only upload
- maximum file size of 10 MB
- text extraction for both text and scanned PDFs
- translation
- summarization
- RAG-based question answering over uploaded PDF content

All of these features are integrated into the same upload-driven workflow.
