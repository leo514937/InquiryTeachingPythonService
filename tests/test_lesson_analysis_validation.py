import pytest


def test_diagnosis_requires_exact_paragraph_ranges_and_authorized_evidence():
    from app.workspace.lesson_analysis import validate_diagnosis
    document = {'sections': [{'id': 's1', 'paragraphs': [{'id': 'p1', 'text': '了解垃圾分类知识。'}]}]}
    evidence = [{'evidence_id': 'e1', 'source_id': 'a'}]
    issue = {'section_id': 's1', 'paragraph_id': 'p1', 'start': 0, 'end': 8,
             'original_text': '了解垃圾分类知识', 'dimension': '教学目标', 'severity': 'medium',
             'title': '目标待明确', 'reason': '难以观察', 'suggested_text': '说明分类理由',
             'evidence_refs': ['e1']}
    result = validate_diagnosis({'issues': [issue]}, document, evidence)
    assert result.issues[0].original_text == '了解垃圾分类知识'
    for change in ({'paragraph_id': 'missing'}, {'start': 1}, {'evidence_refs': ['unselected']},
                   {'section_id': 'missing'}, {'end': 100}):
        with pytest.raises(ValueError):
            validate_diagnosis({'issues': [{**issue, **change}]}, document, evidence)


def test_course_matching_without_evidence_is_rejected():
    from app.workspace.lesson_analysis import validate_diagnosis
    document = {'sections': [{'id': 's', 'paragraphs': [{'id': 'p', 'text': '目标'}]}]}
    issue = {'section_id': 's', 'paragraph_id': 'p', 'start': 0, 'end': 2,
             'original_text': '目标', 'dimension': '课程匹配', 'severity': 'low',
             'title': '匹配', 'reason': '说明', 'suggested_text': '建议', 'evidence_refs': []}
    with pytest.raises(ValueError):
        validate_diagnosis({'issues': [issue]}, document, [])
