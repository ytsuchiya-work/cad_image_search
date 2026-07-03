# CAD画像検索デモ

Databricks FMAPIのGeminiとVector Searchを使い、CAD図面画像を「見た目の内容」でセマンティック検索できるデモです。画像そのものではなく、Geminiが生成したタグ・詳細説明のテキストをベクトル化して検索するため、キーワードやファイル名に頼らず「こういう見た目/内容の図面を探したい」という検索が可能になります。

## デモ概要

- あらかじめ登録された8枚のサンプルCAD画像（2D間取り図、3D組立図、都市デジタルツインなど）をギャラリー表示
- ギャラリーの画像をクリックして「この画像に類似する画像を検索」→ Vector Searchで距離検索し、類似度順に結果表示
- 手元の画像をアップロードして検索 → アップロード画像もGeminiで同じ手順でタグ付け・説明文生成し、同じ埋め込みモデルで検索。検索結果を見た上で、ユーザーが選択すればその画像をギャラリーに追加保存できる（選択しなければ保存されない）
- 画像追加は、UC Volumeに画像を置いて `/api/admin/reindex` を呼ぶ方法に加えて、アップロード検索後に「この画像をギャラリーに追加する」ボタンからも行える

## アーキテクチャ

```
[UC Volume: cad_image/*.png]
        │ (1) 画像を配置
        ▼
POST /api/admin/reindex ──► FMAPI Gemini（画像→タグ+詳細説明のJSON）
        │ (2) INSERT
        ▼
Deltaテーブル cad_images (tags, description, embedding_text, ...)
        │ (3) Vector Search が embedding_text を databricks-gte-large-en で自動埋め込み
        ▼
Vector Search Delta Sync Index (managed embeddings)
        │
        ├─ GET  /api/images                    → ギャラリー一覧
        ├─ POST /api/search/similar/{image_id}  → 登録済み画像を起点に類似検索
        └─ POST /api/search/upload              → アップロード画像をGeminiで解析→類似検索（保存しない）
```

### 使用技術

| レイヤ | 技術 |
|---|---|
| 画像のタグ付け・詳細説明生成 | Databricks Foundation Model API（`databricks-gemini-2-5-flash`、マルチモーダルchat completion） |
| テキスト埋め込み | Databricks Foundation Model API（`databricks-gte-large-en`） |
| ベクトル検索 | Databricks Vector Search（`DELTA_SYNC` インデックス、managed embeddings） |
| データストア | Unity Catalog Delta テーブル + UC Volume（画像原本） |
| アプリ実行基盤 | Databricks Apps |
| バックエンド | FastAPI（Python） |
| フロントエンド | React + Vite（ビルド成果物を `app/static` にコミットして配信） |

### データの格納場所

- カタログ/スキーマ: `classic_stable_ytcy_catalog.cad_image_search`
- 画像原本: Volume `classic_stable_ytcy_catalog.cad_image_search.cad_image`
- メタデータ・タグ・説明文: テーブル `classic_stable_ytcy_catalog.cad_image_search.cad_images`
- Vector Searchインデックス: `classic_stable_ytcy_catalog.cad_image_search.cad_image_index`（エンドポイント: `cad-image-search-endpoint`）

## セットアップ・デプロイ手順

前提: Databricksワークスペース（本デモは `fevm-classic-stable-ytcy`）にGemini系のFMAPIエンドポイント（`databricks-gemini-2-5-flash` 等）が有効であること。ワークスペースによってはGeminiが利用できない場合があるため、その場合は `app/app.yaml` の `GEMINI_ENDPOINT` を利用可能なマルチモーダルモデルに差し替えてください。

### 1. Unity Catalog基盤の作成

```bash
# Volume作成
databricks volumes create classic_stable_ytcy_catalog cad_image_search cad_image MANAGED

# サンプル画像をVolumeへアップロード
databricks fs cp cad_images/ dbfs:/Volumes/classic_stable_ytcy_catalog/cad_image_search/cad_image/ --recursive

# Deltaテーブル作成（CDF有効、Vector Search Delta Syncの前提条件）
# CREATE TABLE classic_stable_ytcy_catalog.cad_image_search.cad_images (
#   image_id STRING, filename STRING, volume_path STRING,
#   tags STRING, description STRING, embedding_text STRING, created_at TIMESTAMP
# ) USING DELTA TBLPROPERTIES (delta.enableChangeDataFeed = true)

# Vector Search エンドポイント + インデックス作成
databricks vector-search-endpoints create-endpoint --json '{"name": "cad-image-search-endpoint", "endpoint_type": "STANDARD"}'
databricks vector-search-indexes create-index --json '{
  "name": "classic_stable_ytcy_catalog.cad_image_search.cad_image_index",
  "endpoint_name": "cad-image-search-endpoint",
  "primary_key": "image_id",
  "index_type": "DELTA_SYNC",
  "delta_sync_index_spec": {
    "source_table": "classic_stable_ytcy_catalog.cad_image_search.cad_images",
    "pipeline_type": "TRIGGERED",
    "embedding_source_columns": [
      {"name": "embedding_text", "embedding_model_endpoint_name": "databricks-gte-large-en"}
    ]
  }
}'
```

エンドポイント作成後、インデックスが `ONLINE` になるまで数分かかります（初回はDelta Live Tablesパイプライン用のサーバーレスコンピュートが起動するため）。

### 2. フロントエンドのビルド

```bash
cd app/frontend
npm install
npm run build   # ../static に出力される（コミット対象）
```

### 3. Gitフォルダへの反映

```bash
git add -A && git commit -m "..."
git push
databricks repos update <repo_id> --branch main   # ワークスペースのGitフォルダを同期
```

### 4. Databricks Appsの作成・デプロイ

```bash
databricks apps create cad-image-search
```

**重要**: `app.yaml` に書く `resources:` セクションは無視されます。リソースはApps API/CLI（`databricks apps update <name> --json '{"resources": [...]}'`）で **アプリオブジェクトに対して直接** 登録する必要があります。`sql_warehouse`・`serving_endpoint`・`uc_securable`（TABLE/VOLUME）はこの方法で登録できますが、`vector_search_endpoint` はリソースタイプとして未対応のため、エンドポイントへの権限は別途 `databricks vector-search-endpoints update-permissions` で付与します。アプリのService Principalに対して必要な権限は以下の通りです。

- SQL Warehouse（`e351c2d1b16eae95`）: `CAN_USE`
- Serving Endpoint `databricks-gemini-2-5-flash`: `CAN_QUERY`
- Serving Endpoint `databricks-gte-large-en`: `CAN_QUERY`
- Vector Search Endpoint `cad-image-search-endpoint`: `CAN_MANAGE`（`/api/admin/reindex` からの同期トリガーに必要。エンドポイント権限は `apps update` の `resources` では設定できないため `databricks vector-search-endpoints update-permissions` で直接付与する）
- Unity Catalog: `classic_stable_ytcy_catalog` に `USE_CATALOG`、`cad_image_search` スキーマに `USE_SCHEMA`、`cad_images` テーブルに `SELECT`+`MODIFY`、`cad_image` Volumeに `READ_VOLUME`+`WRITE_VOLUME`（これらはApp resourcesの `uc_securable` として宣言可能）
- **Vector Searchインデックス自体（`cad_image_index`）にも `SELECT` を直接GRANTする必要がある。** Delta Syncインデックスは内部的にUCの別securable（テーブル扱い）として登録されており、ソーステーブルやエンドポイントへの権限とは独立してACLを持つ。これを付与し忘れると、テーブル読み取りやギャラリー表示は正常に動くのに `/api/search/similar` や `/api/search/upload` だけが `403 Forbidden` になる、という気づきにくい失敗の仕方をする。

```sql
GRANT SELECT ON TABLE classic_stable_ytcy_catalog.cad_image_search.cad_image_index TO `<app-service-principal-id>`;
```

権限付与後にデプロイします。

```bash
databricks apps deploy cad-image-search \
  --source-code-path /Workspace/Users/yusuke.tsuchiya@databricks.com/cad_image_search/app
```

### 5. 初期データ投入

デプロイ後、アプリのURLに対して1回だけ `POST /api/admin/reindex` を呼び出すと、Volume内の画像がGeminiで解析されテーブルに登録され、Vector Searchの同期がトリガーされます。

```bash
curl -X POST https://<app-url>/api/admin/reindex
```

## アプリの使い方

### ギャラリーから検索

1. 「ギャラリーから検索」タブを開くと、登録済みの画像がサムネイル・タグ・説明文付きで一覧表示されます
2. 任意の画像カードの「この画像に類似する画像を検索」を押すと、その画像を起点にVector Searchで距離検索し、類似度が高い順に結果が表示されます
3. サムネイルをクリックすると拡大表示されます

### 画像をアップロードして検索

1. 「画像をアップロードして検索」タブで画像（PNG/JPEG/WEBP、15MBまで）を選択またはドラッグ&ドロップ
2. 「この画像で検索」を押すと、Geminiがその場でタグ付け・詳細説明を生成し、結果を表示
3. 続けて同じ埋め込みモデルでVector Search検索を行い、登録済み画像から類似度の高い順に結果を表示
4. 検索結果の下に表示される「この画像をギャラリーに追加する」ボタンを押すと、その画像がVolume+テーブルに保存され、Vector Searchの同期がトリガーされる（ボタンを押さなければ何も保存されない）。追加後は「ギャラリーから検索」タブに切り替えると一覧に反映される

### 画像の追加

2通りの方法がある。

1. アップロード検索後に「この画像をギャラリーに追加する」ボタンを押す（Gemini解析は再実行せず、検索時に得たタグ・説明文をそのまま保存する）
2. Volume（`/Volumes/classic_stable_ytcy_catalog/cad_image_search/cad_image/`）に画像ファイルを直接追加し、`POST /api/admin/reindex` を呼び出す（未登録の画像だけを検出してGeminiで解析・登録し、Vector Searchの同期をトリガーする）

## 注意点

- **アップロードした画像は、明示的に「ギャラリーに追加する」を選択しない限り保存されません。** アップロード検索自体はGemini解析→ベクトル検索のみを行うその場限りの処理です。同名ファイルが既にVolumeにある場合は自動的にサフィックスを付けて衝突を回避します。
- **サンプルデータは8枚のみ**の小規模データセットです。デモの検索精度・多様性はこのデータ量に依存します。実運用を想定する場合はより多くの画像を登録してください。
- **コストについて**: 画像解析はGemini（FMAPI pay-per-tokenの外部モデル呼び出し）を都度実行するため、アップロード検索・reindexのたびに課金が発生します。Vector Search Standardエンドポイントにも稼働時間に応じた課金があります。
- **Geminiが利用できないワークスペースの場合**は、`app/app.yaml` の `GEMINI_ENDPOINT` を他のマルチモーダル対応モデル（例: Claude系のFMAPIエンドポイント）に差し替えることで動作しますが、プロンプトの出力形式によっては `app/image_analysis.py` の調整が必要になる場合があります。
- **Geminiの出力が稀に不正なJSON（ネストしたJSON文字列や、max_tokens超過による途中切れ）になることがあります。** `image_analysis.py` の `_parse_json` で複数段のフォールバック（コードフェンス除去、ネストJSONのアンラップ、正規表現による部分復旧）を行っていますが、完全ではありません。
- Vector Searchは **managed embeddings方式**（`embedding_source_columns`）を採用しているため、インデックス側のテキスト埋め込みとクエリ時の埋め込み（`query_text`）は常にDatabricks側が同一モデル（`databricks-gte-large-en`）で計算します。埋め込みベクトルを自前で計算・保存する実装にはなっていません。
- Delta Sync インデックスは長期間同期しないとソーステーブルの変更履歴が保持期間を超えて消え、`ONLINE_PIPELINE_FAILED` から復旧できなくなることがあります。その場合はインデックスの削除→再作成が必要です。

## ディレクトリ構成

```
cad_images/              サンプルCAD画像8枚（初期投入用）
app/
  main.py                FastAPIエントリポイント（API定義・静的ファイル配信）
  image_analysis.py       Gemini呼び出し・JSON安全パース（タグ付け・詳細説明生成）
  db_client.py            SQL Warehouse / UC Volume / Vector Search クライアント
  requirements.txt
  app.yaml                Databricks Apps設定（起動コマンド・環境変数）
  smoke_test.sh           ローカルでのAPI疎通確認スクリプト
  static/                 フロントエンドのビルド成果物（コミット対象）
  frontend/               React + Viteのソース
    src/App.jsx
    src/components/Gallery.jsx      ギャラリータブ
    src/components/UploadPanel.jsx  アップロードタブ
    src/components/ResultCard.jsx   検索結果カード（共通コンポーネント）
```
