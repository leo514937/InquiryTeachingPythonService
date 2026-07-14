import json

import httpx

from app.core.config import get_settings


class RagService:
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
        }
        return mock_data.get(stage_id, "【通用教参】以学生问题为起点，用证据链支撑结论，保留新的探究入口。")
