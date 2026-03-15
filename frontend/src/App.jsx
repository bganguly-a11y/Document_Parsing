import { useState, useEffect } from 'react'
import { uploadPdf, translate, summarize, getLanguages } from './api'
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

  useEffect(() => {
    getLanguages().then((data) => setLanguages(data.languages)).catch(() => {})
  }, [])

  const handleFileChange = (e) => {
    const chosen = e.target.files?.[0]
    setFileError('')
    setExtracted(null)
    setTranslated(null)
    setSummary(null)

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
      const data = await translate(extracted.extracted_text, targetLang)
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
      const data = await summarize(extracted.extracted_text)
      setSummary(data)
    } catch (e) {
      const msg = e.response?.data?.detail || e.message || 'Summarization failed'
      setFileError(typeof msg === 'string' ? msg : JSON.stringify(msg))
    } finally {
      setSummaryLoading(false)
    }
  }

  return (
    <div className="app">
      <header className="header">
        <h1>Document Parsing</h1>
        <p>Upload a PDF to extract text and translate to your preferred language</p>
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
