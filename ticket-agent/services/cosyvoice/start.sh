#!/usr/bin/env bash
set -euo pipefail

MODEL_DIR="${COSYVOICE_MODEL_DIR:-/models/CosyVoice2-0.5B}"
MODEL_ID="${COSYVOICE_MODEL_ID:-iic/CosyVoice2-0.5B}"
export COSYVOICE_MODEL_DIR="${MODEL_DIR}"
export COSYVOICE_MODEL_ID="${MODEL_ID}"
export MODELSCOPE_CACHE="${MODELSCOPE_CACHE:-/models/.cache}"

if [ ! -f "${MODEL_DIR}/cosyvoice2.yaml" ]; then
  echo "[cosyvoice] 模型不存在，开始下载 ${MODEL_ID} -> ${MODEL_DIR}"
  mkdir -p "${MODEL_DIR}"
  python -c "from modelscope import snapshot_download; snapshot_download('${MODEL_ID}', local_dir='${MODEL_DIR}')"
fi

echo "[cosyvoice] 启动 TTS 服务，模型目录 ${MODEL_DIR}"
exec uvicorn server:app --host 0.0.0.0 --port 50000 --workers 1
