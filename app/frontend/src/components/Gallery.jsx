import { useEffect, useMemo, useState } from 'react'
import ResultCard from './ResultCard.jsx'

function parseTags(image) {
  return (image.tags || '').split(',').map((t) => t.trim()).filter(Boolean)
}

export default function Gallery({ onShowDetail }) {
  const [images, setImages] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const [selectedTags, setSelectedTags] = useState([])

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

  const allTags = useMemo(() => {
    const set = new Set()
    images.forEach((img) => parseTags(img).forEach((t) => set.add(t)))
    return [...set].sort((a, b) => a.localeCompare(b, 'ja'))
  }, [images])

  const filteredImages = useMemo(() => {
    if (selectedTags.length === 0) return images
    return images.filter((img) => {
      const imgTags = parseTags(img)
      return selectedTags.every((t) => imgTags.includes(t))
    })
  }, [images, selectedTags])

  function toggleTag(tag) {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]
    )
  }

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

        {allTags.length > 0 && (
          <div className="filter-bar">
            <div className="filter-bar-header">
              <span className="filter-bar-title">タグで絞り込み</span>
              {selectedTags.length > 0 && (
                <button className="ghost" onClick={() => setSelectedTags([])}>
                  フィルタを解除
                </button>
              )}
            </div>
            <div className="tag-chips">
              {allTags.map((tag) => (
                <button
                  key={tag}
                  className={selectedTags.includes(tag) ? 'tag-chip tag-chip-filter active' : 'tag-chip tag-chip-filter'}
                  onClick={() => toggleTag(tag)}
                >
                  {tag}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="section-title">
          登録済み画像 ({filteredImages.length}{selectedTags.length > 0 ? ` / ${images.length}` : ''}件)
        </div>
        <div className="grid">
          {filteredImages.map((img) => (
            <ResultCard key={img.image_id} image={img} onFindSimilar={findSimilar} onShowDetail={onShowDetail} />
          ))}
        </div>
        {images.length === 0 && (
          <p className="status-line">
            登録済みの画像がありません。README記載の /api/admin/reindex を実行してください。
          </p>
        )}
        {images.length > 0 && filteredImages.length === 0 && (
          <p className="status-line">選択したタグに一致する画像がありません。</p>
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
