from app.workspace.orchestrator.evaluator import evaluate_completion


def make_outputs(activity_ids, assessment_ids):
    return {
        'goals': {'artifacts': [{'type': 'LearningGoal', 'content': {'title': '目标', 'description': '观察'}}], 'artifact_refs': [{'id': 'goal-1', 'version': 1}]},
        'question': {'artifacts': [{'type': 'InquiryQuestion', 'content': {'title': '问题', 'question': '如何观察？'}}], 'artifact_refs': [{'id': 'q', 'version': 1}]},
        'activity': {'artifacts': [{'type': 'InquiryActivity', 'content': {'title': '活动', 'description': '观察', 'goal_ids': activity_ids}}], 'artifact_refs': [{'id': 'a', 'version': 1}]},
        'assessment': {'artifacts': [{'type': 'Assessment', 'content': {'title': '评价', 'criteria': ['观察'], 'goal_ids': assessment_ids}}], 'artifact_refs': [{'id': 'e', 'version': 1}]},
    }


def test_actual_goal_references_and_coverage_are_required():
    assert evaluate_completion('lesson', make_outputs(['goal-1'], ['goal-1']), True)[0] == 'completed'
    assert evaluate_completion('lesson', make_outputs(['goal-1'], ['fake']), True)[0] == 'waiting_review'
    assert evaluate_completion('lesson', make_outputs(['fake'], ['goal-1']), True)[0] == 'waiting_review'
    assert evaluate_completion('lesson', make_outputs(['goal-1'], ['goal-1']), False)[0] == 'waiting_review'


def test_missing_experiment_safety_or_known_hazard_requires_review():
    base = {'artifacts': [{'type': 'Experiment', 'content': {'title': '实验', 'description': '观察', 'materials': ['镜子'], 'safety_measures': ['成人监督']}}], 'artifact_refs': [{'id': 'a', 'version': 1}]}
    assert evaluate_completion('experiment', {'node': base}, True)[0] == 'completed'
    base['artifacts'][0]['content']['materials'] = ['激光']
    assert evaluate_completion('experiment', {'node': base}, True)[0] == 'waiting_review'
