"""Trusted server-owned profiles; compiled into the existing validated Plan."""
from functools import lru_cache
from pathlib import Path
import copy

import yaml


@lru_cache(maxsize=1)
def _profiles():
    payload = yaml.safe_load(Path(__file__).with_name('profiles.yaml').read_text(encoding='utf-8'))
    if not isinstance(payload, dict) or payload.get('version') != 1 or not isinstance(payload.get('profiles'), dict):
        raise ValueError('invalid profile configuration')
    return payload['profiles']


def load_profile(name: str) -> dict:
    from app.workspace.orchestrator.planner import validate_plan
    profile = _profiles().get(name)
    if not isinstance(profile, dict) or profile.get('version') != 1:
        raise ValueError('unknown profile')
    nodes = profile.get('nodes')
    validate_plan({'version': 1, 'goal': 'profile validation', 'nodes': nodes})
    return copy.deepcopy(profile)
