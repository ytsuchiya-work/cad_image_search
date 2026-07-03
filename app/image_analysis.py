"""Databricks FMAPI Gemini による CAD 画像解析.

画像 1 枚から検索用のタグと詳細説明を生成する。
アップロード検索・初期データ投入 (reindex) の両方から同じロジックを呼び出すことで、
「アップロード画像も既存画像と同様にテキスト化する」という要件をコードレベルで保証する。
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re

import requests
from databricks.sdk import WorkspaceClient

logger = logging.getLogger(__name__)

GEMINI_ENDPOINT = os.environ.get("GEMINI_ENDPOINT", "databricks-gemini-2-5-flash")

_PROMPT = """あなたはCAD/CAE図面を分類する専門家です。この画像を分析し、必ず次のJSON 1つだけで応答してください。
- Markdownコードフェンス禁止。JSON以外の文字を含めないこと。
- description の中にJSONを入れ子で書かないこと。

{
  "tags": ["2D図面 または 3D図面", "配色 (ダークテーマ/ライトテーマ)", "図面の種類 (部品図/組立図/概観図 など)", "その他特徴的なタグ"],
  "description": "画像に写っている内容を具体的に説明する日本語2-4文。図面の種別、視点・構図、配色、描かれている部品や構造、線の密度や表現の特徴などを含めること。"
}
"""


class GeminiAnalysisError(RuntimeError):
    pass


class ImageAnalyzer:
    def __init__(self):
        self.w = WorkspaceClient()
        self.host = self.w.config.host.rstrip("/")

    def _headers(self) -> dict:
        h = self.w.config.authenticate()
        h["Content-Type"] = "application/json"
        return h

    def analyze(self, image_bytes: bytes, mime_type: str = "image/png") -> dict:
        """画像バイト列を Gemini に渡し、{"tags": [...], "description": "..."} を返す."""
        b64 = base64.b64encode(image_bytes).decode()
        content = [
            {"type": "text", "text": _PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}},
        ]

        url = f"{self.host}/serving-endpoints/{GEMINI_ENDPOINT}/invocations"
        body = {
            "messages": [{"role": "user", "content": content}],
            "max_tokens": 2048,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        resp = requests.post(url, headers=self._headers(), json=body, timeout=90)
        if resp.status_code != 200:
            raise GeminiAnalysisError(f"Gemini error {resp.status_code}: {resp.text[:500]}")

        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        result = self._parse_json(text)

        tags = result.get("tags") or []
        if not isinstance(tags, list):
            tags = [str(tags)]
        description = str(result.get("description") or "").strip()
        return {"tags": [str(t).strip() for t in tags if str(t).strip()], "description": description}

    @staticmethod
    def _parse_json(text: str) -> dict:
        """Gemini出力から安全にJSONを抽出する（コードフェンス混入等に対応）."""
        text = text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
            text = text.strip()
        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                try:
                    result = json.loads(text[start:end + 1])
                except Exception:
                    logger.warning("Gemini output was not valid JSON: %s", text[:300])
                    return {"tags": [], "description": text[:500]}
            else:
                logger.warning("Gemini output was not valid JSON: %s", text[:300])
                return {"tags": [], "description": text[:500]}

        # Gemini が {"description": "{...}"} のように1段ネストして返すことがあるためアンラップする
        # (max_tokens 制限でネストしたJSONが途中で切れて壊れているケースは正規表現で救済する)
        if isinstance(result, dict):
            desc = result.get("description", "")
            if isinstance(desc, str) and desc.lstrip().startswith("{"):
                try:
                    inner = json.loads(desc)
                    if isinstance(inner, dict) and any(k in inner for k in ("tags", "description")):
                        return inner
                except Exception:
                    tags_m = re.search(r'"tags"\s*:\s*\[(.*?)\]', desc, re.DOTALL)
                    desc_m = re.search(r'"description"\s*:\s*"((?:[^"\\]|\\.)*)', desc, re.DOTALL)
                    if tags_m or desc_m:
                        tags = re.findall(r'"((?:[^"\\]|\\.)*)"', tags_m.group(1)) if tags_m else []
                        inner_desc = desc_m.group(1) if desc_m else ""
                        return {"tags": tags, "description": inner_desc}
        return result


def build_embedding_text(tags: list[str], description: str) -> str:
    """タグ+説明からVector Searchの埋め込みソーステキストを組み立てる（登録時/検索時で共通利用）."""
    tags_text = ", ".join(tags)
    return f"タグ: {tags_text}\n説明: {description}"[:8000]
