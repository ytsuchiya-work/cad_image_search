export default function ResultCard({ image, onFindSimilar, onZoom, score }) {
  const tags = (image.tags || '').split(',').map((t) => t.trim()).filter(Boolean)
  const thumbUrl = image.image_id ? `/api/image/${image.image_id}/file` : null

  return (
    <div className="card">
      <div className="thumb-wrap">
        {thumbUrl ? (
          <img
            className="thumb"
            src={thumbUrl}
            alt={image.filename}
            onClick={() => onZoom && onZoom(thumbUrl)}
          />
        ) : (
          <div className="thumb" />
        )}
        {typeof score === 'number' && (
          <span className="score-badge">類似度 {(score * 100).toFixed(1)}%</span>
        )}
      </div>
      <div className="card-body">
        <div className="filename">{image.filename}</div>
        <div className="tag-chips">
          {tags.map((t) => (
            <span className="tag-chip" key={t}>{t}</span>
          ))}
        </div>
        <div className="description">{image.description}</div>
        {onFindSimilar && (
          <button className="ghost" onClick={() => onFindSimilar(image)}>
            この画像に類似する画像を検索
          </button>
        )}
      </div>
    </div>
  )
}
