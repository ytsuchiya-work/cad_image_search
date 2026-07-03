import { useEffect, useState } from 'react'
import ResultCard from './ResultCard.jsx'

export default function Gallery({ onShowDetail }) {
  const [images, setImages] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const [searchTarget, setSearchTarget] = useState(null)
  const [searching, setSearching] = useState(false)
  const [results, setResults] = useState(null)

  useEffect(() => {
    fetch('/api/images')
      .then((r) => r.json())
      .then((data) => setImages(data.images || []))
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false))
  }, [])

  async function findSimilar(image) {
    setSearchTarget(image)
    setSearching(true)
    setResults(null)
    setError(null)
    try {
      const resp = await fetch(`/api/search/similar/${encodeURIComponent(image.image_id)}`, {
        method: 'POST',
      })
      if (!resp.ok) throw new Error(await resp.text())
      const data = await resp.json()
      setResults(data.results || [])
    } catch (e) {
      setError(String(e))
    } finally {
      setSearching(false)
    }
  }

  if (loading) return <p className="status-line">読み込み中...</p>

  return (
    <div className="layout-with-sidebar">
      <div className="main-column">
        {error && <div className="error-box">{error}</div>}
        <div className="section-title">登録済み画像 ({images.length}件)</div>
        <div className="grid">
          {images.map((img) => (
            <ResultCard key={img.image_id} image={img} onFindSimilar={findSimilar} onShowDetail={onShowDetail} />
          ))}
        </div>
        {images.length === 0 && (
          <p className="status-line">
            登録済みの画像がありません。README記載の /api/admin/reindex を実行してください。
          </p>
        )}
      </div>

      {searchTarget && (
        <aside className="results-sidebar">
          <div className="result-header">
            <strong>類似画像</strong>
            <button className="ghost" onClick={() => { setSearchTarget(null); setResults(null) }}>
              閉じる
            </button>
          </div>
          <div className="status-line" style={{ marginBottom: 8 }}>
            起点: {searchTarget.filename}
          </div>
          {searching && <p className="status-line"><span className="spinner" /> 検索中...</p>}
          <div className="sidebar-list">
            {results && results.length === 0 && <p className="status-line">類似する画像が見つかりませんでした。</p>}
            {results && results.map((r) => (
              <ResultCard key={r.image_id} image={r} score={r.score} onShowDetail={onShowDetail} vertical />
            ))}
          </div>
        </aside>
      )}
    </div>
  )
}
