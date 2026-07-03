#!/bin/bash
# ローカルスモークテスト: FastAPIバックエンドを起動し主要APIを叩く
set -u
cd "$(dirname "$0")"

export DATABRICKS_HOST=https://fevm-classic-stable-ytcy.cloud.databricks.com
export DATABRICKS_TOKEN=$(/opt/homebrew/bin/databricks auth token -p fevm-classic-stable-ytcy | python3 -c "import json,sys;print(json.load(sys.stdin)['access_token'])")
export CATALOG=classic_stable_ytcy_catalog
export SCHEMA=cad_image_search
export VOLUME=cad_image
export DATABRICKS_WAREHOUSE_ID=e351c2d1b16eae95
export VS_ENDPOINT_NAME=cad-image-search-endpoint
export VS_INDEX_NAME=classic_stable_ytcy_catalog.cad_image_search.cad_image_index
export GEMINI_ENDPOINT=databricks-gemini-2-5-flash
export EMBEDDING_ENDPOINT=databricks-gte-large-en

PORT=8177
python3 -m uvicorn main:app --port $PORT >/tmp/uvicorn_smoke.log 2>&1 &
UVPID=$!
trap "kill $UVPID 2>/dev/null" EXIT
sleep 4

fail=0
check() { # name url [curl-args...]
  local name=$1; shift
  local out
  out=$(curl -s --max-time 120 "$@")
  if [ -z "$out" ] || echo "$out" | grep -q '"detail"'; then
    echo "NG  $name: ${out:0:300}"; fail=1
  else
    echo "OK  $name: ${out:0:200}"
  fi
}

check config       localhost:$PORT/api/config
check images       localhost:$PORT/api/images
check index-status localhost:$PORT/api/index/status
echo "--- SPA index ---"
curl -s localhost:$PORT/ | head -c 120; echo
exit $fail
