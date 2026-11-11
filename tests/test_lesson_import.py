from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from docx import Document


def test_import_docx_keeps_paragraphs_and_table_in_document_order():
    from app.workspace.lesson_import import extract_lesson_file
    document = Document()
    document.add_paragraph('教学目标')
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = '目标一'
    table.cell(0, 1).text = '观察'
    document.add_paragraph('教学过程')
    data = BytesIO()
    document.save(data)
    assert extract_lesson_file('教案.docx', data.getvalue()) == '教学目标\n目标一\t观察\n教学过程'


def test_import_txt_utf8_and_reject_unsupported_or_broken_files():
    from app.workspace.lesson_import import extract_lesson_file, LessonImportError
    assert extract_lesson_file('教案.txt', '教学目标\n探究'.encode('utf-8-sig')) == '教学目标\n探究'
    for name, data in [('旧版.doc', b'not-doc'), ('教案.docx', b'not-a-docx'), ('空.txt', b''), ('坏.txt', b'\xff')]:
        with pytest.raises(LessonImportError):
            extract_lesson_file(name, data)


def test_import_rejects_expanded_archive_above_limit():
    from app.workspace.lesson_import import extract_lesson_file, LessonImportError
    data = BytesIO()
    with ZipFile(data, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('word/document.xml', b'x' * (20 * 1024 * 1024 + 1))
    with pytest.raises(LessonImportError, match='过大'):
        extract_lesson_file('大文件.docx', data.getvalue())


def test_import_rejects_text_that_cannot_be_saved_without_truncation():
    from app.workspace.lesson_import import extract_lesson_file, LessonImportError
    with pytest.raises(LessonImportError, match='长度'):
        extract_lesson_file('大.txt', ('字' * 100001).encode())
    with pytest.raises(LessonImportError, match='段落'):
        extract_lesson_file('长.txt', ('字' * 10001).encode())


def test_import_endpoint_checks_teacher_role_and_returns_parsed_text(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from app.workspace import api
    calls = []
    monkeypatch.setattr(api, 'resolve_workspace_role', lambda db, user, role: calls.append((user.id, role)))
    async def run_inline(fn, *args):
        return fn(*args)
    monkeypatch.setattr(asyncio, 'to_thread', run_inline)
    class Upload:
        filename = '教案.txt'
        async def read(self, size):
            return '教学目标'.encode()
        async def close(self):
            pass
    task = api.parse_lesson_import(Upload(), object(), SimpleNamespace(id='teacher'))
    with pytest.raises(StopIteration) as finished:
        task.send(None)
    assert finished.value.value == {'data': {'text': '教学目标'}}
    assert calls == [('teacher', 'teacher')]
