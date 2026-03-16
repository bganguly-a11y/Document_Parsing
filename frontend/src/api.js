const API_BASE = '/api'

async function request(url, options = {}) {
  const headers = { ...(options.headers || {}) }
  if (options.body && typeof options.body === 'string') {
    headers['Content-Type'] = 'application/json'
  }
  const res = await fetch(`${API_BASE}${url}`, {
    ...options,
    headers,
  })
  if (!res.ok) {
    const err = new Error(res.statusText)
    err.response = res
    const text = await res.text()
    try {
      err.response.data = JSON.parse(text)
    } catch {
      err.response.data = { detail: text }
    }
    throw err
  }
  return res.json()
}

export async function getLanguages() {
  return request('/languages')
}

export async function uploadPdf(file) {
  const formData = new FormData()
  formData.append('file', file)
  const res = await fetch(`${API_BASE}/upload`, {
    method: 'POST',
    body: formData,
  })
  if (!res.ok) {
    const err = new Error(res.statusText)
    err.response = res
    const text = await res.text()
    try {
      err.response.data = JSON.parse(text)
    } catch {
      err.response.data = { detail: text }
    }
    throw err
  }
  return res.json()
}

export async function translate(text, targetLang, documentId = null) {
  return request('/translate', {
    method: 'POST',
    body: JSON.stringify({
      text,
      target_language: targetLang,
      document_id: documentId,
    }),
  })
}

export async function summarize(text, documentId = null) {
  return request('/summarize', {
    method: 'POST',
    body: JSON.stringify({
      text,
      document_id: documentId,
    }),
  })
}
