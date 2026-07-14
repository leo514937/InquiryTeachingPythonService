from app.workflow.flows import get_flow


class MarkdownExportService:
    @staticmethod
    def compile_lesson_plan(topic: str, flow_name: str, outputs: list) -> str:
        flow = get_flow(flow_name)
        output_map = {item.stage_id: item for item in outputs}

        lines = [
            f"# 探究式教学设计：{topic}",
            "",
            f"> 教学流：{flow['display_name']}。本文档由 AI 教师探究式教学指导服务协同生成。",
            "",
            "## 一、课题信息",
            "",
            f"- 课题名称：{topic}",
            "- 课型：探究式科学课",
            "- 建议课时：1-2 课时，可按课堂长度裁剪",
            "",
            "## 二、阶段化活动设计",
            "",
        ]

        for stage in flow["stages"]:
            output = output_map.get(stage["id"])
            content = ""
            if output:
                content = output.final_content or output.draft_content or ""
            lines.extend(
                [
                    f"### {stage['name']}",
                    "",
                    f"**导师角色**：{stage['expert']}",
                    "",
                    f"**阶段目标**：{stage['direction']}",
                    "",
                    content or "_本阶段暂未生成草案。_",
                    "",
                    "**课堂评价建议**：关注学生是否能提出证据、说明推理过程，并根据同伴反馈修正想法。",
                    "",
                ]
            )

        lines.extend(
            [
                "## 三、整体评价量规",
                "",
                "| 维度 | 观察要点 | 评价方式 |",
                "| --- | --- | --- |",
                "| 问题意识 | 能否从现象中提出可探究问题 | 提问卡、课堂追问 |",
                "| 证据意识 | 能否记录、比较、解释实验数据 | 实验记录单、小组汇报 |",
                "| 合作表达 | 能否倾听同伴并清晰表达观点 | 小组互评、展示评价 |",
                "| 迁移应用 | 能否把规律迁移到新情境 | 延伸任务、作品展示 |",
                "",
            ]
        )
        return "\n".join(lines)
