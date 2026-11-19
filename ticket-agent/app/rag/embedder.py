"""Embedding 调用：本地 bge-m3（torch / ONNX int8）或 OpenAI 兼容接口，按批处理。"""

from __future__ import annotations

import os
import threading
from typing import Any

import httpx

from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import logger

# 百炼 text-embedding-v3 单次请求最多 10 条文本，超出会返回 400
MAX_BATCH_SIZE = 10
MAX_SEQ_LENGTH = 1024
INFER_THREADS = 4

_local_model: Any = None
_local_lock = threading.Lock()

_onnx_session: Any = None
_onnx_tokenizer: Any = None
_onnx_lock = threading.Lock()


def _is_local() -> bool:
    return settings.embedding_provider.strip().lower() == "local"


def _backend() -> str:
    """本地推理后端：onnx（int8，常驻内存更小）或 torch。"""
    if settings.embedding_backend.strip().lower() == "onnx":
        if settings.embedding_onnx_path:
            return "onnx"
        logger.warning("EMBEDDING_BACKEND=onnx 但 EMBEDDING_ONNX_PATH 为空，回退 torch")
    return "torch"


def ensure_configured() -> None:
    if _is_local():
        if not settings.embedding_model_path:
            raise AppError(5002, "本地 Embedding 模型路径未配置", 500)
        return
    if not settings.embedding_api_key:
        raise AppError(5002, "Embedding 服务未配置", 500)


def _get_local_model() -> Any:
    """懒加载本地模型并常驻，避免每次请求重复加载。"""
    global _local_model
    if _local_model is not None:
        return _local_model
    with _local_lock:
        if _local_model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise AppError(5002, "本地 Embedding 依赖未安装", 500) from exc
            try:
                model = SentenceTransformer(settings.embedding_model_path)
            except Exception as exc:
                raise AppError(5002, f"本地 Embedding 模型加载失败：{exc}", 500) from exc
            # 限制推理线程，避免占满 12 线程导致整机卡顿
            try:
                import torch

                torch.set_num_threads(INFER_THREADS)
            except Exception:  # noqa: BLE001 - 线程数设置失败不影响推理
                pass
            model.max_seq_length = MAX_SEQ_LENGTH
            _local_model = model
    return _local_model


def _get_onnx_runtime() -> tuple[Any, Any]:
    """懒加载 ONNX 会话与 tokenizer；int8 模型常驻约 0.6GB，比 torch 省一半以上。"""
    global _onnx_session, _onnx_tokenizer
    if _onnx_session is not None:
        return _onnx_session, _onnx_tokenizer
    with _onnx_lock:
        if _onnx_session is None:
            root = settings.embedding_onnx_path
            is_file = root.lower().endswith(".onnx")
            model_file = root if is_file else os.path.join(root, "model_int8.onnx")
            tokenizer_dir = os.path.dirname(root) if is_file else root
            if not os.path.exists(model_file):
                raise AppError(5002, f"ONNX 模型不存在：{model_file}", 500)
            try:
                import onnxruntime as ort
                from transformers import AutoTokenizer
            except ImportError as exc:
                raise AppError(5002, "ONNX Embedding 依赖未安装", 500) from exc
            try:
                options = ort.SessionOptions()
                options.intra_op_num_threads = INFER_THREADS
                options.inter_op_num_threads = 1
                options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
                session = ort.InferenceSession(
                    model_file,
                    sess_options=options,
                    providers=["CPUExecutionProvider"],
                )
                tokenizer = AutoTokenizer.from_pretrained(tokenizer_dir)
            except Exception as exc:
                raise AppError(5002, f"ONNX Embedding 模型加载失败：{exc}", 500) from exc
            _onnx_session = session
            _onnx_tokenizer = tokenizer
    return _onnx_session, _onnx_tokenizer


def _embed_onnx(texts: list[str], batch_size: int) -> list[list[float]]:
    import numpy as np

    session, tokenizer = _get_onnx_runtime()
    input_names = {item.name for item in session.get_inputs()}
    output_names = [item.name for item in session.get_outputs()]
    # sentence_embedding 已在图内做 CLS pooling，等价于 torch 版 encode 的 dense 输出
    index = output_names.index("sentence_embedding") if "sentence_embedding" in output_names else 0
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        encoded = tokenizer(
            batch,
            padding=True,
            truncation=True,
            max_length=MAX_SEQ_LENGTH,
            return_tensors="np",
        )
        feeds = {
            key: np.asarray(value, dtype=np.int64)
            for key, value in encoded.items()
            if key in input_names
        }
        embeddings = np.asarray(session.run(None, feeds)[index], dtype=np.float32)
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        vectors.extend((embeddings / norms).tolist())
    return vectors


def _embed_local(texts: list[str], batch_size: int) -> list[list[float]]:
    if _backend() == "onnx":
        try:
            return _embed_onnx(texts, batch_size)
        except AppError:
            raise
        except Exception as exc:
            raise AppError(5002, f"ONNX Embedding 推理失败：{exc}", 500) from exc
    model = _get_local_model()
    vectors = model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return [vector.tolist() for vector in vectors]


def warmup() -> None:
    """启动时预热本地模型；失败只记录日志，不影响服务启动。"""
    if not _is_local() or not settings.embedding_model_path:
        return
    try:
        backend = _backend()
        if backend == "onnx":
            _get_onnx_runtime()
        else:
            _get_local_model()
        # 先跑一条短文本，把推理路径的初始化也提前做掉
        _embed_local(["预热"], 1)
        logger.info("本地 Embedding 模型已预热", extra={"backend": backend})
    except Exception as exc:  # noqa: BLE001
        logger.warning("本地 Embedding 模型预热失败", extra={"error": str(exc)})


def embed_texts(texts: list[str], batch_size: int = 16) -> list[list[float]]:
    ensure_configured()
    if not texts:
        return []
    if _is_local():
        return _embed_local(texts, max(batch_size, 1))
    batch_size = min(max(batch_size, 1), MAX_BATCH_SIZE)
    url = f"{settings.embedding_base_url.rstrip('/')}/embeddings"
    headers = {"Authorization": f"Bearer {settings.embedding_api_key}"}
    vectors: list[list[float]] = []
    with httpx.Client(timeout=60) as client:
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            response = client.post(
                url,
                headers=headers,
                json={
                    "model": settings.embedding_model,
                    "input": batch,
                    "dimensions": settings.embedding_dim,
                    "encoding_format": "float",
                },
            )
            if response.status_code >= 400:
                raise AppError(
                    4000,
                    f"Embedding 服务返回 {response.status_code}：{response.text[:200]}",
                    502,
                )
            data = sorted(response.json().get("data", []), key=lambda item: item.get("index", 0))
            vectors.extend(item["embedding"] for item in data)
    if len(vectors) != len(texts):
        raise AppError(4000, "Embedding 返回数量不一致", 502)
    return vectors
