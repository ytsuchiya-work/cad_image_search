export default function DetailModal({ image, score, onClose }) {
  if (!image) return null
  const tags = (image.tags || '').split(',').map((t) => t.trim()).filter(Boolean)
  const thumbUrl = image.image_id ? `/api/image/${image.image_id}/file` : null

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="detail-modal" onClick={(e) => e.stopPropagation()}>
        <button className="ghost detail-modal-close" onClick={onClose}>閉じる</button>
        {thumbUrl && <img className="detail-modal-image" src={thumbUrl} alt={image.filename} />}
        <div className="detail-modal-body">
          <div className="result-header">
            <strong>{image.filename}</strong>
            {typeof score === 'number' && (
              <span className="tag-chip">類似度 {(score * 100).toFixed(1)}%</span>
            )}
          </div>
          <div className="tag-chips" style={{ margin: '8px 0' }}>
            {tags.map((t) => (
              <span className="tag-chip" key={t}>{t}</span>
            ))}
          </div>
          <p style={{ margin: 0 }}>{image.description}</p>
        </div>
      </div>
    </div>
  )
}
