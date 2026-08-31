from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.db.database import Base, SessionLocal, engine
from app.services.curriculum_knowledge_service import (
    SUPPORTED_CURRICULUM_EXTENSIONS,
    CurriculumKnowledgeService,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="导入本地课标文件并建立 BM25 检索数据。",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=str(get_settings().curriculum_dir),
        help="课标文件或目录，默认读取 CURRICULUM_DIR。",
    )
    return parser.parse_args()


def collect_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path] if path.suffix.lower() in SUPPORTED_CURRICULUM_EXTENSIONS else []
    if not path.is_dir():
        return []
    return sorted(
        item
        for item in path.rglob("*")
        if item.is_file() and item.suffix.lower() in SUPPORTED_CURRICULUM_EXTENSIONS
    )


def main() -> int:
    args = parse_args()
    import_path = Path(args.path).expanduser().resolve()
    files = collect_files(import_path)
    if not files:
        print(f"未找到可导入的课标文件：{import_path}")
        return 1

    Base.metadata.create_all(bind=engine)
    imported_files = 0
    imported_chunks = 0
    errors: list[str] = []
    source_root = import_path if import_path.is_dir() else import_path.parent

    with SessionLocal() as db:
        service = CurriculumKnowledgeService(db)
        for file_path in files:
            source = file_path.relative_to(source_root).as_posix()
            try:
                count = service.ingest_file(file_path, source=source)
                db.commit()
                imported_files += 1
                imported_chunks += count
                print(f"已导入：{source}（{count} 个片段）")
            except Exception as exc:
                db.rollback()
                errors.append(f"{source}: {exc}")
                print(f"导入失败：{source}（{exc}）")

    print(f"导入完成：{imported_files} 个文件，{imported_chunks} 个片段。")
    if errors:
        print(f"失败文件：{len(errors)} 个。")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
