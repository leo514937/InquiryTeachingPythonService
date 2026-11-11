"""Typed, explicit task context shared by all capabilities in one run."""
import re
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field
from app.workspace.learner import LearnerProfile, recommended_profile


ContextEntry = Annotated[str, Field(max_length=2000)]


class TeachingContext(BaseModel):
    model_config = ConfigDict(extra='forbid')
    topic: str = Field(default='', max_length=4000)
    subject: str = Field(default='', max_length=200)
    stage: str = Field(default='', max_length=100)
    grade: str = Field(default='', max_length=100)
    learning_goals: list[ContextEntry] = Field(default_factory=list, max_length=30)
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    prior_knowledge: str = Field(default='', max_length=2000)
    language_level: str = Field(default='', max_length=1000)
    real_life_context: str = Field(default='', max_length=2000)
    resources: list[ContextEntry] = Field(default_factory=list, max_length=50)
    activity_formats: list[ContextEntry] = Field(default_factory=list, max_length=30)
    safety_constraints: str = Field(default='', max_length=2000)
    teacher_requirements: str = Field(default='', max_length=4000)
    assumptions: list[ContextEntry] = Field(default_factory=list, max_length=30)
    learner_profile: LearnerProfile | None = None

    @classmethod
    def from_request(cls, goal: str, supplied: dict | None = None):
        values = dict(supplied or {})
        values['topic'] = values.get('topic') or goal
        # Extract only conditions explicitly stated in the request; never infer age or stage.
        grade = re.search(r'([一二三四五六七八九]|[1-9])年级', goal)
        stage = re.search(r'(小学|初中|高中)', goal)
        duration = re.search(r'(?<!\d)(\d{1,3})\s*分钟', goal)
        # Capture an explicitly named subject only when it is unambiguous; this
        # records teacher input and does not choose capabilities or topology.
        subjects = [name for name in ('语文', '数学', '科学', '物理', '跨学科') if name in goal]
        if not values.get('subject') and len(subjects) == 1 and (grade or stage or '学科' in goal):
            values['subject'] = subjects[0]
        if grade and not values.get('grade'):
            values['grade'] = grade.group(0)
        if stage and not values.get('stage'):
            values['stage'] = stage.group(0)
        if duration and not values.get('duration_minutes') and int(duration.group(1)) > 0:
            values['duration_minutes'] = int(duration.group(1))
        context = cls.model_validate(values)
        unknown = {'subject':'学科未提供','stage':'学段未提供','grade':'年级未提供',
                   'duration_minutes':'课程时长未提供','learning_goals':'具体教学目标未单独提供','prior_knowledge':'已有知识基础未提供',
                   'language_level':'阅读与语言水平未提供','real_life_context':'真实生活情境未提供',
                   'resources':'教学资源未提供','activity_formats':'学生活动形式未提供',
                   'safety_constraints':'安全与环境约束未提供','teacher_requirements':'教师特殊要求未单独提供'}
        context.assumptions = [label for key,label in unknown.items() if not getattr(context,key)]
        context.learner_profile = recommended_profile(context.grade, context.stage)
        return context
