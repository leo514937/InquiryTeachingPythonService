"""Validation boundary for future model-produced lesson diagnostics.

This module does not perform retrieval, model calls, or persistence. Offsets
are Unicode code-point offsets into the exact saved paragraph version.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class LessonIssue(BaseModel):
    model_config = ConfigDict(extra='forbid')
    section_id: str = Field(min_length=1, max_length=80)
    paragraph_id: str = Field(min_length=1, max_length=80)
    start: StrictInt = Field(ge=0)
    end: StrictInt = Field(ge=1)
    original_text: str = Field(min_length=1, max_length=10000)
    dimension: Literal['教学目标', '课程匹配', '探究活动', '教学逻辑', '学习评价', '学情适配', '实施可行性']
    severity: Literal['low', 'medium', 'high']
    title: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=2000)
    suggested_text: str = Field(min_length=1, max_length=10000)
    evidence_refs: list[str] = Field(default_factory=list, max_length=20)


class LessonDiagnosis(BaseModel):
    model_config = ConfigDict(extra='forbid')
    issues: list[LessonIssue] = Field(max_length=50)


def validate_diagnosis(payload, document, evidence):
    """Reject locations or citations that cannot be resolved against inputs."""
    result = LessonDiagnosis.model_validate(payload)
    sections = {section['id']: section for section in document['sections']}
    available = {item['evidence_id'] for item in evidence}
    for issue in result.issues:
        section = sections.get(issue.section_id)
        paragraphs = {paragraph['id']: paragraph for paragraph in section['paragraphs']} if section else {}
        paragraph = paragraphs.get(issue.paragraph_id)
        if (not paragraph or issue.end <= issue.start or issue.end > len(paragraph['text'])
                or paragraph['text'][issue.start:issue.end] != issue.original_text):
            raise ValueError('诊断位置与教案版本不一致')
        if len(issue.evidence_refs) != len(set(issue.evidence_refs)) or set(issue.evidence_refs) - available:
            raise ValueError('诊断引用了不可用的证据')
        if issue.dimension == '课程匹配' and not issue.evidence_refs:
            raise ValueError('课程匹配判断缺少证据')
    return result
