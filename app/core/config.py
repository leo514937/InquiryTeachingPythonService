import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class DifyAgentConfig:
    id: str
    stage_id: str
    command: str
    name: str
    description: str
    api_url: str = ""
    api_key: str = ""
    flow_names: tuple[str, ...] = ()


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

    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_api_base: str = os.getenv("LLM_API_BASE", "https://api.openai.com/v1")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    llm_reasoning_enabled: bool = os.getenv(
        "LLM_REASONING_ENABLED",
        "false",
    ).strip().lower() in {"1", "true", "yes", "on"}
    llm_http_referer: str = os.getenv("LLM_HTTP_REFERER", "")
    llm_app_title: str = os.getenv("LLM_APP_TITLE", "")

    dify_dataset_api_url: str = os.getenv("DIFY_DATASET_API_URL", "https://api.dify.ai/v1")
    dify_dataset_id: str = os.getenv("DIFY_DATASET_ID", "")
    dify_dataset_api_key: str = os.getenv("DIFY_DATASET_API_KEY", "")

    dify_stage_agent_mode: str = os.getenv("DIFY_STAGE_AGENT_MODE", "mock").strip().lower()
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

    def dify_stage_agents(self) -> list[DifyAgentConfig]:
        raw = os.getenv("DIFY_STAGE_AGENTS_JSON", "").strip()
        if raw:
            try:
                parsed = json.loads(raw)
                return [self._agent_from_dict(item) for item in parsed]
            except Exception as exc:
                raise RuntimeError(f"DIFY_STAGE_AGENTS_JSON parse failed: {exc}") from exc

        return [
            DifyAgentConfig(
                id="stage_observation_start",
                stage_id="observation_start",
                command="@stage_observation_start",
                name="情境探寻专家",
                description="负责从真实现象、生活事件和具体实物中设计观察起点。",
                flow_names=("inquiry_7_stage", "three_step_inquiry", "steam_project", "insect_hotel_project"),
            ),
            DifyAgentConfig(
                id="stage_question_refine",
                stage_id="question_refine",
                command="@stage_question_refine",
                name="问题提炼导师",
                description="负责把学生的零散发问提炼为可验证的核心探究问题。",
                flow_names=("inquiry_7_stage", "three_step_inquiry", "steam_project", "insect_hotel_project"),
            ),
            DifyAgentConfig(
                id="stage_hypothesis",
                stage_id="hypothesis",
                command="@stage_hypothesis",
                name="头脑风暴教练",
                description="负责整理学生猜想并形成可验证的科学假设。",
                flow_names=("inquiry_7_stage", "three_step_inquiry", "steam_project", "insect_hotel_project"),
            ),
            DifyAgentConfig(
                id="stage_experiment_design",
                stage_id="experiment_design",
                command="@stage_experiment_design",
                name="实验设计专家",
                description="负责实验变量、材料、步骤、记录方式和安全边界。",
                flow_names=("inquiry_7_stage", "three_step_inquiry", "steam_project", "insect_hotel_project"),
            ),
            DifyAgentConfig(
                id="stage_new_questions",
                stage_id="new_questions",
                command="@stage_new_questions",
                name="教育契机捕手",
                description="负责把异常现象和学生追问转化为新的探究机会。",
                flow_names=("inquiry_7_stage", "three_step_inquiry", "steam_project"),
            ),
            DifyAgentConfig(
                id="stage_conclusion",
                stage_id="conclusion",
                command="@stage_conclusion",
                name="证据链整理师",
                description="负责用证据和推理组织阶段性科学结论。",
                flow_names=("inquiry_7_stage", "three_step_inquiry", "steam_project", "insect_hotel_project"),
            ),
            DifyAgentConfig(
                id="stage_extension",
                stage_id="extension",
                command="@stage_extension",
                name="探究闭环架构师",
                description="负责迁移拓展、成果反思和下一轮探究问题。",
                flow_names=("inquiry_7_stage", "three_step_inquiry", "steam_project", "insect_hotel_project"),
            ),
        ]

    @staticmethod
    def _agent_from_dict(item: dict[str, Any]) -> DifyAgentConfig:
        flows = item.get("flow_names") or item.get("flows") or []
        return DifyAgentConfig(
            id=str(item["id"]),
            stage_id=str(item["stage_id"]),
            command=str(item.get("command") or f"@{item['id']}"),
            name=str(item.get("name") or item["id"]),
            description=str(item.get("description") or ""),
            api_url=str(item.get("api_url") or ""),
            api_key=str(item.get("api_key") or ""),
            flow_names=tuple(str(flow) for flow in flows),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
