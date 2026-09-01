from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="下载本地 Embedding 模型并重建课标 Chroma 索引。",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="使用已经存在的本地模型，不执行下载。",
    )
    parser.add_argument(
        "--skip-rebuild",
        action="store_true",
        help="只准备模型，不重建课标向量索引。",
    )
    return parser.parse_args()


def download_model(repo_id: str, destination: Path) -> None:
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise RuntimeError(
            "缺少 huggingface-hub，请先安装 requirements.txt"
        ) from exc

    destination.mkdir(parents=True, exist_ok=True)
    print(f"正在准备模型：{repo_id}")
    print(f"本地目录：{destination}")
    snapshot_download(
        repo_id=repo_id,
        local_dir=str(destination),
    )


def main() -> int:
    args = parse_args()

    from app.core.config import get_settings
    from app.db.database import Base, SessionLocal, engine
    from app.db.migrations import ensure_schema_compatibility
    from app.services.curriculum_knowledge_service import CurriculumKnowledgeService

    settings = get_settings()
    Base.metadata.create_all(bind=engine)
    ensure_schema_compatibility()

    if not args.skip_download:
        download_model(
            settings.curriculum_embedding_model,
            settings.curriculum_embedding_model_dir,
        )
    elif not settings.curriculum_embedding_model_dir.is_dir():
        print(f"模型目录不存在：{settings.curriculum_embedding_model_dir}")
        return 1

    with SessionLocal() as db:
        service = CurriculumKnowledgeService(db, settings)
        if not args.skip_rebuild:
            if not settings.curriculum_vector_enabled:
                print("CURRICULUM_VECTOR_ENABLED=false，未重建向量索引。")
                return 1
            try:
                count = service.rebuild_vector_index()
                db.commit()
                print(f"向量索引重建完成：{count} 个片段。")
            except Exception as exc:
                db.commit()
                print(f"向量索引重建失败：{exc}")
                return 1
        status = service.status()
        db.commit()

    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0 if status.get("available") else 1


if __name__ == "__main__":
    raise SystemExit(main())
