"""FastAPI backend for CAD Image Search.

責務:
  1. GET  /api/images              登録済み画像の一覧（ギャラリー表示用）
  2. GET  /api/image/{id}/file     Volumeから画像バイトを配信（サムネイル/拡大表示）
  3. POST /api/search/similar/{id} 登録済み画像を起点にした類似画像検索
  4. POST /api/search/upload       アップロード画像をGeminiで解析→類似検索（保存はしない）
  5. POST /api/gallery/add         アップロード画像をユーザーの選択でギャラリーに追加保存
  6. POST /api/admin/reindex       Volume内の未登録画像をGeminiで解析→登録→Vector Search同期
"""
from __future__ import annotations

import logging
import mimetypes
import re
import traceback
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from db_client import DBClient, T_IMAGES, VOLUME_ROOT
from image_analysis import GEMINI_ENDPOINT, GeminiAnalysisError, ImageAnalyzer, build_embedding_text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("cad_image_search")

app = FastAPI(title="CAD Image Search")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # フロントエンドは常にJSONを期待するため、想定外の例外もJSONで返す
    # (素の500 "Internal Server Error" テキストだとフロントのJSON.parseが壊れる)
    logger.exception("unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": f"{type(exc).__name__}: {exc}"})

db = DBClient()
analyzer = ImageAnalyzer()

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MAX_UPLOAD_BYTES = 15 * 1024 * 1024


def _slugify(name: str) -> str:
    stem = Path(name).stem
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", stem).strip("-").lower()
    return slug or uuid.uuid4().hex[:12]


def _make_unique(candidate: str, existing: set[str], suffix_sep: str = "-") -> str:
    """candidate が existing と衝突する場合、短いサフィックスを付けて一意にする."""
    if candidate not in existing:
        return candidate
    stem = Path(candidate).stem
    ext = Path(candidate).suffix
    for _ in range(20):
        attempt = f"{stem}{suffix_sep}{uuid.uuid4().hex[:6]}{ext}"
        if attempt not in existing:
            return attempt
    return f"{stem}{suffix_sep}{uuid.uuid4().hex}{ext}"


# ── 1) Gallery listing ──────────────────────────────────────────────────────

@app.get("/api/images")
async def list_images():
    rows = db.query(
        f"SELECT image_id, filename, tags, description, created_at "
        f"FROM {T_IMAGES} ORDER BY created_at DESC"
    )
    for r in rows:
        if r.get("created_at") is not None:
            r["created_at"] = str(r["created_at"])
    return {"images": rows}


# ── 2) Serve image bytes from Volume ────────────────────────────────────────

@app.get("/api/image/{image_id}/file")
async def get_image_file(image_id: str):
    rows = db.query(
        f"SELECT filename FROM {T_IMAGES} WHERE image_id = ?", params=(image_id,)
    )
    if not rows:
        raise HTTPException(404, f"image not found: {image_id}")
    filename = rows[0]["filename"]
    content = db.download_from_volume(filename)
    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return StreamingResponse(iter([content]), media_type=media_type)


# ── 3) Similar-image search from an already-indexed image ──────────────────

@app.post("/api/search/similar/{image_id}")
async def search_similar(image_id: str, num_results: int = 6):
    rows = db.query(
        f"SELECT image_id, filename, tags, description, embedding_text "
        f"FROM {T_IMAGES} WHERE image_id = ?",
        params=(image_id,),
    )
    if not rows:
        raise HTTPException(404, f"image not found: {image_id}")
    source = rows[0]

    try:
        raw_results = db.search(source["embedding_text"], num_results=num_results + 1)
    except Exception as e:
        logger.exception("vector search failed")
        raise HTTPException(500, str(e))

    results = [r for r in raw_results if r.get("image_id") != image_id][:num_results]
    return {"query_image": source, "results": results}


# ── 4) Upload-based search (ephemeral — not persisted) ──────────────────────

@app.post("/api/search/upload")
async def search_upload(file: UploadFile = File(...), num_results: int = 6):
    if not file.filename:
        raise HTTPException(400, "filename is empty")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"unsupported file type: {suffix}")

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "file too large (max 15MB)")

    mime_type = mimetypes.guess_type(file.filename)[0] or "image/png"
    try:
        analysis = analyzer.analyze(content, mime_type=mime_type)
    except GeminiAnalysisError as e:
        raise HTTPException(502, str(e))

    embedding_text = build_embedding_text(analysis["tags"], analysis["description"])
    try:
        results = db.search(embedding_text, num_results=num_results)
    except Exception as e:
        logger.exception("vector search failed")
        raise HTTPException(500, str(e))

    return {"analysis": analysis, "results": results}


# ── 5) User opt-in: persist an uploaded image into the gallery ─────────────

@app.post("/api/gallery/add")
async def add_to_gallery(
    file: UploadFile = File(...),
    tags: str = Form(...),
    description: str = Form(...),
):
    """アップロード検索で表示した解析結果を、ユーザーの選択でギャラリーに永続化する.
    再度Geminiを呼ばず、アップロード検索時に得た tags/description をそのまま使う。"""
    if not file.filename:
        raise HTTPException(400, "filename is empty")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"unsupported file type: {suffix}")

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "file too large (max 15MB)")

    existing_files = set(db.list_volume_files())
    filename = _make_unique(file.filename, existing_files)

    existing_ids = {r["image_id"] for r in db.query(f"SELECT image_id FROM {T_IMAGES}")}
    image_id = _make_unique(_slugify(filename), existing_ids)

    tags_list = [t.strip() for t in tags.split(",") if t.strip()]
    embedding_text = build_embedding_text(tags_list, description)

    db.upload_to_volume(filename, content)
    db.exec(
        f"""INSERT INTO {T_IMAGES}
              (image_id, filename, volume_path, tags, description, embedding_text, created_at)
            VALUES (?, ?, ?, ?, ?, ?, current_timestamp())""",
        params=(
            image_id, filename, f"{VOLUME_ROOT}/{filename}",
            ", ".join(tags_list), description, embedding_text,
        ),
    )
    sync_result = db.trigger_sync()

    return {"image_id": image_id, "filename": filename, "sync": sync_result}


# ── 6) Admin: seed / re-index images already in the Volume ─────────────────

@app.post("/api/admin/reindex")
async def reindex():
    existing = {
        r["filename"] for r in db.query(f"SELECT filename FROM {T_IMAGES}")
    }
    all_files = [
        f for f in db.list_volume_files()
        if Path(f).suffix.lower() in ALLOWED_EXTENSIONS
    ]
    todo = [f for f in all_files if f not in existing]

    processed = []
    errors = []
    for filename in todo:
        try:
            content = db.download_from_volume(filename)
            mime_type = mimetypes.guess_type(filename)[0] or "image/png"
            analysis = analyzer.analyze(content, mime_type=mime_type)
            embedding_text = build_embedding_text(analysis["tags"], analysis["description"])
            image_id = _slugify(filename)
            db.exec(
                f"""INSERT INTO {T_IMAGES}
                      (image_id, filename, volume_path, tags, description, embedding_text, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, current_timestamp())""",
                params=(
                    image_id, filename, f"{VOLUME_ROOT}/{filename}",
                    ", ".join(analysis["tags"]), analysis["description"], embedding_text,
                ),
            )
            processed.append({"filename": filename, "image_id": image_id})
        except Exception as e:
            logger.exception("failed to process %s", filename)
            errors.append({"filename": filename, "error": str(e), "trace": traceback.format_exc()[:500]})

    sync_result = None
    if processed:
        sync_result = db.trigger_sync()

    return {
        "found_in_volume": len(all_files),
        "already_indexed": len(existing),
        "newly_processed": processed,
        "errors": errors,
        "sync": sync_result,
    }


# ── misc ─────────────────────────────────────────────────────────────────────

@app.get("/api/index/status")
async def index_status():
    s = db.index_status()
    return {
        "name": s.get("name"),
        "ready": s.get("status", {}).get("ready"),
        "detailed_state": s.get("status", {}).get("detailed_state"),
        "indexed_row_count": s.get("status", {}).get("indexed_row_count"),
        "message": s.get("status", {}).get("message"),
    }


@app.get("/api/config")
async def get_config():
    return {
        "gemini_endpoint": GEMINI_ENDPOINT,
    }


# ── Static frontend ──────────────────────────────────────────────────────────

static_dir = str(Path(__file__).parent / "static")
if Path(static_dir).is_dir():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
