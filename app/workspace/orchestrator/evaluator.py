"""Deterministic checks complementing the model's teaching review."""
import json
from app.workspace.artifacts.types import ACTIVITY_TYPES

APPROVABLE_REVIEW_REASONS = frozenset({'实验可能涉及安全风险', '模型提示需要安全审核'})


def risk_only_review(reason):
    suffix = '，请教师审核。'
    if not reason.endswith(suffix):
        return False
    reasons = set(reason[:-len(suffix)].split('；'))
    return bool(reasons) and reasons.issubset(APPROVABLE_REVIEW_REASONS)


def evaluate_completion(mode, outputs, evaluation_covered):
    artifacts = [artifact for result in outputs.values() for artifact in result.get('artifacts', [])]
    types = {item.get('type') for item in artifacts}
    reasons = []
    if mode != 'replan':
        required = {'Experiment'} if mode == 'experiment' else {'LearningGoal', 'InquiryQuestion', 'Assessment'}
        if not required.issubset(types) or (mode == 'lesson' and not (ACTIVITY_TYPES & types)):
            return 'failed', ['教学对象不完整']
    goal_ids = set()
    for result in outputs.values():
        refs = result.get('artifact_refs', [])
        for artifact, ref in zip(result.get('artifacts', []), refs):
            if artifact.get('type') == 'LearningGoal' and isinstance(ref, dict) and isinstance(ref.get('id'), str):
                goal_ids.add(ref['id'])
    covered = {'activity': set(), 'Assessment': set()}
    for artifact in artifacts:
        content, kind = artifact.get('content', {}), artifact.get('type')
        if kind == 'Experiment' and not all(content.get(field) for field in ('description', 'materials', 'safety_measures')):
            reasons.append('实验描述、材料或安全措施不完整')
        if kind in {'LearningGoal', 'InquiryActivity', 'Assessment'} and not (content.get('description') or content.get('criteria')):
            reasons.append('教学对象内容不完整')
        if kind == 'InquiryQuestion' and not (content.get('question') or content.get('description')):
            reasons.append('探究问题不完整')
        if (kind in (ACTIVITY_TYPES - {'Experiment', 'EvidenceRecord'}) or kind == 'Assessment') and mode == 'lesson':
            refs = content.get('goal_ids')
            if not isinstance(refs, list) or not refs or not all(isinstance(ref, str) and ref in goal_ids for ref in refs):
                reasons.append('活动或评价引用了不存在的学习目标')
            else:
                covered['activity' if kind in ACTIVITY_TYPES else 'Assessment'].update(refs)
    if mode == 'lesson' and (not goal_ids or any(not goal_ids.issubset(ids) for ids in covered.values())):
        reasons.append('学习目标尚未被活动和评价完整覆盖')
    if any(word in json.dumps(artifacts, ensure_ascii=False).lower() for word in ('激光', '明火', '有毒', '腐蚀', '高压', 'laser', 'open flame')):
        reasons.append('实验可能涉及安全风险')
    if not evaluation_covered:
        reasons.append('自动质量检查未覆盖全部教学对象')
    warnings = [warning for result in outputs.values() for warning in result.get('warnings', [])]
    if any(any(word in warning.lower() for word in ('安全', '危险', '风险', 'risk', 'safety')) for warning in warnings):
        reasons.append('模型提示需要安全审核')
    return ('waiting_review', list(dict.fromkeys(reasons))) if reasons else ('completed', [])
