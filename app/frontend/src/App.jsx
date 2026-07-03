import { useState } from 'react'
import Gallery from './components/Gallery.jsx'
import UploadPanel from './components/UploadPanel.jsx'
import DetailModal from './components/DetailModal.jsx'

export default function App() {
  const [tab, setTab] = useState('gallery')
  const [detail, setDetail] = useState(null) // { image, score }

  function showDetail(image, score) {
    setDetail({ image, score })
  }

  return (
    <>
      <header className="app-header">
        <div>
          <h1>CAD画像検索デモ</h1>
          <div className="subtitle">FMAPI Gemini + Vector Search による類似図面検索</div>
        </div>
      </header>

      <nav className="tabs">
        <button className={tab === 'gallery' ? 'active' : ''} onClick={() => setTab('gallery')}>
          ギャラリーから検索
        </button>
        <button className={tab === 'upload' ? 'active' : ''} onClick={() => setTab('upload')}>
          画像をアップロードして検索
        </button>
      </nav>

      <main>
        {tab === 'gallery' && <Gallery onShowDetail={showDetail} />}
        {tab === 'upload' && <UploadPanel onShowDetail={showDetail} />}
      </main>

      {detail && (
        <DetailModal image={detail.image} score={detail.score} onClose={() => setDetail(null)} />
      )}
    </>
  )
}
