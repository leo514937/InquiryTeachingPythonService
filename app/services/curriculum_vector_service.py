from __future__ import annotations

import importlib.util
import shutil
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from app.core.config import Settings
from app.db.models import CurriculumChunkModel


class CurriculumVectorUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class CurriculumVectorHit:
    chunk_id: int
    score: float


_MODEL_CACHE: dict[tuple[str, str], "LocalEmbeddingModel"] = {}
_MODEL_CACHE_LOCK = threading.Lock()
_VECTOR_LOCKS: dict[str, threading.RLock] = {}
_VECTOR_LOCKS_GUARD = threading.Lock()


def get_local_embedding_model(settings: Settings) -> "LocalEmbeddingModel":
    key = (
        str(settings.curriculum_embedding_model_dir),
        settings.curriculum_embedding_device,
    )
    with _MODEL_CACHE_LOCK:
        model = _MODEL_CACHE.get(key)
        if model is None:
            model = LocalEmbeddingModel(settings)
            _MODEL_CACHE[key] = model
        return model


def vector_directory_lock(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _VECTOR_LOCKS_GUARD:
        lock = _VECTOR_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _VECTOR_LOCKS[key] = lock
        return lock


class LocalEmbeddingModel:
    def __init__(self, settings: Settings):
        self.model_name = settings.curriculum_embedding_model
        self.model_dir = settings.curriculum_embedding_model_dir
        self.device = settings.curriculum_embedding_device or "cpu"
        self.batch_size = settings.curriculum_embedding_batch_size
        self._model = None
        self._dimension: int | None = None
        self._load_lock = threading.Lock()
        self._encode_lock = threading.Lock()

    @property
    def dimension(self) -> int | None:
        return self._dimension

    def availability_error(self) -> str:
        if not self.model_dir.is_dir():
            return f"本地 Embedding 模型不存在：{self.model_dir}"
        if importlib.util.find_spec("sentence_transformers") is None:
            return "缺少 sentence-transformers 依赖"
        if importlib.util.find_spec("torch") is None:
            return "缺少 torch 依赖"
        return ""

    def load(self):
        if self._model is not None:
            return self._model
        with self._load_lock:
            if self._model is not None:
                return self._model
            error = self.availability_error()
            if error:
                raise CurriculumVectorUnavailable(error)
            try:
                from sentence_transformers import SentenceTransformer

                model = SentenceTransformer(str(self.model_dir), device=self.device)
                get_dimension = getattr(model, "get_embedding_dimension", None)
                if get_dimension is None:
                    get_dimension = model.get_sentence_embedding_dimension
                dimension = get_dimension()
            except Exception as exc:
                raise CurriculumVectorUnavailable(
                    f"本地 Embedding 模型加载失败：{type(exc).__name__}: {exc}"
                ) from exc
            if not dimension:
                raise CurriculumVectorUnavailable("Embedding 模型未提供有效向量维度")
            self._model = model
            self._dimension = int(dimension)
            return model

    def encode(self, texts: Iterable[str]) -> list[list[float]]:
        values = [text if text.strip() else " " for text in texts]
        if not values:
            return []
        model = self.load()
        try:
            with self._encode_lock:
                vectors = model.encode(
                    values,
                    batch_size=self.batch_size,
                    show_progress_bar=False,
                    normalize_embeddings=True,
                    convert_to_numpy=True,
                )
        except Exception as exc:
            raise CurriculumVectorUnavailable(
                f"Embedding 计算失败：{type(exc).__name__}: {exc}"
            ) from exc
        return [[float(value) for value in row] for row in vectors]


class CurriculumVectorStore:
    def __init__(
        self,
        settings: Settings,
        embedding_model: LocalEmbeddingModel | None = None,
    ):
        self.settings = settings
        self.embedding_model = embedding_model or get_local_embedding_model(settings)
        self.persist_dir = settings.curriculum_vector_dir
        self.collection_name = settings.curriculum_vector_collection
        self.error = ""
        self.rebuild_required = False
        self.client = None
        self.collection = None
        self._lock = vector_directory_lock(self.persist_dir)
        self._initialize()

    @property
    def available(self) -> bool:
        return self.collection is not None and not self.error and not self.rebuild_required

    def _initialize(self) -> None:
        if not self.settings.curriculum_vector_enabled:
            self.error = "向量检索未启用"
            return
        model_error = self.embedding_model.availability_error()
        if model_error:
            self.error = model_error
            return
        if importlib.util.find_spec("chromadb") is None:
            self.error = "缺少 chromadb 依赖"
            return
        try:
            import chromadb

            self.persist_dir.mkdir(parents=True, exist_ok=True)
            chroma_settings = chromadb.config.Settings(anonymized_telemetry=False)
            self.client = chromadb.PersistentClient(
                path=str(self.persist_dir),
                settings=chroma_settings,
            )
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=None,
                metadata={
                    "hnsw:space": "cosine",
                    "embedding_model": self.settings.curriculum_embedding_model,
                },
            )
            metadata = self.collection.metadata or {}
            indexed_model = str(metadata.get("embedding_model") or "")
            if self.collection.count() and indexed_model != self.settings.curriculum_embedding_model:
                self.rebuild_required = True
                self.error = (
                    f"向量索引模型为 {indexed_model or '未知'}，当前模型为 "
                    f"{self.settings.curriculum_embedding_model}，需要重建索引"
                )
        except Exception as exc:
            self.client = None
            self.collection = None
            self.error = f"Chroma 初始化失败：{type(exc).__name__}: {exc}"

    def embed_texts(self, texts: Iterable[str]) -> list[list[float]]:
        if self.collection is None:
            raise CurriculumVectorUnavailable(self.error or "Chroma 不可用")
        vectors = self.embedding_model.encode(texts)
        if vectors:
            self._validate_dimension(len(vectors[0]))
        return vectors

    def _validate_dimension(self, dimension: int) -> None:
        if self.collection is None:
            raise CurriculumVectorUnavailable(self.error or "Chroma 不可用")
        metadata = dict(self.collection.metadata or {})
        indexed_dimension = int(metadata.get("embedding_dimension") or 0)
        if self.collection.count() and indexed_dimension and indexed_dimension != dimension:
            self.rebuild_required = True
            self.error = (
                f"向量索引维度为 {indexed_dimension}，当前模型维度为 {dimension}，需要重建索引"
            )
            raise CurriculumVectorUnavailable(self.error)
        if indexed_dimension != dimension:
            self.collection.modify(
                metadata={
                    "embedding_model": self.settings.curriculum_embedding_model,
                    "embedding_dimension": dimension,
                }
            )

    def upsert_chunks(
        self,
        chunks: list[CurriculumChunkModel],
        embeddings: list[list[float]],
    ) -> int:
        rows = [row for row in chunks if row.id is not None and row.content.strip()]
        if len(rows) != len(embeddings):
            raise CurriculumVectorUnavailable("课标片段与向量数量不一致")
        if not rows:
            return 0
        if self.collection is None:
            raise CurriculumVectorUnavailable(self.error or "Chroma 不可用")
        self._validate_dimension(len(embeddings[0]))
        with self._lock:
            for start in range(0, len(rows), 256):
                batch_rows = rows[start : start + 256]
                batch_vectors = embeddings[start : start + 256]
                self.collection.upsert(
                    ids=[self._id(int(row.id)) for row in batch_rows],
                    embeddings=batch_vectors,
                    metadatas=[
                        {
                            "db_id": int(row.id),
                            "source": row.source,
                            "source_index": int(row.source_index),
                        }
                        for row in batch_rows
                    ],
                )
        return len(rows)

    def index_chunks(self, chunks: list[CurriculumChunkModel]) -> int:
        embeddings = self.embed_texts([row.content for row in chunks])
        return self.upsert_chunks(chunks, embeddings)

    def delete_source(self, source: str) -> None:
        if self.collection is None:
            return
        with self._lock:
            self.collection.delete(where={"source": source})

    def query(self, query: str, top_k: int) -> list[CurriculumVectorHit]:
        if not self.available:
            raise CurriculumVectorUnavailable(self.error or "向量检索不可用")
        query_vectors = self.embed_texts([query])
        if not query_vectors:
            return []
        result = self.collection.query(
            query_embeddings=query_vectors,
            n_results=max(1, top_k),
            include=["metadatas", "distances"],
        )
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        hits: list[CurriculumVectorHit] = []
        for index, metadata in enumerate(metadatas):
            chunk_id = metadata.get("db_id") if metadata else None
            if chunk_id is None:
                continue
            distance = float(distances[index]) if index < len(distances) else 1.0
            hits.append(
                CurriculumVectorHit(
                    chunk_id=int(chunk_id),
                    score=max(0.0, 1.0 - distance),
                )
            )
        return hits

    def rebuild(self, chunks: list[CurriculumChunkModel]) -> int:
        if self.client is None:
            raise CurriculumVectorUnavailable(self.error or "Chroma 不可用")
        with self._lock:
            try:
                self.client.delete_collection(self.collection_name)
            except Exception:
                pass
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=None,
                metadata={
                    "hnsw:space": "cosine",
                    "embedding_model": self.settings.curriculum_embedding_model,
                },
            )
            self.error = ""
            self.rebuild_required = False
            if not chunks:
                return 0
            return self.index_chunks(chunks)

    def count(self) -> int:
        return int(self.collection.count()) if self.collection is not None else 0

    def snapshot(self) -> str | None:
        if not self.persist_dir.is_dir():
            return None
        root = self.settings.curriculum_snapshot_dir
        root.mkdir(parents=True, exist_ok=True)
        destination = root / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        with self._lock:
            shutil.copytree(self.persist_dir, destination)
        snapshots = sorted(
            [path for path in root.iterdir() if path.is_dir()],
            reverse=True,
        )
        for stale in snapshots[self.settings.curriculum_snapshot_keep :]:
            shutil.rmtree(stale, ignore_errors=True)
        return str(destination)

    def status(self) -> dict:
        dependency_ready = (
            importlib.util.find_spec("chromadb") is not None
            and not self.embedding_model.availability_error()
        )
        return {
            "enabled": self.settings.curriculum_vector_enabled,
            "required": self.settings.curriculum_vector_required,
            "available": self.available,
            "dependency_ready": dependency_ready,
            "model": self.settings.curriculum_embedding_model,
            "model_dir": str(self.settings.curriculum_embedding_model_dir),
            "device": self.settings.curriculum_embedding_device,
            "vector_dir": str(self.persist_dir),
            "collection": self.collection_name,
            "vector_count": self.count(),
            "rebuild_required": self.rebuild_required,
            "error": self.error,
        }

    @staticmethod
    def _id(chunk_id: int) -> str:
        return f"curriculum-chunk-{chunk_id}"
