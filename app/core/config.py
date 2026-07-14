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
                flow_names=("inquiry_7_stage", "three_step_inquiry", "steam_project"),
            ),
            DifyAgentConfig(
                id="stage_question_refine",
                stage_id="question_refine",
                command="@stage_question_refine",
                name="问题提炼导师",
                description="负责把学生的零散发问提炼为可验证的核心探究问题。",
                flow_names=("inquiry_7_stage", "three_step_inquiry", "steam_project"),
            ),
            DifyAgentConfig(
                id="stage_hypothesis",
                stage_id="hypothesis",
                command="@stage_hypothesis",
                name="头脑风暴教练",
                description="负责整理学生猜想并形成可验证的科学假设。",
                flow_names=("inquiry_7_stage", "three_step_inquiry", "steam_project"),
            ),
            DifyAgentConfig(
                id="stage_experiment_design",
                stage_id="experiment_design",
                command="@stage_experiment_design",
                name="实验设计专家",
                description="负责实验变量、材料、步骤、记录方式和安全边界。",
                flow_names=("inquiry_7_stage", "three_step_inquiry", "steam_project"),
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
                flow_names=("inquiry_7_stage", "three_step_inquiry", "steam_project"),
            ),
            DifyAgentConfig(
                id="stage_extension",
                stage_id="extension",
                command="@stage_extension",
                name="探究闭环架构师",
                description="负责迁移拓展、成果反思和下一轮探究问题。",
                flow_names=("inquiry_7_stage", "three_step_inquiry", "steam_project"),
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
