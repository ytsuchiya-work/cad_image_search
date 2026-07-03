import { useEffect, useState } from 'react'
import ResultCard from './ResultCard.jsx'

export default function Gallery({ onZoom }) {
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
    <div>
      {error && <div className="error-box">{error}</div>}

      {searchTarget && (
        <div className="analysis-box">
          <div className="result-header">
            <strong>「{searchTarget.filename}」に類似する画像</strong>
            <button className="ghost" onClick={() => { setSearchTarget(null); setResults(null) }}>
              閉じる
            </button>
          </div>
          {searching && <p className="status-line"><span className="spinner" /> 検索中...</p>}
          {results && (
            <div className="grid" style={{ marginTop: 12 }}>
              {results.length === 0 && <p className="status-line">類似する画像が見つかりませんでした。</p>}
              {results.map((r) => (
                <ResultCard key={r.image_id} image={r} score={r.score} onZoom={onZoom} />
              ))}
            </div>
          )}
        </div>
      )}

      <div className="section-title">登録済み画像 ({images.length}件)</div>
      <div className="grid">
        {images.map((img) => (
          <ResultCard key={img.image_id} image={img} onFindSimilar={findSimilar} onZoom={onZoom} />
        ))}
      </div>
      {images.length === 0 && (
        <p className="status-line">
          登録済みの画像がありません。README記載の /api/admin/reindex を実行してください。
        </p>
      )}
    </div>
  )
}
