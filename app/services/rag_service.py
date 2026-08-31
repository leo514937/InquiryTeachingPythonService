import json

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.curriculum_knowledge_service import (
    CurriculumKnowledgeService,
    CurriculumSearchResult,
)


class RagService:
    @staticmethod
    def retrieve_curriculum_context(
        db: Session,
        *,
        topic: str,
        stage: dict,
        user_message: str,
    ) -> tuple[str, dict]:
        settings = get_settings()
        query = RagService.build_curriculum_query(
            topic=topic,
            stage=stage,
            user_message=user_message,
        )
        if not settings.curriculum_rag_enabled:
            return "", {
                "mode": "disabled",
                "query": query,
                "reason": "CURRICULUM_RAG_ENABLED=false",
                "records": [],
            }

        try:
            results = CurriculumKnowledgeService(db, settings).retrieve(
                query,
                settings.curriculum_top_k,
            )
        except Exception as exc:
            return "", {
                "mode": "local_bm25_error",
                "query": query,
                "error": str(exc),
                "records": [],
            }

        records = [RagService.curriculum_result_to_dict(result) for result in results]
        if not results:
            return "", {
                "mode": "local_bm25_empty",
                "query": query,
                "records": [],
            }
        return RagService.format_curriculum_context(results), {
            "mode": "local_bm25",
            "query": query,
            "records": records,
        }

    @staticmethod
    def build_curriculum_query(*, topic: str, stage: dict, user_message: str) -> str:
        parts = [
            topic.strip(),
            str(stage.get("name") or "").strip(),
            str(stage.get("display_direction") or "").strip(),
            user_message.strip(),
        ]
        return "\n".join(part for part in parts if part)

    @staticmethod
    def format_curriculum_context(results: list[CurriculumSearchResult]) -> str:
        sections = [
            "<curriculum_reference>",
            "以下内容仅作为课程标准参考，请结合学生年龄、技术基础和当前教学目标使用。",
        ]
        for index, result in enumerate(results, start=1):
            sections.extend(
                [
                    "",
                    f"[{index}] 来源：{result.source}",
                    f"相关内容：{result.content}",
                ]
            )
        sections.extend(
            [
                "",
                "请据此调整任务难度、活动形式、技术要求和评价方式，不要机械复述课标。",
                "</curriculum_reference>",
            ]
        )
        return "\n".join(sections)

    @staticmethod
    def merge_context(doc_input: str, curriculum_context: str) -> str:
        return "\n\n".join(
            item.strip()
            for item in (doc_input, curriculum_context)
            if item and item.strip()
        )

    @staticmethod
    def curriculum_sources(source: dict) -> list[str]:
        return list(
            dict.fromkeys(
                str(record.get("source") or "").strip()
                for record in source.get("records", [])
                if str(record.get("source") or "").strip()
            )
        )

    @staticmethod
    def source_note(sources: list[str]) -> str:
        if not sources:
            return ""
        return "\n\n参考课标：" + "、".join(sources)

    @staticmethod
    def curriculum_result_to_dict(result: CurriculumSearchResult) -> dict:
        return {
            "chunk_id": result.chunk_id,
            "chunk_ids": list(result.chunk_ids),
            "source": result.source,
            "source_index": result.source_index,
            "content": result.content,
            "score": result.score,
        }

    @staticmethod
    async def retrieve_context(stage_id: str, query: str) -> tuple[str, dict]:
        settings = get_settings()
        if not settings.dify_dataset_api_key or not settings.dify_dataset_id:
            context = RagService._mock_context(stage_id)
            return context, {"mode": "mock", "records": []}

        url = (
            f"{settings.dify_dataset_api_url.rstrip('/')}/datasets/"
            f"{settings.dify_dataset_id}/retrieve"
        )
        headers = {
            "Authorization": f"Bearer {settings.dify_dataset_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "query": query,
            "retrieval_model": {
                "search_method": "hybrid_search",
                "top_k": 3,
                "score_threshold": 0.35,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
                response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            records = data.get("records", [])
            contexts = [
                record.get("segment", {}).get("content", "")
                for record in records
                if record.get("segment", {}).get("content")
            ]
            if contexts:
                return "\n\n".join(contexts), {"mode": "dify_dataset", "records": records}
        except Exception as exc:
            context = RagService._mock_context(stage_id)
            return context, {"mode": "mock_after_error", "error": str(exc), "records": []}

        return RagService._mock_context(stage_id), {"mode": "mock_empty", "records": []}

    @staticmethod
    def source_json(source: dict) -> str:
        return json.dumps(source, ensure_ascii=False)

    @staticmethod
    def _mock_context(stage_id: str) -> str:
        mock_data = {
            "observation_start": "【教参提示】探究课适合从真实、可观察、略带认知冲突的现象进入，例如硬币隐现、筷子折弯、影子变化等。",
            "question_refine": "【课标提示】课堂主问题应具体、可验证、可操作，避免停留在“为什么会这样”的泛化层面。",
            "hypothesis": "【学习心理】鼓励学生大胆猜想，再把生活化表达整理为可验证假设。",
            "experiment_design": "【科学方法】实验设计需明确自变量、因变量、控制变量、记录表和安全边界。",
            "new_questions": "【生成性教学】实验误差、异常数据、学生追问都可转化为二次探究契机。",
            "conclusion": "【CER框架】建议按 Claim、Evidence、Reasoning 组织结论表达，强化证据意识。",
            "extension": "【迁移拓展】可通过 STEAM 制作、小研究、家庭观察任务，把规律迁移到新情境。",
            "natural_materials": "【生态提示】昆虫旅馆取材宜优先使用自然掉落或可安全回收材料，避免破坏原有栖息环境与过度采集。",
            "habitat_needs": "【观察提示】可结合校园植被、湿度、遮阴和高度条件，判断本地哪些昆虫更可能自然停留或入住。",
            "structure_design": "【工程提示】可比较孔径、分层、遮挡、通风和材料组合对不同昆虫栖息可能性的影响。",
            "build_and_sensing": "【数据提示】建议至少记录温湿度，并根据条件扩展光照等信息，让环境变化与昆虫活动能被持续追踪。",
            "settlement_observation": "【证据提示】观察时应坚持非侵扰原则，把现场现象、活动痕迹和传感数据分开记录再做判断。",
            "iteration_sharing": "【项目提示】根据入住情况和环境数据改进结构、位置或材料，并整理为可展示的项目迭代结论。",
        }
        return mock_data.get(stage_id, "【通用教参】以学生问题为起点，用证据链支撑结论，保留新的探究入口。")
