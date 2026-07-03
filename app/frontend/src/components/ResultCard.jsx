export default function ResultCard({ image, onFindSimilar, onShowDetail, score, vertical }) {
  const tags = (image.tags || '').split(',').map((t) => t.trim()).filter(Boolean)
  const thumbUrl = image.image_id ? `/api/image/${image.image_id}/file` : null

  return (
    <div className={vertical ? 'card card-horizontal' : 'card'}>
      <div className="thumb-wrap" onClick={() => onShowDetail && onShowDetail(image, score)}>
        {thumbUrl ? (
          <img className="thumb" src={thumbUrl} alt={image.filename} />
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
        <div className="card-actions">
          <button className="ghost" onClick={() => onShowDetail && onShowDetail(image, score)}>
            詳細を確認
          </button>
          {onFindSimilar && (
            <button className="ghost" onClick={() => onFindSimilar(image)}>
              類似画像を検索
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
