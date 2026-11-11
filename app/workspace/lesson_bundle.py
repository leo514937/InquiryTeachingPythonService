"""Structured lesson output and deterministic validation for the studio profile."""
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field, StrictInt

LessonText = Annotated[str, Field(min_length=1, max_length=4000)]


class Activity(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=300)
    minutes: StrictInt = Field(gt=0, le=1440)
    goal_indexes: list[StrictInt] = Field(min_length=1, max_length=30)
    teacher_guide: str = Field(min_length=1, max_length=4000)
    student_task: str = Field(min_length=1, max_length=4000)
    evidence: str = Field(min_length=1, max_length=2000)
    materials: list[LessonText] = Field(min_length=1, max_length=30)
    safety: str = Field(min_length=1, max_length=2000)


class Worksheet(BaseModel):
    model_config = ConfigDict(extra='forbid')
    steps: list[LessonText] = Field(min_length=1, max_length=30)
    activity_indexes: list[StrictInt] = Field(min_length=1, max_length=30)


class Assessment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    criteria: list[LessonText] = Field(min_length=1, max_length=30)
    goal_indexes: list[StrictInt] = Field(min_length=1, max_length=30)
    activity_indexes: list[StrictInt] = Field(min_length=1, max_length=30)


class LessonBundle(BaseModel):
    model_config = ConfigDict(extra='forbid')
    goals: list[LessonText] = Field(min_length=1, max_length=30)
    questions: list[LessonText] = Field(min_length=1, max_length=30)
    activities: list[Activity] = Field(min_length=1, max_length=30)
    worksheet: Worksheet
    assessment: Assessment
    resources: list[LessonText] = Field(min_length=1, max_length=50)


class CompleteActivity(Activity):
    teacher_preparation: LessonText


class CompleteLessonBundle(LessonBundle):
    background: LessonText
    situation: LessonText
    reflection: LessonText
    activities: list[CompleteActivity] = Field(min_length=1, max_length=15)


def validate_complete_lesson(payload: dict, duration_minutes: int | None) -> CompleteLessonBundle:
    bundle = CompleteLessonBundle.model_validate(payload)
    legacy = bundle.model_dump(exclude={'background', 'situation', 'reflection'})
    for activity in legacy['activities']:
        activity.pop('teacher_preparation', None)
    validate_lesson(legacy, duration_minutes)
    if len(bundle.goals) + len(bundle.questions) + len(bundle.activities) + 6 > 30:
        raise ValueError('教学成果数量超出限制')
    return bundle


def validate_lesson(payload: dict, duration_minutes: int | None) -> LessonBundle:
    bundle = LessonBundle.model_validate(payload)
    if duration_minutes is not None and sum(activity.minutes for activity in bundle.activities) != duration_minutes:
        raise ValueError('活动时间与总课时不一致')
    def valid(indexes, length):
        return all(isinstance(i, int) and not isinstance(i, bool) and 0 <= i < length for i in indexes)
    if (any(not valid(a.goal_indexes, len(bundle.goals)) for a in bundle.activities)
            or not valid(bundle.assessment.goal_indexes, len(bundle.goals))
            or not valid(bundle.assessment.activity_indexes, len(bundle.activities))
            or not valid(bundle.worksheet.activity_indexes, len(bundle.activities))):
        raise ValueError('教学对象引用无效')
    covered = {index for activity in bundle.activities for index in activity.goal_indexes}
    if covered != set(range(len(bundle.goals))) or set(bundle.assessment.goal_indexes) != covered:
        raise ValueError('目标与活动或评价引用不完整')
    return bundle


def make_artifacts(payload: dict, duration_minutes: int | None) -> list[dict]:
    from app.workspace.artifacts.service import _id
    complete = 'background' in payload
    bundle = validate_complete_lesson(payload, duration_minutes) if complete else validate_lesson(payload, duration_minutes)
    goals = [_id('art') for _ in bundle.goals]
    activities = [_id('art') for _ in bundle.activities]
    def narrative(key, title, value):
        return {'server_id': _id('art'), 'type': 'ReportNarrative',
                'content': {'section_key': key, 'title': title, 'paragraphs': [value], 'author_kind': 'agent'}}
    result = [narrative('teaching_context', '教学背景与学情', bundle.background)] if complete else []
    result += [{'server_id': goals[i], 'type': 'LearningGoal',
               'content': {'title': f'教学目标 {i + 1}', 'description': text}}
              for i, text in enumerate(bundle.goals)]
    if complete:
        result.append(narrative('situation', '真实问题情境', bundle.situation))
    result += [{'server_id': _id('art'), 'type': 'InquiryQuestion',
                'content': {'title': f'探究问题 {i + 1}', 'question': text}}
               for i, text in enumerate(bundle.questions)]
    for i, activity in enumerate(bundle.activities):
        result.append({'server_id': activities[i], 'type': 'InquiryActivity',
                       'content': {'title': activity.name, 'description': activity.teacher_guide,
                                   **({'teacher_preparation': activity.teacher_preparation} if complete else {}),
                                   'student_instructions': activity.student_task,
                                   'minutes': activity.minutes, 'evidence': activity.evidence,
                                   'materials': activity.materials, 'safety_measures': activity.safety,
                                   'goal_ids': [goals[n] for n in activity.goal_indexes]}})
    result.append({'server_id': _id('art'), 'type': 'StudentWorksheet',
                   'content': {'title': '学生任务单', 'steps': bundle.worksheet.steps,
                               'activity_ids': [activities[n] for n in bundle.worksheet.activity_indexes]}})
    result.append({'server_id': _id('art'), 'type': 'Assessment',
                   'content': {'title': '学习评价', 'criteria': bundle.assessment.criteria,
                               'goal_ids': [goals[n] for n in bundle.assessment.goal_indexes],
                               'activity_ids': [activities[n] for n in bundle.assessment.activity_indexes]}})
    result.append({'server_id': _id('art'), 'type': 'ResourceChecklist',
                   'content': {'title': '资源清单', 'materials': bundle.resources}})
    if complete:
        result.append(narrative('reflection', '教学反思建议', bundle.reflection))
    return result
