"""Server-owned scene configuration and bounded, deterministic query rewriting."""
from functools import lru_cache
from pathlib import Path
import re

import yaml
from pydantic import BaseModel, ConfigDict, Field


class Scene(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(pattern=r'^[a-z][a-z0-9_]{0,63}$')
    version: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(max_length=500)
    intents: list[str] = Field(max_length=5)
    source_groups: list[str] = Field(default_factory=list, max_length=20)
    incompatible_with: list[str] = Field(default_factory=list, max_length=100)
    retrieval_profile: str = Field(default='existing_hybrid@1', max_length=100)
    default_strategy: str = Field(default='general_inquiry@1', max_length=100)
    capability_profile: str = Field(default='minimal_lesson@1', max_length=100)


class Catalog(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(ge=1)
    scenes: list[Scene] = Field(max_length=100)
    source_groups: dict[str, list[str]] = Field(default_factory=dict)


INTENT_LABELS = {
    'curriculum': '课程目标与教材依据',
    'teaching_case': '探究式教学案例',
    'environment': '教学情境',
    'resources': '教学资源与安全条件',
    'assessment': '学习评价方法',
}


@lru_cache(maxsize=1)
def load_catalog() -> Catalog:
    payload = yaml.safe_load(Path(__file__).with_name('scene_catalog.yaml').read_text(encoding='utf-8'))
    catalog = Catalog.model_validate(payload)
    ids = [item.id for item in catalog.scenes]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate scene id')
    for item in catalog.scenes:
        if (set(item.intents) - set(INTENT_LABELS) or set(item.source_groups) - set(catalog.source_groups)
                or set(item.incompatible_with) - set(ids) or item.id in item.incompatible_with):
            raise ValueError('invalid scene configuration')
    return catalog


def load_scenes() -> dict[str, Scene]:
    return {scene.id: scene for scene in load_catalog().scenes}


def rewrite_queries(goal: str, teaching_context: dict, scene_ids: list[str], intents: list[str]) -> list[dict]:
    scenes = load_scenes()
    if len(scene_ids) > 3 or len(set(scene_ids)) != len(scene_ids) or set(scene_ids) - set(scenes):
        raise ValueError('invalid scenes')
    if any(set(scenes[scene_id].incompatible_with) & set(scene_ids) for scene_id in scene_ids):
        raise ValueError('所选课程场景存在冲突')
    if set(intents) - set(INTENT_LABELS):
        raise ValueError('invalid retrieval intent')
    topic = re.sub(r'\s+', ' ', goal).strip()[:300]
    grade = str(teaching_context.get('grade') or '').strip()[:100]
    subject = str(teaching_context.get('subject') or '').strip()[:100]
    return [{'intent': intent, 'query': ' '.join(part for part in (grade, subject, topic, INTENT_LABELS[intent]) if part),
             'scene_ids': list(scene_ids)} for intent in dict.fromkeys(intents)][:5]
