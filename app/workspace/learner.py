"""Grade-band suggestions; these are guidance, not claims about individual students."""
import re
from pydantic import BaseModel


class LearnerProfile(BaseModel):
    band: str
    language_guidance: str
    task_guidance: str
    abstraction_guidance: str
    teacher_support: str
    collaboration_guidance: str
    is_recommendation: bool = True


def recommended_profile(grade: str, stage: str) -> LearnerProfile | None:
    if stage != '小学':
        return None
    match = re.fullmatch(r'([一二三四五六1-6])年级', grade.strip())
    if not match:
        return None
    grade_number = {'一':1,'二':2,'三':3,'四':4,'五':5,'六':6}.get(match.group(1))
    if grade_number is None:
        grade_number = int(match.group(1))
    if grade_number <= 2:
        return LearnerProfile(band='小学低年级',language_guidance='使用短句和熟悉词语，必要时结合图示。',task_guidance='每次呈现一个短步骤，先示范再操作。',abstraction_guidance='从具体可观察的事物出发。',teacher_support='教师示范并在操作时持续支持。',collaboration_guidance='采用明确分工的双人交流。')
    if grade_number <= 4:
        return LearnerProfile(band='小学中年级',language_guidance='使用清晰短句，解释必要的新词。',task_guidance='将任务分成少量步骤并提供记录提示。',abstraction_guidance='比较具体证据并尝试解释关系。',teacher_support='教师提供记录支架和阶段性提示。',collaboration_guidance='小组轮流记录、分享和倾听。')
    return LearnerProfile(band='小学高年级',language_guidance='使用准确、适龄的学科词汇并说明关键术语。',task_guidance='允许学生自主安排多步骤任务并检查结果。',abstraction_guidance='比较多种证据，解释关系和局限。',teacher_support='教师提供评价标准并在需要时点拨。',collaboration_guidance='小组自主分工、讨论并综合观点。')
