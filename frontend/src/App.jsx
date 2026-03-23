import { useState, useEffect } from 'react'
import { uploadPdf, translate, summarize, getLanguages, askQuestion } from './api'
import './App.css'

function App() {
  const [file, setFile] = useState(null)
  const [fileError, setFileError] = useState('')
  const [extracted, setExtracted] = useState(null)
  const [translated, setTranslated] = useState(null)
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(false)
  const [targetLang, setTargetLang] = useState('en')
  const [languages, setLanguages] = useState({})
  const [translateLoading, setTranslateLoading] = useState(false)
  const [summaryLoading, setSummaryLoading] = useState(false)
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState(null)
  const [askLoading, setAskLoading] = useState(false)

  useEffect(() => {
    getLanguages().then((data) => setLanguages(data.languages)).catch(() => {})
  }, [])

  const handleFileChange = (e) => {
    const chosen = e.target.files?.[0]
    setFileError('')
    setExtracted(null)
    setTranslated(null)
    setSummary(null)
    setQuestion('')
    setAnswer(null)

    if (!chosen) {
      setFile(null)
      return
    }

    const ext = chosen.name.slice(chosen.name.lastIndexOf('.')).toLowerCase()
    if (ext !== '.pdf') {
      setFileError('Upload .pdf file only')
      setFile(null)
      e.target.value = ''
      return
    }

    const MAX_SIZE = 10 * 1024 * 1024 // 10MB
    if (chosen.size > MAX_SIZE) {
      setFileError('add a .pdf file less than 10MB.')
      setFile(null)
      e.target.value = ''
      return
    }

    setFile(chosen)
  }

  const handleUpload = async () => {
    if (!file) return
    setLoading(true)
    setFileError('')
    setExtracted(null)
    setTranslated(null)
    setSummary(null)
    setQuestion('')
    setAnswer(null)
    try {
      const data = await uploadPdf(file)
      setExtracted(data)
    } catch (e) {
      const msg = e.response?.data?.detail || e.message || 'Upload failed'
      setFileError(typeof msg === 'string' ? msg : JSON.stringify(msg))
    } finally {
      setLoading(false)
    }
  }

  const handleTranslate = async () => {
    if (!extracted) return
    setTranslateLoading(true)
    setTranslated(null)
    try {
      const data = await translate(extracted.extracted_text, targetLang, extracted.document_id)
      setTranslated(data)
    } catch (e) {
      const msg = e.response?.data?.detail || e.message || 'Translation failed'
      setFileError(typeof msg === 'string' ? msg : JSON.stringify(msg))
    } finally {
      setTranslateLoading(false)
    }
  }

  const handleSummarize = async () => {
    if (!extracted) return
    setSummaryLoading(true)
    setSummary(null)
    setFileError('')
    try {
      const data = await summarize(extracted.extracted_text, extracted.document_id)
      setSummary(data)
    } catch (e) {
      const msg = e.response?.data?.detail || e.message || 'Summarization failed'
      setFileError(typeof msg === 'string' ? msg : JSON.stringify(msg))
    } finally {
      setSummaryLoading(false)
    }
  }

  const handleAskQuestion = async () => {
    if (!extracted || !question.trim()) return
    setAskLoading(true)
    setAnswer(null)
    setFileError('')
    try {
      const data = await askQuestion(extracted.document_id, question.trim())
      setAnswer(data)
    } catch (e) {
      const msg = e.response?.data?.detail || e.message || 'Question answering failed'
      setFileError(typeof msg === 'string' ? msg : JSON.stringify(msg))
    } finally {
      setAskLoading(false)
    }
  }

  return (
    <div className="app">
      <header className="header">
        <h1>Document Parsing</h1>
        <p>Upload a PDF to extract text, translate, summarize, and ask grounded questions</p>
      </header>

      <main className="main">
        <section className="upload-section">
          <div className="upload-area">
            <input
              type="file"
              id="file-input"
              accept=".pdf,application/pdf"
              onChange={handleFileChange}
              className="file-input"
            />
            <label htmlFor="file-input" className="upload-label">
              <span className="upload-icon">📄</span>
              <span>Choose PDF file</span>
              {file && <span className="file-name">{file.name}</span>}
            </label>
          </div>

          {fileError && (
            <div className="error-msg">{fileError}</div>
          )}

          <button
            className="btn btn-primary"
            onClick={handleUpload}
            disabled={!file || loading}
          >
            {loading ? 'Extracting…' : 'Extract Text'}
          </button>
        </section>

        {extracted && (
          <section className="content-section">
            <div className="card">
              <h2>Extracted Text</h2>
              <span className="badge">{extracted.extraction_method}</span>
              <span className={`badge ${extracted.rag_ready ? 'badge-success' : 'badge-muted'}`}>
                {extracted.rag_ready ? `RAG ready • ${extracted.rag_chunk_count} chunks` : 'RAG unavailable'}
              </span>
              <div className="text-box extracted">{extracted.extracted_text}</div>
            </div>

            <div className="action-controls">
              <button
                className="btn btn-secondary"
                onClick={handleSummarize}
                disabled={summaryLoading}
              >
                {summaryLoading ? 'Summarizing…' : 'Summary'}
              </button>
              <select
                value={targetLang}
                onChange={(e) => setTargetLang(e.target.value)}
                className="lang-select"
              >
                {Object.entries(languages).length === 0 && (
                  <option value="en">Loading…</option>
                )}
                {Object.entries(languages).map(([code, name]) => (
                  <option key={code} value={code}>{name}</option>
                ))}
              </select>
              <button
                className="btn btn-secondary"
                onClick={handleTranslate}
                disabled={translateLoading}
              >
                {translateLoading ? 'Translating…' : 'Translate'}
              </button>
            </div>

            <div className="card">
              <h2>Ask Questions About This PDF</h2>
              <p className="card-copy">
                Ask a question and the application will retrieve the most relevant document chunks before generating an answer.
              </p>
              {!extracted.rag_ready && extracted.rag_error && (
                <div className="hint-msg">{extracted.rag_error}</div>
              )}
              <textarea
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                className="question-input"
                // placeholder="Example: What are the key obligations mentioned in this document?"
                rows={4}
              />
              <button
                className="btn btn-secondary"
                onClick={handleAskQuestion}
                disabled={!question.trim() || askLoading || !extracted.rag_ready}
              >
                {askLoading ? 'Searching and answering…' : 'Ask PDF'}
              </button>
            </div>

            {answer && (
              <div className="card">
                <h2>RAG Answer</h2>
                <div className="text-box summary">{answer.answer}</div>
                {answer.retrieved_chunks?.length > 0 && (
                  <div className="rag-context">
                    <h3>Retrieved Context</h3>
                    {answer.retrieved_chunks.map((chunk, index) => (
                      <div key={`${index}-${chunk.slice(0, 24)}`} className="context-snippet">
                        {chunk}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {summary && (
              <div className="card">
                <h2>Summary</h2>
                <div className="text-box summary">{summary.summary}</div>
              </div>
            )}

            {translated && (
              <div className="card">
                <h2>Translated Text ({translated.target_language})</h2>
                <div className="text-box translated">{translated.translated_text}</div>
              </div>
            )}
          </section>
        )}
      </main>
    </div>
  )
}

export default App
