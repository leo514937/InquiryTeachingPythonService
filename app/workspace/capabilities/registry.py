from dataclasses import dataclass
from typing import Callable

from pydantic import BaseModel


@dataclass(frozen=True)
class Capability:
    id: str
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    handler: Callable
    timeout_seconds: int = 90
    permission: str = 'teacher'
    side_effects: bool = False
    parallel: bool = True
    applicability: str = '通用教学任务，按规划目标选择'
    retry_policy: str = '模型暂不可用时由运行时进行有界重试'
    idempotency: str = '结果由运行时按节点事务提交'

    @property
    def version(self):
        suffix = self.id.rpartition('@')[2]
        return int(suffix) if suffix.isdecimal() else None


class CapabilityRegistry:
    def __init__(self):
        self._items = {}

    def register(self, capability):
        if capability.id in self._items:
            raise ValueError('duplicate capability')
        self._items[capability.id] = capability

    def get(self, capability_id):
        if capability_id not in self._items:
            raise ValueError('unknown capability')
        return self._items[capability_id]

    def invoke(self, capability_id, context, payload):
        capability = self.get(capability_id)
        data = capability.input_schema.model_validate(payload)
        result = capability.handler(context, data)
        return capability.output_schema.model_validate(result).model_dump(mode='json')
