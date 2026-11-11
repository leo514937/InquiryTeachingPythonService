"""Bounded, text-only parsing for teacher-supplied lesson documents."""
from io import BytesIO
from pathlib import PurePath
from zipfile import ZipFile

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_EXPANDED_BYTES = 20 * 1024 * 1024


class LessonImportError(ValueError):
    pass


def extract_lesson_file(filename: str, data: bytes) -> str:
    extension = PurePath(filename.lower()).suffix
    if extension not in ('.txt', '.docx'):
        raise LessonImportError('仅支持 TXT 或 DOCX；旧版 DOC 请先转换为 DOCX')
    if not data:
        raise LessonImportError('文件为空')
    if len(data) > MAX_FILE_BYTES:
        raise LessonImportError('文件不能超过 5 MB')
    if extension == '.txt':
        try:
            text = data.decode('utf-8-sig')
        except UnicodeDecodeError as exc:
            raise LessonImportError('文本编码无法识别，请使用 UTF-8') from exc
    else:
        try:
            with ZipFile(BytesIO(data)) as archive:
                entries = archive.infolist()
                if sum(item.file_size for item in entries) > MAX_EXPANDED_BYTES:
                    raise LessonImportError('Word 文件解压后过大')
                if any(item.flag_bits & 1 for item in entries):
                    raise LessonImportError('不支持加密的 Word 文件')
            document = Document(BytesIO(data))
            blocks = []
            for child in document.element.body.iterchildren():
                if child.tag == qn('w:p'):
                    blocks.append(Paragraph(child, document).text)
                elif child.tag == qn('w:tbl'):
                    table = Table(child, document)
                    for row in table.rows:
                        blocks.append('\t'.join(cell.text.replace('\n', '；') for cell in row.cells))
            text = '\n'.join(blocks)
        except LessonImportError:
            raise
        except Exception as exc:
            raise LessonImportError('Word 解析失败，请确认文件为未损坏的 DOCX') from exc
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    if not text.strip():
        raise LessonImportError('未提取到正文，请检查文件内容')
    if len(text) > 100000:
        raise LessonImportError('教案正文长度超过 100000 字，请缩短后重试')
    lines = text.split('\n')
    if len(lines) > 1000 or any(len(line) > 10000 for line in lines):
        raise LessonImportError('教案段落数量或长度超过限制')
    return text
