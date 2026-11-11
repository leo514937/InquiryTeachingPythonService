
import json

import pytest

from app.workspace.capabilities.builtin import build_registry
from app.workspace.integrations.llm import ModelUnavailable


class SequenceModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []
    def complete(self, system, message):
        self.prompts.append((system, message))
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return json.dumps(value, ensure_ascii=False)


def invoke(model, capability):
    return build_registry(model).invoke(capability, {}, {
        'goal': '设计光的反射探究教学', 'parameters': {}, 'dependencies': {},
    })


def test_requirements_retries_when_model_returns_unpermitted_objects():
    model = SequenceModel([
        {'summary': '需求', 'artifacts': [{'type': 'lesson_plan', 'content': {'title': '计划'}}], 'warnings': []},
        {'summary': '需求', 'artifacts': [], 'warnings': []},
    ])
    result = invoke(model, 'requirements.analyze@1')
    assert result['artifacts'] == []
    assert len(model.prompts) == 2
    assert 'artifacts' in model.prompts[1][1]


@pytest.mark.parametrize('capability,kind', [
    ('goals.compose@1', 'LearningGoal'),
    ('inquiry.design@1', 'InquiryQuestion'),
    ('activity.design@1', 'Experiment'),
    ('assessment.design@1', 'Assessment'),
])
def test_artifact_producer_retries_empty_output(capability, kind):
    model = SequenceModel([
        {'summary': '完成', 'artifacts': [], 'warnings': []},
        {'summary': '完成', 'artifacts': [{'type': kind, 'content': {'title': '教学对象'}}], 'warnings': []},
    ])
    result = invoke(model, capability)
    assert result['artifacts'][0]['type'] == kind
    assert len(model.prompts) == 2


def test_invalid_model_output_fails_after_bounded_attempts():
    invalid = {'summary': '无法完成', 'artifacts': [], 'warnings': []}
    model = SequenceModel([invalid, invalid])
    with pytest.raises(ValueError):
        invoke(model, 'goals.compose@1')
    assert len(model.prompts) == 2


def test_model_unavailability_is_not_misrepresented_as_validation_repair():
    model = SequenceModel([ModelUnavailable('unavailable', retryable=True)])
    with pytest.raises(ModelUnavailable):
        invoke(model, 'requirements.analyze@1')
    assert len(model.prompts) == 1



def test_model_output_failure_has_a_specific_safe_error_category():
    from app.workspace.runtime.runs import _safe_error_code
    from app.workspace.capabilities.builtin import ModelOutputInvalid
    assert _safe_error_code(ModelOutputInvalid('bad output')) == 'model_output_invalid'

