"""Subject strategies influence teaching without granting data access."""
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class Strategy(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(pattern=r'^[a-z_]+$')
    subject: str = Field(max_length=100)
    phases: list[str] = Field(min_length=1, max_length=10)
    guidance: str = Field(max_length=1000)


@lru_cache(maxsize=1)
def load_strategies():
    payload = yaml.safe_load(Path(__file__).with_name('teaching_strategies.yaml').read_text(encoding='utf-8'))
    if payload.get('version') != 1:
        raise ValueError('invalid strategy version')
    result = [Strategy.model_validate(item) for item in payload['strategies']]
    if len({item.id for item in result}) != len(result) or not any(item.id == 'general_inquiry' for item in result):
        raise ValueError('invalid strategy configuration')
    return result


def select_strategy(subject: str) -> dict:
    strategies = load_strategies()
    selected = next((item for item in strategies if item.subject and item.subject == subject), None)
    return (selected or next(item for item in strategies if item.id == 'general_inquiry')).model_dump()
