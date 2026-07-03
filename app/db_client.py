"""Databricks SQL warehouse / UC Volume / Vector Search クライアント."""
from __future__ import annotations

import io
import logging
import os
import time

import requests
from databricks.sdk import WorkspaceClient
from databricks import sql as dbsql

logger = logging.getLogger(__name__)

CATALOG = os.environ.get("CATALOG", "classic_stable_ytcy_catalog")
SCHEMA = os.environ.get("SCHEMA", "cad_image_search")
VOLUME = os.environ.get("VOLUME", "cad_image")
WAREHOUSE_ID = os.environ.get("DATABRICKS_WAREHOUSE_ID", "e351c2d1b16eae95")
VS_ENDPOINT = os.environ.get("VS_ENDPOINT_NAME", "cad-image-search-endpoint")
VS_INDEX = os.environ.get(
    "VS_INDEX_NAME", f"{CATALOG}.{SCHEMA}.cad_image_index"
)
VS_EMBEDDING_MODEL = os.environ.get("EMBEDDING_ENDPOINT", "databricks-gte-large-en")

T_IMAGES = f"{CATALOG}.{SCHEMA}.cad_images"
VOLUME_ROOT = f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME}"


class DBClient:
    def __init__(self):
        self.w = WorkspaceClient()
        self.host = self.w.config.host.rstrip("/")

    def _conn(self):
        token = self.w.config.authenticate()["Authorization"].split(" ", 1)[1]
        return dbsql.connect(
            server_hostname=self.host.replace("https://", ""),
            http_path=f"/sql/1.0/warehouses/{WAREHOUSE_ID}",
            access_token=token,
        )

    def exec(self, statement: str, params=None) -> None:
        with self._conn() as c, c.cursor() as cur:
            if params is None:
                cur.execute(statement)
            else:
                cur.execute(statement, parameters=params)

    def query(self, statement: str, params=None) -> list[dict]:
        with self._conn() as c, c.cursor() as cur:
            if params is None:
                cur.execute(statement)
            else:
                cur.execute(statement, parameters=params)
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in rows]

    # ── UC Volume file IO (SDK Files API) ──
    def list_volume_files(self) -> list[str]:
        return [
            e.name for e in self.w.files.list_directory_contents(VOLUME_ROOT)
            if e.name and not e.is_directory
        ]

    def download_from_volume(self, filename: str) -> bytes:
        resp = self.w.files.download(file_path=f"{VOLUME_ROOT}/{filename}")
        return resp.contents.read()

    def upload_to_volume(self, filename: str, content: bytes) -> None:
        self.w.files.upload(file_path=f"{VOLUME_ROOT}/{filename}", contents=io.BytesIO(content), overwrite=False)

    def _auth(self) -> dict:
        return self.w.config.authenticate()

    # ── Vector Search ──
    def trigger_sync(self) -> dict:
        url = f"{self.host}/api/2.0/vector-search/indexes/{VS_INDEX}/sync"
        h = self._auth(); h["Content-Type"] = "application/json"
        r = requests.post(url, headers=h, timeout=30)
        return {"status": r.status_code, "body": r.text[:400]}

    def index_status(self) -> dict:
        url = f"{self.host}/api/2.0/vector-search/indexes/{VS_INDEX}"
        r = requests.get(url, headers=self._auth(), timeout=30)
        return r.json()

    def wait_until_ready(self, timeout_sec: int = 300) -> None:
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            info = self.index_status()
            if info.get("status", {}).get("ready"):
                return
            time.sleep(5)
        logger.warning("vector search index not ready after %ss", timeout_sec)

    def search(self, query_text: str, num_results: int = 10) -> list[dict]:
        url = f"{self.host}/api/2.0/vector-search/indexes/{VS_INDEX}/query"
        h = self._auth(); h["Content-Type"] = "application/json"
        body = {
            "query_text": query_text,
            "columns": ["image_id", "filename", "tags", "description"],
            "num_results": num_results,
        }
        r = requests.post(url, headers=h, json=body, timeout=30)
        r.raise_for_status()
        data = r.json()
        result_cols = [c["name"] for c in data["manifest"]["columns"]]
        rows = data.get("result", {}).get("data_array", []) or []
        return [dict(zip(result_cols, row)) for row in rows]
