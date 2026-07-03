import { useRef, useState } from 'react'
import ResultCard from './ResultCard.jsx'

export default function UploadPanel({ onShowDetail }) {
  const inputRef = useRef(null)
  const [file, setFile] = useState(null)
  const [previewUrl, setPreviewUrl] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [analysis, setAnalysis] = useState(null)
  const [results, setResults] = useState(null)

  function handleFile(f) {
    if (!f) return
    setFile(f)
    setPreviewUrl(URL.createObjectURL(f))
    setAnalysis(null)
    setResults(null)
    setError(null)
  }

  async function runSearch() {
    if (!file) return
    setLoading(true)
    setError(null)
    setAnalysis(null)
    setResults(null)

    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 90_000)
    try {
      const form = new FormData()
      form.append('file', file)
      const resp = await fetch('/api/search/upload', { method: 'POST', body: form, signal: controller.signal })
      if (!resp.ok) throw new Error(await resp.text())
      const data = await resp.json()
      setAnalysis(data.analysis)
      setResults(data.results || [])
    } catch (e) {
      if (e.name === 'AbortError') {
        setError('画像の解析がタイムアウトしました。画像サイズを小さくするか、もう一度お試しください。')
      } else if (e instanceof TypeError) {
        setError('通信エラーが発生しました（ネットワーク切断、またはサーバー側のタイムアウトの可能性があります）。もう一度お試しください。')
      } else {
        setError(String(e))
      }
    } finally {
      clearTimeout(timeoutId)
      setLoading(false)
    }
  }

  return (
    <div className="layout-with-sidebar">
      <div className="main-column">
        <label
          className="dropzone"
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault()
            handleFile(e.dataTransfer.files?.[0])
          }}
        >
          <input
            ref={inputRef}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            onChange={(e) => handleFile(e.target.files?.[0])}
          />
          <div>クリック または ドラッグ&amp;ドロップ で画像を選択</div>
          <div className="muted">{file ? file.name : '未選択（PNG/JPEG/WEBP, 15MBまで）'}</div>
        </label>

        {previewUrl && <img className="preview" src={previewUrl} alt="preview" />}

        <div>
          <button className="primary" disabled={!file || loading} onClick={runSearch}>
            {loading ? '解析・検索中...' : 'この画像で検索'}
          </button>
        </div>

        {error && <div className="error-box">{error}</div>}

        {analysis && (
          <div className="analysis-box">
            <strong>Geminiによる解析結果</strong>
            <div className="tag-chips" style={{ margin: '8px 0' }}>
              {analysis.tags.map((t) => (
                <span className="tag-chip" key={t}>{t}</span>
              ))}
            </div>
            <p style={{ margin: 0 }}>{analysis.description}</p>
          </div>
        )}
      </div>

      {results && (
        <aside className="results-sidebar">
          <div className="result-header">
            <strong>類似画像 ({results.length}件)</strong>
          </div>
          <div className="sidebar-list">
            {results.length === 0 && <p className="status-line">類似する画像が見つかりませんでした。</p>}
            {results.map((r) => (
              <ResultCard key={r.image_id} image={r} score={r.score} onShowDetail={onShowDetail} vertical />
            ))}
          </div>
        </aside>
      )}
    </div>
  )
}
