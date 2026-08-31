from __future__ import annotations

import datetime as dt
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from docx import Document
from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import CurriculumChunkModel


SUPPORTED_CURRICULUM_EXTENSIONS = {".md", ".txt", ".pdf", ".docx"}
TOKEN_STOPWORDS = {
    "的",
    "了",
    "和",
    "与",
    "及",
    "在",
    "是",
    "为",
    "对",
    "将",
    "中",
    "可",
    "要",
    "把",
}
EDUCATION_LEVEL_KEYWORDS = {
    "primary": {
        "小学",
        "一年级",
        "二年级",
        "三年级",
        "四年级",
        "五年级",
        "六年级",
    },
    "middle": {"初中", "七年级", "八年级", "九年级"},
    "high": {"高中", "高一", "高二", "高三"},
}


class CurriculumFileError(ValueError):
    pass


@dataclass(frozen=True)
class CurriculumSearchResult:
    chunk_id: int
    source: str
    source_index: int
    content: str
    score: float
    chunk_ids: tuple[int, ...]


class CurriculumKnowledgeService:
    def __init__(self, db: Session, settings: Settings | None = None):
        self.db = db
        self.settings = settings or get_settings()

    def ingest_file(self, path: Path, *, source: str | None = None) -> int:
        path = path.resolve()
        extension = path.suffix.lower()
        if extension not in SUPPORTED_CURRICULUM_EXTENSIONS:
            supported = ", ".join(sorted(SUPPORTED_CURRICULUM_EXTENSIONS))
            raise CurriculumFileError(f"仅支持以下课标文件格式：{supported}")
        if not path.is_file():
            raise CurriculumFileError(f"课标文件不存在：{path}")

        content = self.extract_text(path)
        return self.ingest(source or path.name, content)

    def ingest(self, source: str, content: str) -> int:
        normalized_source = source.replace("\\", "/").strip()
        if not normalized_source:
            raise CurriculumFileError("课标来源名称不能为空")

        normalized_content = normalize_text(content)
        if not normalized_content:
            raise CurriculumFileError("课标文件中未提取到可用文字；扫描版 PDF 暂不支持 OCR")

        overlap = min(
            self.settings.curriculum_chunk_overlap,
            self.settings.curriculum_chunk_size - 1,
        )
        chunks = chunk_text(
            normalized_content,
            size=self.settings.curriculum_chunk_size,
            overlap=overlap,
        )
        if not chunks:
            raise CurriculumFileError("课标文件无法切分出有效内容")

        self.db.query(CurriculumChunkModel).filter(
            CurriculumChunkModel.source == normalized_source
        ).delete(synchronize_session=False)
        timestamp = now_iso()
        self.db.add_all(
            [
                CurriculumChunkModel(
                    source=normalized_source,
                    source_index=index,
                    content=chunk,
                    created_at=timestamp,
                )
                for index, chunk in enumerate(chunks)
            ]
        )
        self.db.flush()
        return len(chunks)

    def retrieve(self, query: str, top_k: int | None = None) -> list[CurriculumSearchResult]:
        query = query.strip()
        if not query:
            return []

        chunks = (
            self.db.query(CurriculumChunkModel)
            .order_by(CurriculumChunkModel.source, CurriculumChunkModel.source_index)
            .all()
        )
        if not chunks:
            return []

        scores = bm25_scores(query, chunks)
        if not scores:
            return []

        maximum = max(scores.values()) or 1.0
        query_levels = detect_education_levels(query)
        ranked: list[tuple[CurriculumChunkModel, float]] = []
        for chunk in chunks:
            base_score = scores.get(chunk.id, 0.0)
            if base_score <= 0:
                continue
            chunk_levels = detect_education_levels(f"{chunk.source}\n{chunk.content}")
            if query_levels and chunk_levels and query_levels.isdisjoint(chunk_levels):
                continue
            score = base_score
            if self.settings.curriculum_rerank_enabled:
                normalized_base = base_score / maximum
                score = (
                    normalized_base * 0.65
                    + query_token_coverage(query, chunk.content) * 0.25
                    + phrase_score(query, chunk.content) * 0.10
                )
            ranked.append((chunk, score))

        ranked.sort(key=lambda item: (-item[1], item[0].source, item[0].source_index))
        candidates = ranked[: self.settings.curriculum_candidate_k]
        limit = max(1, top_k or self.settings.curriculum_top_k)
        selected = select_diverse_anchors(candidates, limit)
        chunk_map = {(chunk.source, chunk.source_index): chunk for chunk in chunks}

        results: list[CurriculumSearchResult] = []
        for anchor, score in selected:
            neighbors = [
                chunk_map.get((anchor.source, index))
                for index in range(anchor.source_index - 1, anchor.source_index + 2)
            ]
            neighbors = [item for item in neighbors if item is not None]
            results.append(
                CurriculumSearchResult(
                    chunk_id=anchor.id,
                    source=anchor.source,
                    source_index=anchor.source_index,
                    content="\n\n".join(item.content for item in neighbors),
                    score=round(score, 6),
                    chunk_ids=tuple(item.id for item in neighbors),
                )
            )
        return results

    @staticmethod
    def extract_text(path: Path) -> str:
        extension = path.suffix.lower()
        try:
            if extension in {".md", ".txt"}:
                return extract_plain_text(path)
            if extension == ".pdf":
                return extract_pdf(path)
            if extension == ".docx":
                return extract_docx(path)
        except CurriculumFileError:
            raise
        except Exception as exc:
            raise CurriculumFileError(f"课标文件解析失败：{path.name}") from exc
        raise CurriculumFileError(f"不支持的课标文件格式：{extension}")


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat()


def chunk_text(content: str, *, size: int, overlap: int) -> list[str]:
    text = normalize_text(content)
    if not text:
        return []

    chunks: list[str] = []
    start = 0
    length = len(text)
    boundary_chars = "\n。！？；.!?;"
    minimum_boundary = max(1, int(size * 0.6))

    while start < length:
        target = min(length, start + size)
        end = target
        if target < length:
            window = text[start + minimum_boundary : target]
            boundary = max((window.rfind(char) for char in boundary_chars), default=-1)
            if boundary >= 0:
                end = start + minimum_boundary + boundary + 1

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= length:
            break
        start = max(start + 1, end - overlap)

    return chunks


def bm25_scores(query: str, chunks: list[CurriculumChunkModel]) -> dict[int, float]:
    query_terms = Counter(tokenize(query))
    if not query_terms:
        return {}

    documents: list[tuple[int, Counter[str], int]] = []
    document_frequencies: Counter[str] = Counter()
    for chunk in chunks:
        token_counts = Counter(tokenize(chunk.content))
        documents.append((chunk.id, token_counts, sum(token_counts.values())))
        document_frequencies.update(token_counts.keys())

    average_length = sum(item[2] for item in documents) / len(documents) or 1.0
    total_documents = len(documents)
    scores: dict[int, float] = {}
    k1 = 1.5
    b = 0.75

    for chunk_id, token_counts, document_length in documents:
        score = 0.0
        length_normalizer = k1 * (1.0 - b + b * document_length / average_length)
        for term, query_frequency in query_terms.items():
            term_frequency = token_counts.get(term, 0)
            if term_frequency == 0:
                continue
            document_frequency = document_frequencies[term]
            inverse_frequency = math.log(
                1.0 + (total_documents - document_frequency + 0.5) / (document_frequency + 0.5)
            )
            query_boost = 1.0 + math.log(query_frequency)
            score += (
                inverse_frequency
                * query_boost
                * (term_frequency * (k1 + 1.0))
                / (term_frequency + length_normalizer)
            )
        if score > 0:
            scores[chunk_id] = score
    return scores


def select_diverse_anchors(
    candidates: list[tuple[CurriculumChunkModel, float]],
    limit: int,
) -> list[tuple[CurriculumChunkModel, float]]:
    selected: list[tuple[CurriculumChunkModel, float]] = []
    deferred: list[tuple[CurriculumChunkModel, float]] = []
    for item in candidates:
        chunk = item[0]
        overlaps = any(
            chosen.source == chunk.source
            and abs(chosen.source_index - chunk.source_index) <= 1
            for chosen, _ in selected
        )
        if overlaps:
            deferred.append(item)
        else:
            selected.append(item)
        if len(selected) >= limit:
            return selected

    for item in deferred:
        selected.append(item)
        if len(selected) >= limit:
            break
    return selected


def tokenize(text: str) -> list[str]:
    raw_tokens = re.findall(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]", text.lower())
    tokens = [token for token in raw_tokens if token not in TOKEN_STOPWORDS]
    chinese = "".join(char for char in text.lower() if "\u4e00" <= char <= "\u9fff")
    tokens.extend(chinese[index : index + 2] for index in range(max(0, len(chinese) - 1)))
    return tokens


def detect_education_levels(text: str) -> set[str]:
    return {
        level
        for level, keywords in EDUCATION_LEVEL_KEYWORDS.items()
        if any(keyword in text for keyword in keywords)
    }


def query_token_coverage(query: str, content: str) -> float:
    query_tokens = set(tokenize(query))
    if not query_tokens:
        return 0.0
    return len(query_tokens & set(tokenize(content))) / len(query_tokens)


def phrase_score(query: str, content: str) -> float:
    query_parts = [
        compact_text(part)
        for part in re.split(r"[\n，。！？、；：,.!?;:]", query)
        if len(compact_text(part)) >= 2
    ]
    if not query_parts:
        return 0.0
    compact_content = compact_text(content)
    return sum(1 for part in query_parts if part in compact_content) / len(query_parts)


def compact_text(text: str) -> str:
    return re.sub(r"\s+", "", text.lower())


def extract_plain_text(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise CurriculumFileError("TXT/MD 文件编码无法识别，请使用 UTF-8 或 GB18030")


def extract_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    if reader.is_encrypted and reader.decrypt("") == 0:
        raise CurriculumFileError("PDF 已加密，无法读取")
    pages = [normalize_text(page.extract_text() or "") for page in reader.pages]
    pages = remove_repeated_page_edges(pages)
    return "\n\n".join(page for page in pages if page)


def remove_repeated_page_edges(pages: list[str]) -> list[str]:
    if len(pages) < 2:
        return pages

    page_lines = [[line.strip() for line in page.splitlines() if line.strip()] for page in pages]
    edge_counts: Counter[str] = Counter()
    for lines in page_lines:
        if lines:
            edge_counts.update({lines[0], lines[-1]})
    threshold = max(2, math.ceil(len(page_lines) * 0.5))
    repeated_edges = {line for line, count in edge_counts.items() if count >= threshold}

    cleaned_pages = []
    for lines in page_lines:
        if lines and lines[0] in repeated_edges:
            lines = lines[1:]
        if lines and lines[-1] in repeated_edges:
            lines = lines[:-1]
        cleaned_pages.append("\n".join(lines))
    return cleaned_pages


def extract_docx(path: Path) -> str:
    document = Document(str(path))
    blocks = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            if any(cells):
                blocks.append(" | ".join(cells))
    return "\n".join(blocks)


def normalize_text(text: str) -> str:
    text = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
