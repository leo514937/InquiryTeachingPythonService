import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{(BASE_DIR / 'app.db').as_posix()}",
    )
    upload_dir: Path = Path(
        os.getenv("UPLOAD_DIR", str(BASE_DIR / "data" / "uploads"))
    ).resolve()
    upload_max_file_bytes: int = int(os.getenv("UPLOAD_MAX_FILE_BYTES", str(20 * 1024 * 1024)))
    upload_max_files_per_session: int = int(os.getenv("UPLOAD_MAX_FILES_PER_SESSION", "10"))
    upload_max_total_chars: int = int(os.getenv("UPLOAD_MAX_TOTAL_CHARS", "50000"))

    curriculum_dir: Path = Path(
        os.getenv("CURRICULUM_DIR", str(BASE_DIR / "data" / "curriculum"))
    ).resolve()
    knowledge_source_dir: Path = Path(
        os.getenv(
            "KNOWLEDGE_SOURCE_DIR",
            str(BASE_DIR / "data" / "knowledge_sources"),
        )
    ).resolve()
    curriculum_rag_enabled: bool = os.getenv(
        "CURRICULUM_RAG_ENABLED",
        "true",
    ).strip().lower() in {"1", "true", "yes", "on"}
    curriculum_top_k: int = max(1, int(os.getenv("CURRICULUM_TOP_K", "4")))
    curriculum_candidate_k: int = max(
        curriculum_top_k,
        int(os.getenv("CURRICULUM_CANDIDATE_K", "16")),
    )
    curriculum_chunk_size: int = max(128, int(os.getenv("CURRICULUM_CHUNK_SIZE", "512")))
    curriculum_chunk_overlap: int = max(
        0,
        int(os.getenv("CURRICULUM_CHUNK_OVERLAP", "64")),
    )
    curriculum_rerank_enabled: bool = os.getenv(
        "CURRICULUM_RERANK_ENABLED",
        "true",
    ).strip().lower() in {"1", "true", "yes", "on"}
    curriculum_vector_enabled: bool = os.getenv(
        "CURRICULUM_VECTOR_ENABLED",
        "true",
    ).strip().lower() in {"1", "true", "yes", "on"}
    curriculum_vector_required: bool = os.getenv(
        "CURRICULUM_VECTOR_REQUIRED",
        "false",
    ).strip().lower() in {"1", "true", "yes", "on"}
    curriculum_vector_min_similarity: float = min(
        1.0,
        max(0.0, float(os.getenv("CURRICULUM_VECTOR_MIN_SIMILARITY", "0.5"))),
    )
    curriculum_embedding_model: str = os.getenv(
        "CURRICULUM_EMBEDDING_MODEL",
        "BAAI/bge-small-zh-v1.5",
    ).strip()
    curriculum_embedding_model_dir: Path = Path(
        os.getenv(
            "CURRICULUM_EMBEDDING_MODEL_DIR",
            str(BASE_DIR / "data" / "models" / "bge-small-zh-v1.5"),
        )
    ).resolve()
    curriculum_embedding_device: str = os.getenv(
        "CURRICULUM_EMBEDDING_DEVICE",
        "cpu",
    ).strip()
    curriculum_vector_dir: Path = Path(
        os.getenv(
            "CURRICULUM_VECTOR_DIR",
            str(BASE_DIR / "data" / "curriculum_vector"),
        )
    ).resolve()
    curriculum_vector_collection: str = os.getenv(
        "CURRICULUM_VECTOR_COLLECTION",
        "curriculum_chunks",
    ).strip()
    curriculum_snapshot_dir: Path = Path(
        os.getenv(
            "CURRICULUM_SNAPSHOT_DIR",
            str(BASE_DIR / "data" / "curriculum_snapshots"),
        )
    ).resolve()
    curriculum_snapshot_keep: int = max(
        1,
        int(os.getenv("CURRICULUM_SNAPSHOT_KEEP", "3")),
    )
    curriculum_hybrid_vector_weight: float = max(
        0.0,
        float(os.getenv("CURRICULUM_HYBRID_VECTOR_WEIGHT", "0.65")),
    )
    curriculum_hybrid_bm25_weight: float = max(
        0.0,
        float(os.getenv("CURRICULUM_HYBRID_BM25_WEIGHT", "0.35")),
    )
    curriculum_embedding_batch_size: int = max(
        1,
        int(os.getenv("CURRICULUM_EMBEDDING_BATCH_SIZE", "8")),
    )

    ecology_graph_auto_sync_enabled: bool = os.getenv(
        "ECOLOGY_GRAPH_AUTO_SYNC_ENABLED",
        "true",
    ).strip().lower() in {"1", "true", "yes", "on"}
    ecology_lightrag_dir: Path = Path(
        os.getenv(
            "ECOLOGY_LIGHTRAG_DIR",
            str(BASE_DIR / "data" / "lightrag" / "ecology"),
        )
    ).resolve()
    ecology_graph_worker_poll_seconds: float = max(
        0.5,
        float(os.getenv("ECOLOGY_GRAPH_WORKER_POLL_SECONDS", "2")),
    )
    ecology_graph_job_max_attempts: int = max(
        1,
        int(os.getenv("ECOLOGY_GRAPH_JOB_MAX_ATTEMPTS", "3")),
    )
    globi_import_worker_enabled: bool = os.getenv(
        "GLOBI_IMPORT_WORKER_ENABLED",
        "true",
    ).strip().lower() in {"1", "true", "yes", "on"}
    globi_import_worker_poll_seconds: float = max(
        0.5,
        float(os.getenv("GLOBI_IMPORT_WORKER_POLL_SECONDS", "2")),
    )
    globi_runtime_enabled: bool = os.getenv(
        "GLOBI_RUNTIME_ENABLED",
        "true",
    ).strip().lower() in {"1", "true", "yes", "on"}
    globi_runtime_cache_seconds: int = max(
        60,
        int(os.getenv("GLOBI_RUNTIME_CACHE_SECONDS", "86400")),
    )
    globi_runtime_timeout_seconds: float = max(
        1.0,
        float(os.getenv("GLOBI_RUNTIME_TIMEOUT_SECONDS", "10")),
    )
    globi_runtime_max_attempts: int = max(
        1,
        min(5, int(os.getenv("GLOBI_RUNTIME_MAX_ATTEMPTS", "3"))),
    )
    globi_runtime_max_entities: int = max(
        1,
        min(3, int(os.getenv("GLOBI_RUNTIME_MAX_ENTITIES", "3"))),
    )
    globi_runtime_result_limit: int = max(
        25,
        min(1000, int(os.getenv("GLOBI_RUNTIME_RESULT_LIMIT", "250"))),
    )
    globi_runtime_relation_limit: int = max(
        5,
        min(100, int(os.getenv("GLOBI_RUNTIME_RELATION_LIMIT", "40"))),
    )
    globi_runtime_concurrency: int = max(
        1,
        min(4, int(os.getenv("GLOBI_RUNTIME_CONCURRENCY", "2"))),
    )
    globi_runtime_max_response_bytes: int = max(
        1024 * 1024,
        int(os.getenv("GLOBI_RUNTIME_MAX_RESPONSE_BYTES", str(8 * 1024 * 1024))),
    )

    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_api_base: str = os.getenv("LLM_API_BASE", "https://api.openai.com/v1")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    ecology_graph_extract_model: str = os.getenv(
        "ECOLOGY_GRAPH_EXTRACT_MODEL",
        "",
    ).strip() or os.getenv("LLM_MODEL", "gpt-4o-mini").strip()
    llm_reasoning_enabled: bool = os.getenv(
        "LLM_REASONING_ENABLED",
        "false",
    ).strip().lower() in {"1", "true", "yes", "on"}
    llm_http_referer: str = os.getenv("LLM_HTTP_REFERER", "")
    llm_app_title: str = os.getenv("LLM_APP_TITLE", "")

    agent_config_path: Path = Path(
        os.getenv(
            "AGENT_CONFIG_PATH",
            str(BASE_DIR / "app" / "agents" / "config" / "agents.yaml"),
        )
    ).resolve()

    request_timeout_seconds: float = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "60"))
    frontend_origin: str = os.getenv("FRONTEND_ORIGIN", "http://127.0.0.1:5173").strip()
    frontend_origins: tuple[str, ...] = tuple(
        origin.strip()
        for origin in frontend_origin.split(",")
        if origin.strip()
    )
    auth_session_days: int = int(os.getenv("AUTH_SESSION_DAYS", "30"))
    auth_cookie_secure: bool = os.getenv(
        "AUTH_COOKIE_SECURE",
        "false",
    ).strip().lower() in {"1", "true", "yes", "on"}
    admin_registration_enabled: bool = os.getenv(
        "ADMIN_REGISTRATION_ENABLED",
        "true",
    ).strip().lower() in {"1", "true", "yes", "on"}

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
