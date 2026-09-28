import asyncio
import gzip
import json
import os
import shutil
import tempfile
import unittest
import uuid
import zipfile
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker


TEST_DIR = Path(tempfile.mkdtemp(prefix="inquiry-agent-architecture-"))
TEST_DB = TEST_DIR / "agents.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["UPLOAD_DIR"] = str(TEST_DIR / "uploads")
os.environ["KNOWLEDGE_SOURCE_DIR"] = str(TEST_DIR / "knowledge_sources")
os.environ["LLM_API_KEY"] = ""
os.environ["AGENT_CONFIG_PATH"] = "app/agents/config/agents.yaml"
os.environ["CURRICULUM_VECTOR_ENABLED"] = "false"
os.environ["ECOLOGY_GRAPH_AUTO_SYNC_ENABLED"] = "false"
os.environ["GLOBI_IMPORT_WORKER_ENABLED"] = "false"
os.environ["FRONTEND_ORIGIN"] = (
    "http://127.0.0.1:5173,"
    "http://localhost:5173,"
    "http://152.136.39.252:5173"
)

from fastapi.testclient import TestClient
from docx import Document
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.core.config import get_settings
from app.agents.registry import AgentRegistry, get_agent_registry
from app.agents.service import ExpertAgentService
from app.db.database import Base, SessionLocal, engine
from app.db.migrations import ensure_schema_compatibility
from app.db.models import (
    ChatTurnModel,
    CurriculumChunkModel,
    CurriculumSourceModel,
    CurriculumSourceAgentPermissionModel,
    DraftProposalModel,
    EcologyGraphSourceStateModel,
    EcologyGraphSyncJobModel,
    GlobiImportRunModel,
    GlobiInteractionModel,
    KnowledgeEntityModel,
    KnowledgeEntityMentionModel,
    KnowledgeEntitySourceModel,
    KnowledgeEntityTaxonModel,
    KnowledgeRelationEvidenceModel,
    KnowledgeRelationGlobiEvidenceModel,
    KnowledgeRelationModel,
    MessageModel,
    RagRecordModel,
    SessionFileModel,
    SessionModel,
)
from app.main import app
from app.services.auth_service import register_user
from app.services.chat_interrupt_service import chat_interruptions
from app.services.context_service import ContextService
from app.services.curriculum_knowledge_service import (
    CurriculumKnowledgeService,
    bm25_scores,
    chunk_policy_text,
    detect_subjects,
    policy_structural_units,
)
from app.services.curriculum_vector_service import CurriculumVectorHit
from app.services.curriculum_permission_service import CurriculumPermissionService
from app.services.graph_rag_service import GraphRagService
from app.services.ecology_graph_sync_service import (
    EcologyGraphJobProcessor,
    EcologyGraphSyncService,
)
from app.services.ecology_lightrag_service import (
    EcologyExtractionResult,
    ExtractedEntity,
    ExtractedRelation,
)
from app.services.knowledge_graph_service import KnowledgeGraphService
from app.services.globi_import_service import (
    GlobiImportOptions,
    GlobiImportService,
    GlobiImportWorker,
)
from app.services.globi_runtime_service import GlobiRuntimeService
from app.services.prompt_service import PromptService
from app.services.session_file_service import SessionFileService
from app.workflow.flows import get_flow


EXPECTED_EXPERT_IDS = [
    "insect_agent",
    "nature_agent",
    "mathematics_teacher_agent",
    "safety_agent",
    "physics_teacher_agent",
]

EXPECTED_INSECT_HOTEL_STAGES = [
    "natural_materials",
    "habitat_needs",
    "structure_design",
    "build_and_sensing",
    "settlement_observation",
    "iteration_sharing",
]


def make_text_pdf(text: str) -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_ref = writer._add_object(font)
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})}
    )
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    writer.write(output)
    return output.getvalue()


def make_docx() -> bytes:
    output = BytesIO()
    document = Document()
    document.add_paragraph("DOCX_PARAGRAPH_MARKER")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "DOCX_TABLE_LEFT"
    table.cell(0, 1).text = "DOCX_TABLE_RIGHT"
    document.save(output)
    return output.getvalue()


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        event_name = "message"
        data_lines = []
        for line in block.splitlines():
            if line.startswith("event:"):
                event_name = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].strip())
        if data_lines:
            events.append((event_name, json.loads("\n".join(data_lines))))
    return events


def make_curriculum_bundle(payload: dict) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "curriculum.json",
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        )
    return output.getvalue()


class FakeCurriculumVectorStore:
    def __init__(self, *, available: bool = True, error: str = ""):
        self.available = available
        self.error = error
        self.rows = []
        self.deleted_sources = []

    def index_chunks(self, chunks):
        if not self.available:
            raise RuntimeError(self.error or "fake vector unavailable")
        self.rows.extend(chunks)
        return len(chunks)

    def delete_source(self, source):
        self.deleted_sources.append(source)
        self.rows = [row for row in self.rows if row.source != source]

    def query(self, _query, top_k, allowed_sources=None):
        if not self.available:
            raise RuntimeError(self.error or "fake vector unavailable")
        rows = self.rows
        if allowed_sources is not None:
            rows = [row for row in rows if row.source in allowed_sources]
        return [
            CurriculumVectorHit(chunk_id=int(row.id), score=0.95 - index * 0.05)
            for index, row in enumerate(rows[:top_k])
        ]

    def rebuild(self, chunks):
        if not self.available:
            raise RuntimeError(self.error or "fake vector unavailable")
        self.rows = list(chunks)
        return len(chunks)

    def snapshot(self):
        return None

    def status(self):
        return {
            "enabled": True,
            "required": False,
            "available": self.available,
            "dependency_ready": self.available,
            "model": "fake-local-model",
            "model_dir": "fake",
            "device": "cpu",
            "vector_dir": "fake",
            "collection": "curriculum_chunks",
            "vector_count": len(self.rows),
            "rebuild_required": False,
            "error": self.error,
        }


class FakeEcologyExtractor:
    def __init__(self, result: EcologyExtractionResult):
        self.result = result
        self.calls = []
        self.deleted_sources = []

    async def extract(self, *, source: str, checksum: str, chunks: list[str]):
        self.calls.append((source, checksum, list(chunks)))
        return self.result

    def delete_source_artifacts(self, source: str):
        self.deleted_sources.append(source)


class AgentArchitectureApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.username = f"test_{uuid.uuid4().hex[:10]}"
        response = cls.client.post(
            "/api/auth/register",
            json={"username": cls.username, "password": "test-password-123"},
        )
        if response.status_code != 200:
            raise AssertionError(response.text)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        engine.dispose()
        shutil.rmtree(TEST_DIR, ignore_errors=True)

    def create_session(
        self,
        flow_name: str = "inquiry_7_stage",
        topic: str = "光的折射",
    ) -> tuple[str, str]:
        response = self.client.post(
            "/api/sessions",
            json={"topic": topic, "flow_name": flow_name},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        return data["id"], data["current_stage"]["id"]

    def delete_session(self, session_id: str) -> None:
        response = self.client.delete(f"/api/sessions/{session_id}")
        self.assertEqual(response.status_code, 200)

    def stream_chat(self, session_id: str, message: str):
        response = self.client.post(
            f"/api/sessions/{session_id}/chat",
            json={"type": "chat", "message": message},
        )
        self.assertEqual(response.status_code, 200)
        return response, parse_sse(response.text)

    def get_session(self, session_id: str) -> dict:
        response = self.client.get(f"/api/sessions/{session_id}")
        self.assertEqual(response.status_code, 200)
        return response.json()["data"]

    def get_messages(self, session_id: str) -> list[dict]:
        response = self.client.get(f"/api/sessions/{session_id}/messages")
        self.assertEqual(response.status_code, 200)
        return response.json()["data"]

    def upload_file(
        self,
        session_id: str,
        name: str,
        content: bytes,
        content_type: str,
    ):
        return self.client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": (name, content, content_type)},
        )

    def get_files(self, session_id: str) -> list[dict]:
        response = self.client.get(f"/api/sessions/{session_id}/files")
        self.assertEqual(response.status_code, 200)
        return response.json()["data"]

    def set_draft_mode(self, session_id: str, enabled: bool) -> dict:
        response = self.client.put(
            f"/api/sessions/{session_id}/draft-mode",
            json={"enabled": enabled},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["data"]

    def test_flows_use_main_tutor_and_experts_are_selectable(self):
        flow_response = self.client.get("/api/flows")
        self.assertEqual(flow_response.status_code, 200)
        inquiry_flow = next(
            item
            for item in flow_response.json()["data"]
            if item["name"] == "inquiry_7_stage"
        )
        self.assertTrue(all("agent_id" not in stage for stage in inquiry_flow["stages"]))
        self.assertTrue(all("expert" not in stage for stage in inquiry_flow["stages"]))
        expert_response = self.client.get("/api/experts")
        self.assertEqual(expert_response.status_code, 200)
        experts = expert_response.json()["data"]
        self.assertEqual([item["id"] for item in experts], EXPECTED_EXPERT_IDS)
        self.assertTrue(all(item["role"] and item["capabilities"] for item in experts))

    def test_agent_registry_rejects_duplicate_id_invalid_kind_and_missing_prompt(self):
        registry_dir = TEST_DIR / f"registry_{uuid.uuid4().hex}"
        registry_dir.mkdir(parents=True)
        cases = [
            """agents:\n  - {id: main_tutor, kind: main, name: 主导师, role: 主导师, prompt_file: prompts/main_tutor.md}\n  - {id: main_tutor, kind: expert, name: 重复, role: 专家, prompt_file: prompts/main_tutor.md, selectable: true}\n""",
            """agents:\n  - {id: main_tutor, kind: wrong, name: 主导师, role: 主导师, prompt_file: prompts/main_tutor.md}\n""",
            """agents:\n  - {id: main_tutor, kind: main, name: 主导师, role: 主导师, prompt_file: missing.md}\n""",
        ]
        try:
            for index, content in enumerate(cases):
                config = registry_dir / f"agents_{index}.yaml"
                config.write_text(content, encoding="utf-8")
                with self.assertRaises(RuntimeError):
                    AgentRegistry(config)
        finally:
            shutil.rmtree(registry_dir, ignore_errors=True)

    def test_permission_migration_assigns_existing_math_and_physics_once(self):
        database_path = TEST_DIR / f"permission-migration-{uuid.uuid4().hex}.db"
        local_engine = create_engine(
            f"sqlite:///{database_path.as_posix()}",
            connect_args={"check_same_thread": False},
        )
        LocalSession = sessionmaker(autocommit=False, autoflush=False, bind=local_engine)
        math_source = "义务教育数学课程标准（2022年版）.docx"
        physics_source = "义务教育物理课程标准（2022年版）.docx"
        try:
            Base.metadata.create_all(local_engine)
            table_names = set(inspect(local_engine).get_table_names())
            self.assertNotIn("app_settings", table_names)
            self.assertNotIn("agent_conversations", table_names)
            self.assertNotIn(
                "chat_mode",
                {column["name"] for column in inspect(local_engine).get_columns("users")},
            )
            with LocalSession() as db:
                for source, count in ((math_source, 267), (physics_source, 96)):
                    db.add(
                        CurriculumSourceModel(
                            source=source,
                            checksum="test",
                            chunk_count=count,
                            vector_chunk_count=count,
                            vector_status="ready",
                            embedding_model="test",
                            last_error="",
                            updated_at="2026-01-01T00:00:00+00:00",
                        )
                    )
                    db.add_all(
                        CurriculumChunkModel(
                            source=source,
                            source_index=index,
                            content=f"片段 {index}",
                            created_at="2026-01-01T00:00:00+00:00",
                        )
                        for index in range(count)
                    )
                db.commit()
            with patch("app.db.migrations.engine", local_engine):
                ensure_schema_compatibility()
            with LocalSession() as db:
                self.assertEqual(db.query(CurriculumChunkModel).count(), 363)
                permissions = {
                    (row.source, row.agent_id)
                    for row in db.query(CurriculumSourceAgentPermissionModel).all()
                }
                self.assertEqual(
                    permissions,
                    {
                        (math_source, "mathematics_teacher_agent"),
                        (physics_source, "physics_teacher_agent"),
                    },
                )
                db.query(CurriculumSourceAgentPermissionModel).filter(
                    CurriculumSourceAgentPermissionModel.source == physics_source
                ).delete()
                db.commit()
            with patch("app.db.migrations.engine", local_engine):
                ensure_schema_compatibility()
            with LocalSession() as db:
                self.assertEqual(
                    CurriculumPermissionService.allowed_expert_ids(db, physics_source),
                    [],
                )
        finally:
            local_engine.dispose()

    def test_v3_database_migrates_to_v4_idempotently(self):
        database_path = TEST_DIR / f"v3-migration-{uuid.uuid4().hex}.db"
        local_engine = create_engine(f"sqlite:///{database_path.as_posix()}")
        try:
            with local_engine.begin() as connection:
                connection.execute(text("""
                    CREATE TABLE curriculum_sources (
                        source VARCHAR PRIMARY KEY,
                        category VARCHAR NOT NULL DEFAULT 'curriculum',
                        checksum VARCHAR NOT NULL DEFAULT '',
                        chunk_count INTEGER NOT NULL DEFAULT 0,
                        vector_chunk_count INTEGER NOT NULL DEFAULT 0,
                        vector_status VARCHAR NOT NULL DEFAULT 'pending',
                        embedding_model VARCHAR NOT NULL DEFAULT '',
                        last_error TEXT NOT NULL DEFAULT '',
                        updated_at VARCHAR NOT NULL
                    )
                """))
                connection.execute(text("""
                    CREATE TABLE curriculum_chunks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        source VARCHAR NOT NULL,
                        source_index INTEGER NOT NULL,
                        content TEXT NOT NULL,
                        created_at VARCHAR NOT NULL,
                        UNIQUE(source, source_index)
                    )
                """))
                connection.execute(
                    text("""
                        INSERT INTO curriculum_sources
                        (source, category, checksum, chunk_count, vector_chunk_count,
                         vector_status, embedding_model, last_error, updated_at)
                        VALUES (:source, 'rural_revitalization', 'sum', 1, 0,
                                'disabled', '', '', '2026-01-01')
                    """),
                    {"source": "legacy-rural.txt"},
                )
                connection.execute(
                    text("""
                        INSERT INTO curriculum_chunks
                        (source, source_index, content, created_at)
                        VALUES ('legacy-rural.txt', 0, '第一条 旧资料', '2026-01-01')
                    """),
                )
            with patch("app.db.migrations.engine", local_engine):
                ensure_schema_compatibility()
                ensure_schema_compatibility()
            migrated = inspect(local_engine)
            source_columns = {column["name"] for column in migrated.get_columns("curriculum_sources")}
            chunk_columns = {column["name"] for column in migrated.get_columns("curriculum_chunks")}
            self.assertTrue({"id", "policy_layer", "validity_status", "review_status"} <= source_columns)
            self.assertTrue({"heading_path", "article_number", "chunk_type"} <= chunk_columns)
            self.assertIn("knowledge_source_topics", migrated.get_table_names())
            self.assertIn("knowledge_source_review_events", migrated.get_table_names())
            with local_engine.connect() as connection:
                row = connection.execute(
                    text("SELECT id, review_status, policy_layer FROM curriculum_sources WHERE source='legacy-rural.txt'")
                ).mappings().one()
            self.assertEqual(
                row["id"],
                uuid.uuid5(uuid.NAMESPACE_URL, "knowledge-source:legacy-rural.txt").hex,
            )
            self.assertEqual(row["review_status"], "draft")
            self.assertIsNone(row["policy_layer"])
        finally:
            local_engine.dispose()

    def test_insect_hotel_flow_is_listed_with_expected_stages(self):
        flow_response = self.client.get("/api/flows")
        self.assertEqual(flow_response.status_code, 200)

        insect_flow = next(
            item
            for item in flow_response.json()["data"]
            if item["name"] == "insect_hotel_project"
        )

        self.assertEqual(insect_flow["display_name"], "昆虫旅馆项目探究流")
        self.assertEqual(insect_flow["stage_count"], 6)
        self.assertEqual(
            [stage["id"] for stage in insect_flow["stages"]],
            EXPECTED_INSECT_HOTEL_STAGES,
        )

    def test_main_tutor_receives_every_stage_direction(self):
        for flow_name in (
            "inquiry_7_stage",
            "three_step_inquiry",
            "steam_project",
            "insect_hotel_project",
        ):
            flow = get_flow(flow_name)
            for stage in flow["stages"]:
                prompt = PromptService.build_guide_agent_prompt(
                    topic="阶段能力测试",
                    flow_display_name=flow["display_name"],
                    stage=stage,
                    dialog_history="",
                    doc_input="",
                )
                self.assertIn("你是贯穿完整教学设计流程的主导师 Agent", prompt)
                self.assertIn(stage["direction"], prompt)

    def test_insect_hotel_session_initializes_expected_outputs_and_agents(self):
        session_id, stage_id = self.create_session(
            flow_name="insect_hotel_project",
            topic="昆虫旅馆",
        )
        try:
            session = self.get_session(session_id)
            self.assertEqual(session["flow_name"], "insect_hotel_project")
            self.assertEqual(session["flow_display_name"], "昆虫旅馆项目探究流")
            self.assertEqual(session["current_stage"]["id"], "natural_materials")
            self.assertEqual(stage_id, "natural_materials")
            self.assertEqual(len(session["outputs"]), 6)
            self.assertEqual(
                [item["stage_id"] for item in session["outputs"]],
                EXPECTED_INSECT_HOTEL_STAGES,
            )
            self.assertEqual(
                self.client.get(f"/api/sessions/{session_id}/stage_agents").status_code,
                404,
            )
        finally:
            self.delete_session(session_id)

    def test_insect_hotel_flow_supports_stage_progression_and_stage_back(self):
        session_id, stage_id = self.create_session(
            flow_name="insect_hotel_project",
            topic="昆虫旅馆",
        )
        try:
            advance_response = self.client.post(
                f"/api/sessions/{session_id}/chat",
                json={
                    "type": "sys_action",
                    "action": "next_stage",
                    "final_content": "自然取材阶段定稿",
                },
            )
            self.assertEqual(advance_response.status_code, 200)

            session = self.get_session(session_id)
            self.assertEqual(session["current_stage_index"], 1)
            self.assertEqual(session["current_stage"]["id"], "habitat_needs")
            first_output = next(item for item in session["outputs"] if item["stage_id"] == stage_id)
            self.assertTrue(first_output["confirmed"])
            self.assertEqual(first_output["final_content"], "自然取材阶段定稿")

            rollback_response = self.client.post(
                f"/api/sessions/{session_id}/rollback",
                json={"steps": 1, "stage_back": True},
            )
            self.assertEqual(rollback_response.status_code, 200)
            rolled_session = rollback_response.json()["data"]["session"]
            self.assertEqual(rolled_session["current_stage_index"], 0)
            self.assertEqual(rolled_session["current_stage"]["id"], "natural_materials")
            rolled_output = next(item for item in rolled_session["outputs"] if item["stage_id"] == stage_id)
            self.assertFalse(rolled_output["confirmed"])
            self.assertEqual(rolled_output["final_content"], "")
        finally:
            self.delete_session(session_id)

    def test_auth_registration_validation_and_logout(self):
        username = f"auth_{uuid.uuid4().hex[:10]}"
        client = TestClient(app)
        try:
            invalid = client.post(
                "/api/auth/register",
                json={"username": "ab", "password": "short"},
            )
            self.assertEqual(invalid.status_code, 422)

            registered = client.post(
                "/api/auth/register",
                json={"username": username, "password": "valid-password-123"},
            )
            self.assertEqual(registered.status_code, 200)
            self.assertEqual(registered.json()["data"]["username"], username)
            self.assertFalse(registered.json()["data"]["is_admin"])
            self.assertEqual(client.get("/api/auth/me").status_code, 200)

            duplicate = client.post(
                "/api/auth/register",
                json={"username": username.upper(), "password": "valid-password-123"},
            )
            self.assertEqual(duplicate.status_code, 409)

            logout = client.post("/api/auth/logout")
            self.assertEqual(logout.status_code, 200)
            self.assertEqual(client.get("/api/auth/me").status_code, 401)

            invalid_login = client.post(
                "/api/auth/login",
                json={"username": username, "password": "wrong-password"},
            )
            self.assertEqual(invalid_login.status_code, 401)
            valid_login = client.post(
                "/api/auth/login",
                json={"username": username.upper(), "password": "valid-password-123"},
            )
            self.assertEqual(valid_login.status_code, 200)
            self.assertEqual(client.get("/api/auth/me").status_code, 200)
            for origin in (
                "http://127.0.0.1:5173",
                "http://localhost:5173",
                "http://152.136.39.252:5173",
            ):
                cors_response = client.options(
                    "/api/auth/register",
                    headers={
                        "Origin": origin,
                        "Access-Control-Request-Method": "POST",
                        "Access-Control-Request-Headers": "content-type",
                    },
                )
                self.assertEqual(cors_response.status_code, 200)
                self.assertEqual(
                    cors_response.headers.get("access-control-allow-origin"),
                    origin,
                )
                self.assertEqual(
                    cors_response.headers.get("access-control-allow-credentials"),
                    "true",
                )
        finally:
            client.close()

    def test_admin_channels_and_curriculum_file_permissions(self):
        ordinary_client = TestClient(app)
        admin_client = TestClient(app)
        disabled_client = TestClient(app)
        ordinary_username = f"ordinary_{uuid.uuid4().hex[:8]}"
        admin_username = f"admin_{uuid.uuid4().hex[:8]}"
        password = "valid-password-123"
        sources = [
            f"小学课标_{uuid.uuid4().hex}.md",
            f"课标表格_{uuid.uuid4().hex}.docx",
            f"课标文档_{uuid.uuid4().hex}.pdf",
        ]
        try:
            ordinary_registered = ordinary_client.post(
                "/api/auth/register",
                json={"username": ordinary_username, "password": password},
            )
            self.assertEqual(ordinary_registered.status_code, 200)
            self.assertFalse(ordinary_registered.json()["data"]["is_admin"])

            admin_registered = admin_client.post(
                "/api/auth/admin/register",
                json={"username": admin_username, "password": password},
            )
            self.assertEqual(admin_registered.status_code, 200)
            self.assertTrue(admin_registered.json()["data"]["is_admin"])

            admin_client.post("/api/auth/logout")
            self.assertEqual(
                admin_client.post(
                    "/api/auth/login",
                    json={"username": admin_username, "password": password},
                ).status_code,
                401,
            )
            self.assertEqual(
                admin_client.post(
                    "/api/auth/admin/login",
                    json={"username": admin_username, "password": password},
                ).status_code,
                200,
            )

            ordinary_client.post("/api/auth/logout")
            self.assertEqual(
                ordinary_client.post(
                    "/api/auth/admin/login",
                    json={"username": ordinary_username, "password": password},
                ).status_code,
                401,
            )
            self.assertEqual(
                ordinary_client.post(
                    "/api/auth/login",
                    json={"username": ordinary_username, "password": password},
                ).status_code,
                200,
            )

            with patch.object(get_settings(), "admin_registration_enabled", False):
                disabled = disabled_client.post(
                    "/api/auth/admin/register",
                    json={
                        "username": f"disabled_{uuid.uuid4().hex[:8]}",
                        "password": password,
                    },
                )
            self.assertEqual(disabled.status_code, 403)

            self.assertEqual(ordinary_client.get("/api/curriculum/files").status_code, 200)
            denied_upload = ordinary_client.post(
                "/api/curriculum/files",
                files={"file": (sources[0], b"ordinary cannot upload", "text/markdown")},
            )
            self.assertEqual(denied_upload.status_code, 403)

            uploads = [
                (sources[0], "小学三年级人工智能活动应使用图形化工具。".encode("utf-8"), "text/markdown"),
                (
                    sources[1],
                    make_docx(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ),
                (sources[2], make_text_pdf("CURRICULUM_API_PDF"), "application/pdf"),
            ]
            for name, data, content_type in uploads:
                uploaded = admin_client.post(
                    "/api/curriculum/files",
                    files={"file": (name, data, content_type)},
                )
                self.assertEqual(uploaded.status_code, 200, uploaded.text)
                self.assertEqual(uploaded.json()["data"]["source"], name)
                self.assertGreater(uploaded.json()["data"]["chunk_count"], 0)

            replaced = admin_client.post(
                "/api/curriculum/files",
                files={
                    "file": (
                        sources[0],
                        "小学三年级活动需要过程评价与安全边界。".encode("utf-8"),
                        "text/markdown",
                    )
                },
            )
            self.assertEqual(replaced.status_code, 200)
            with SessionLocal() as db:
                markdown_chunks = (
                    db.query(CurriculumChunkModel)
                    .filter(CurriculumChunkModel.source == sources[0])
                    .all()
                )
                self.assertTrue(markdown_chunks)
                self.assertTrue(all("图形化工具" not in row.content for row in markdown_chunks))

            failed_replacement = admin_client.post(
                "/api/curriculum/files",
                files={"file": (sources[1], b"not-a-docx", "application/octet-stream")},
            )
            self.assertEqual(failed_replacement.status_code, 400)
            with SessionLocal() as db:
                self.assertGreater(
                    db.query(CurriculumChunkModel)
                    .filter(CurriculumChunkModel.source == sources[1])
                    .count(),
                    0,
                )

            ordinary_sources = {
                item["source"]
                for item in ordinary_client.get("/api/curriculum/files").json()["data"]
            }
            self.assertTrue(set(sources).issubset(ordinary_sources))
            self.assertEqual(
                ordinary_client.delete(
                    "/api/curriculum/files",
                    params={"source": sources[0]},
                ).status_code,
                403,
            )

            for source in sources:
                deleted = admin_client.delete(
                    "/api/curriculum/files",
                    params={"source": source},
                )
                self.assertEqual(deleted.status_code, 200)
        finally:
            with SessionLocal() as db:
                db.query(CurriculumChunkModel).filter(
                    CurriculumChunkModel.source.in_(sources)
                ).delete(synchronize_session=False)
                db.commit()
            ordinary_client.close()
            admin_client.close()
            disabled_client.close()

    def test_first_registration_claims_legacy_sessions_without_chat_mode(self):
        database_path = TEST_DIR / f"legacy-{uuid.uuid4().hex}.db"
        local_engine = create_engine(
            f"sqlite:///{database_path.as_posix()}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(local_engine)
        LocalSession = sessionmaker(autocommit=False, autoflush=False, bind=local_engine)
        try:
            with LocalSession() as db:
                legacy = SessionModel(
                    id="legacy_session",
                    owner_user_id=None,
                    title="旧会话",
                    topic="旧课题",
                    flow_name="inquiry_7_stage",
                    current_stage_index=0,
                    status="active",
                    draft_mode_enabled=0,
                    created_at="2026-01-01T00:00:00+00:00",
                    updated_at="2026-01-01T00:00:00+00:00",
                )
                db.add(legacy)
                db.commit()

                user, _ = register_user(db, "legacy_owner", "valid-password-123")
                db.refresh(legacy)

                self.assertEqual(legacy.owner_user_id, user.id)
        finally:
            local_engine.dispose()

    def test_users_have_isolated_sessions_and_main_tutor_chat(self):
        alice = TestClient(app)
        bob = TestClient(app)
        try:
            for client, username in (
                (alice, f"alice_{uuid.uuid4().hex[:10]}"),
                (bob, f"bob_{uuid.uuid4().hex[:10]}"),
            ):
                response = client.post(
                    "/api/auth/register",
                    json={"username": username, "password": "valid-password-123"},
                )
                self.assertEqual(response.status_code, 200)

            alice_session = alice.post(
                "/api/sessions",
                json={"topic": "Alice 的课题", "flow_name": "inquiry_7_stage"},
            ).json()["data"]["id"]
            bob_session = bob.post(
                "/api/sessions",
                json={"topic": "Bob 的课题", "flow_name": "inquiry_7_stage"},
            ).json()["data"]["id"]

            self.assertNotEqual(alice_session, bob_session)
            self.assertEqual(
                [item["id"] for item in alice.get("/api/sessions").json()["data"]],
                [alice_session],
            )
            self.assertEqual(
                [item["id"] for item in bob.get("/api/sessions").json()["data"]],
                [bob_session],
            )
            self.assertEqual(alice.get(f"/api/sessions/{bob_session}").status_code, 404)
            self.assertEqual(bob.delete(f"/api/sessions/{alice_session}").status_code, 404)

            self.assertEqual(alice.get("/api/settings/chat-mode").status_code, 404)
            alice_events = parse_sse(
                alice.post(
                    f"/api/sessions/{alice_session}/chat",
                    json={"type": "chat", "message": "Alice 的第一轮提问"},
                ).text
            )
            bob_events = parse_sse(
                bob.post(
                    f"/api/sessions/{bob_session}/chat",
                    json={"type": "chat", "message": "Bob 的第一轮提问"},
                ).text
            )
            self.assertNotIn("chat_mode", alice_events[0][1])
            self.assertNotIn("chat_mode", bob_events[0][1])
            self.assertTrue(
                all(
                    data.get("agent_id") == "main_tutor"
                    for name, data in alice_events
                    if name == "delta"
                )
            )
        finally:
            alice.close()
            bob.close()

    def test_same_topic_different_flows_are_separate_and_flow_switch_cannot_clear_data(self):
        first_response = self.client.post(
            "/api/sessions",
            json={"topic": "光的折射", "flow_name": "inquiry_7_stage"},
        )
        second_response = self.client.post(
            "/api/sessions",
            json={"topic": "光的折射", "flow_name": "three_step_inquiry"},
        )
        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)

        first = first_response.json()["data"]
        second = second_response.json()["data"]
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(first["flow_name"], "inquiry_7_stage")
        self.assertEqual(second["flow_name"], "three_step_inquiry")
        self.assertNotEqual(len(first["outputs"]), len(second["outputs"]))
        listed_ids = {
            item["id"]
            for item in self.client.get("/api/sessions").json()["data"]
        }
        self.assertTrue({first["id"], second["id"]}.issubset(listed_ids))

        first_stage_id = first["outputs"][0]["stage_id"]
        with SessionLocal() as db:
            db.add(
                MessageModel(
                    id="msg_isolation_test",
                    session_id=first["id"],
                    stage_id=first_stage_id,
                    role="user",
                    content="只属于七阶段流程的消息",
                    agent_id=None,
                    message_type="chat",
                    created_at="2026-01-01T00:00:00+00:00",
                )
            )
            db.add(
                ChatTurnModel(
                    turn_id="turn_isolation_test",
                    session_id=first["id"],
                    stage_id=first_stage_id,
                    user_message_id="msg_isolation_test",
                    assistant_message_id="msg_isolation_test",
                    draft_before="",
                    draft_after="",
                    created_at="2026-01-01T00:00:00+00:00",
                )
            )
            db.add(
                DraftProposalModel(
                    id="proposal_isolation_test",
                    session_id=first["id"],
                    stage_id=first_stage_id,
                    base_content="旧草案",
                    candidate_content="新草案",
                    diff_json="[]",
                    status="pending",
                    created_at="2026-01-01T00:00:00+00:00",
                    updated_at="2026-01-01T00:00:00+00:00",
                )
            )
            db.add(
                RagRecordModel(
                    id="rag_isolation_test",
                    session_id=first["id"],
                    stage_id=first_stage_id,
                    query="隔离测试",
                    context="只属于第一个会话",
                    source_json="[]",
                    created_at="2026-01-01T00:00:00+00:00",
                )
            )
            db.commit()

        switched = self.client.post(
            f"/api/sessions/{first['id']}/select_flow",
            json={"flow_name": "three_step_inquiry", "clear_messages": True},
        )
        self.assertEqual(switched.status_code, 409)
        self.assertIn("流程不可修改", switched.json()["detail"])

        first_after = self.get_session(first["id"])
        second_after = self.get_session(second["id"])
        self.assertEqual(first_after["flow_name"], "inquiry_7_stage")
        self.assertEqual(len(first_after["outputs"]), 7)
        self.assertEqual(len(second_after["outputs"]), 3)
        self.assertEqual(len(self.get_messages(first["id"])), 1)
        self.assertEqual(self.get_messages(second["id"]), [])

        with SessionLocal() as db:
            self.assertEqual(
                db.query(ChatTurnModel)
                .filter(ChatTurnModel.session_id == first["id"])
                .count(),
                1,
            )
            self.assertEqual(
                db.query(DraftProposalModel)
                .filter(DraftProposalModel.session_id == first["id"])
                .count(),
                1,
            )
            self.assertEqual(
                db.query(RagRecordModel)
                .filter(RagRecordModel.session_id == first["id"])
                .count(),
                1,
            )
        self.delete_session(first["id"])
        self.assertEqual(self.get_session(second["id"])["flow_name"], "three_step_inquiry")
        self.delete_session(second["id"])

    def test_chat_stream_defaults_to_main_mode_and_persists_two_messages(self):
        session_id, stage_id = self.create_session()
        try:
            response, events = self.stream_chat(session_id, "用筷子折弯现象导入")
            event_names = [name for name, _ in events]

            self.assertEqual(event_names[0], "stage")
            agent_events = [
                (index, data)
                for index, (name, data) in enumerate(events)
                if name == "agent"
            ]
            self.assertEqual(
                [data["message_type"] for _, data in agent_events],
                ["main_tutor"],
            )
            main_delta_indices = [
                index
                for index, (name, data) in enumerate(events)
                if name == "delta" and data.get("message_type") == "main_tutor"
            ]
            self.assertTrue(main_delta_indices)
            self.assertNotIn("draft", event_names)
            self.assertEqual(event_names[-1], "done")
            self.assertFalse(events[-1][1]["degraded"])
            self.assertFalse(events[-1][1]["draft_mode_enabled"])
            self.assertFalse(events[-1][1]["draft_updated"])
            self.assertEqual(response.headers["cache-control"], "no-cache")
            self.assertEqual(response.headers["x-accel-buffering"], "no")

            messages = self.get_messages(session_id)
            self.assertEqual(
                [item["message_type"] for item in messages],
                ["chat", "main_tutor"],
            )
            self.assertEqual(
                [item["agent_id"] for item in messages],
                [None, "main_tutor"],
            )
            self.assertNotIn("===DRAFT_START===", messages[1]["content"])

            session = self.get_session(session_id)
            output = next(item for item in session["outputs"] if item["stage_id"] == stage_id)
            self.assertFalse(output["draft_content"])

            with SessionLocal() as db:
                turn = (
                    db.query(ChatTurnModel)
                    .filter(ChatTurnModel.session_id == session_id)
                    .one()
                )
                self.assertFalse(turn.expert_message_id)
                self.assertFalse(turn.rag_record_id)
                self.assertEqual(
                    db.query(RagRecordModel)
                    .filter(RagRecordModel.session_id == session_id)
                    .count(),
                    0,
                )
        finally:
            self.delete_session(session_id)

    def test_curriculum_files_ingest_idempotently_and_retrieve_with_bm25(self):
        source = f"小学信息科技课标_{uuid.uuid4().hex}.md"
        wrong_level_source = f"初中信息科技课标_{uuid.uuid4().hex}.md"
        curriculum_dir = TEST_DIR / f"curriculum_{uuid.uuid4().hex}"
        curriculum_dir.mkdir(parents=True, exist_ok=True)
        markdown_path = curriculum_dir / source
        markdown_path.write_text(
            "小学三年级学生以直观体验为主，人工智能活动应采用图形化工具，控制任务难度。",
            encoding="utf-8",
        )
        try:
            with SessionLocal() as db:
                service = CurriculumKnowledgeService(db)
                first_count = service.ingest_file(markdown_path, source=source)
                db.commit()
                self.assertGreater(first_count, 0)

                markdown_path.write_text(
                    "小学三年级学生适合图形化人工智能活动，并应设置清晰的安全边界与过程评价。",
                    encoding="utf-8",
                )
                second_count = service.ingest_file(markdown_path, source=source)
                db.commit()
                stored = (
                    db.query(CurriculumChunkModel)
                    .filter(CurriculumChunkModel.source == source)
                    .all()
                )
                self.assertEqual(len(stored), second_count)
                self.assertTrue(all("直观体验为主" not in item.content for item in stored))

                service.ingest(
                    wrong_level_source,
                    "初中七年级学生可以使用 Python 编程完成复杂的人工智能模型训练活动。",
                )
                db.commit()

                results = service.retrieve("小学三年级人工智能活动的安全与评价", top_k=2)
                self.assertTrue(results)
                self.assertEqual(results[0].source, source)
                self.assertIn("安全边界", results[0].content)
                self.assertNotIn(wrong_level_source, [item.source for item in results])
        finally:
            with SessionLocal() as db:
                db.query(CurriculumChunkModel).filter(
                    CurriculumChunkModel.source.in_([source, wrong_level_source])
                ).delete(synchronize_session=False)
                db.commit()
            shutil.rmtree(curriculum_dir, ignore_errors=True)

    def test_curriculum_parser_supports_txt_pdf_and_docx(self):
        curriculum_dir = TEST_DIR / f"curriculum_formats_{uuid.uuid4().hex}"
        curriculum_dir.mkdir(parents=True, exist_ok=True)
        text_path = curriculum_dir / "standard.txt"
        pdf_path = curriculum_dir / "standard.pdf"
        docx_path = curriculum_dir / "standard.docx"
        text_path.write_text("TXT_CURRICULUM_MARKER", encoding="utf-8")
        pdf_path.write_bytes(make_text_pdf("PDF_CURRICULUM_MARKER"))
        docx_path.write_bytes(make_docx())
        try:
            self.assertIn(
                "TXT_CURRICULUM_MARKER",
                CurriculumKnowledgeService.extract_text(text_path),
            )
            self.assertIn(
                "PDF_CURRICULUM_MARKER",
                CurriculumKnowledgeService.extract_text(pdf_path),
            )
            docx_text = CurriculumKnowledgeService.extract_text(docx_path)
            self.assertIn("DOCX_PARAGRAPH_MARKER", docx_text)
            self.assertIn("DOCX_TABLE_LEFT", docx_text)
        finally:
            shutil.rmtree(curriculum_dir, ignore_errors=True)

    def test_curriculum_hybrid_retrieval_and_vector_sync(self):
        source = f"初中物理课标_{uuid.uuid4().hex}.md"
        settings = get_settings()
        vector_store = FakeCurriculumVectorStore()
        try:
            with patch.object(settings, "curriculum_vector_enabled", True), patch.object(
                settings,
                "curriculum_embedding_model",
                "fake-local-model",
            ):
                with SessionLocal() as db:
                    service = CurriculumKnowledgeService(
                        db,
                        settings,
                        vector_store=vector_store,
                    )
                    count = service.ingest(
                        source,
                        "初中八年级学生通过推墙体验力的作用是相互的，并记录身体后退的证据。",
                    )
                    db.commit()
                    self.assertEqual(len(vector_store.rows), count)

                    query = "为什么推墙的人会向后移动"
                    results = service.retrieve(query, top_k=1)
                    self.assertTrue(results)
                    self.assertEqual(results[0].source, source)
                    self.assertEqual(results[0].vector_score, 0.95)
                    all_chunks = db.query(CurriculumChunkModel).all()
                    expected_bm25 = bm25_scores(query, all_chunks)[results[0].chunk_id]
                    self.assertAlmostEqual(results[0].bm25_score, expected_bm25, places=6)
                    self.assertEqual(results[0].retrieval_mode, "local_hybrid")

                    deleted = service.delete_source(source)
                    db.commit()
                    self.assertGreater(deleted, 0)
                    self.assertIn(source, vector_store.deleted_sources)
                    self.assertEqual(
                        db.query(CurriculumChunkModel)
                        .filter(CurriculumChunkModel.source == source)
                        .count(),
                        0,
                    )
        finally:
            with SessionLocal() as db:
                db.query(CurriculumSourceModel).filter(
                    CurriculumSourceModel.source == source
                ).delete(synchronize_session=False)
                db.query(CurriculumChunkModel).filter(
                    CurriculumChunkModel.source == source
                ).delete(synchronize_session=False)
                db.commit()

    def test_curriculum_subject_detection_only_filters_explicit_subjects(self):
        self.assertEqual(detect_subjects("八年级力的作用是相互的探究"), {"physics"})
        self.assertEqual(detect_subjects("初中函数与方程教学"), {"mathematics"})
        self.assertEqual(detect_subjects("适合八年级的探究活动"), set())

    def test_curriculum_vector_similarity_threshold(self):
        source = f"初中物理阈值测试_{uuid.uuid4().hex}.md"
        settings = get_settings()
        vector_store = FakeCurriculumVectorStore()
        try:
            with patch.object(settings, "curriculum_vector_enabled", True), patch.object(
                settings,
                "curriculum_vector_min_similarity",
                0.5,
            ):
                with SessionLocal() as db:
                    service = CurriculumKnowledgeService(
                        db,
                        settings,
                        vector_store=vector_store,
                    )
                    service.ingest(source, "初中八年级学生观察力的相互作用。")
                    db.commit()
                    chunk = db.query(CurriculumChunkModel).filter(
                        CurriculumChunkModel.source == source
                    ).one()

                    with patch.object(
                        vector_store,
                        "query",
                        return_value=[CurriculumVectorHit(chunk_id=chunk.id, score=0.499999)],
                    ):
                        self.assertEqual(service.retrieve("完全不同的检索词", top_k=1), [])

                    with patch.object(
                        vector_store,
                        "query",
                        return_value=[CurriculumVectorHit(chunk_id=chunk.id, score=0.5)],
                    ):
                        results = service.retrieve("完全不同的检索词", top_k=1)
                        self.assertEqual(len(results), 1)
                        self.assertEqual(results[0].vector_score, 0.5)
        finally:
            with SessionLocal() as db:
                db.query(CurriculumSourceModel).filter(
                    CurriculumSourceModel.source == source
                ).delete(synchronize_session=False)
                db.query(CurriculumChunkModel).filter(
                    CurriculumChunkModel.source == source
                ).delete(synchronize_session=False)
                db.commit()

    def test_curriculum_admin_export_import_and_permissions(self):
        source = f"export_{uuid.uuid4().hex}.md"
        ecology_source = f"export_ecology_{uuid.uuid4().hex}.md"
        rural_source = f"export_rural_{uuid.uuid4().hex}.md"
        admin_client = TestClient(app)
        ordinary_client = TestClient(app)
        try:
            password = "valid-password-123"
            admin_client.post(
                "/api/auth/admin/register",
                json={"username": f"export_admin_{uuid.uuid4().hex[:8]}", "password": password},
            )
            ordinary_client.post(
                "/api/auth/register",
                json={"username": f"export_user_{uuid.uuid4().hex[:8]}", "password": password},
            )
            uploaded = admin_client.post(
                "/api/curriculum/files",
                files={"file": (source, "初中实验应记录证据。".encode("utf-8"), "text/markdown")},
            )
            self.assertEqual(uploaded.status_code, 200, uploaded.text)
            self.assertEqual(uploaded.json()["data"]["allowed_expert_ids"], [])
            ecology_uploaded = admin_client.post(
                "/api/curriculum/files",
                data={"category": "ecology"},
                files={
                    "file": (
                        ecology_source,
                        "月季吸引访花昆虫。".encode("utf-8"),
                        "text/markdown",
                    )
                },
            )
            self.assertEqual(ecology_uploaded.status_code, 200, ecology_uploaded.text)
            self.assertEqual(ecology_uploaded.json()["data"]["category"], "ecology")
            rural_uploaded = admin_client.post(
                "/api/curriculum/files",
                data={"category": "rural_revitalization"},
                files={
                    "file": (
                        rural_source,
                        "乡村产业发展需要人才与生态资源协同。".encode("utf-8"),
                        "text/markdown",
                    )
                },
            )
            self.assertEqual(rural_uploaded.status_code, 200, rural_uploaded.text)
            self.assertEqual(
                rural_uploaded.json()["data"]["category"],
                "rural_revitalization",
            )
            permission_response = admin_client.put(
                "/api/curriculum/files/permissions",
                json={
                    "source": source,
                    "expert_ids": [
                        "physics_teacher_agent",
                        "mathematics_teacher_agent",
                        "physics_teacher_agent",
                    ],
                },
            )
            self.assertEqual(permission_response.status_code, 200, permission_response.text)
            self.assertEqual(
                permission_response.json()["data"]["allowed_expert_ids"],
                ["physics_teacher_agent", "mathematics_teacher_agent"],
            )
            denied_permission = ordinary_client.put(
                "/api/curriculum/files/permissions",
                json={"source": source, "expert_ids": []},
            )
            self.assertEqual(denied_permission.status_code, 403)
            invalid_permission = admin_client.put(
                "/api/curriculum/files/permissions",
                json={"source": source, "expert_ids": ["unknown_agent"]},
            )
            self.assertEqual(invalid_permission.status_code, 400)
            self.assertEqual(ordinary_client.get("/api/curriculum/status").status_code, 403)
            self.assertEqual(ordinary_client.get("/api/curriculum/export").status_code, 403)
            self.assertEqual(ordinary_client.get("/api/curriculum/retrievals").status_code, 403)

            exported = admin_client.get("/api/curriculum/export")
            self.assertEqual(exported.status_code, 200)
            with zipfile.ZipFile(BytesIO(exported.content)) as archive:
                payload = json.loads(archive.read("curriculum.json").decode("utf-8"))
            self.assertEqual(payload["version"], 3)
            self.assertEqual(payload["category_filter"], "all")
            self.assertIn(
                rural_source,
                [item["source"] for item in payload["sources"]],
            )
            exported_source = next(item for item in payload["sources"] if item["source"] == source)
            self.assertEqual(
                exported_source["allowed_expert_ids"],
                ["mathematics_teacher_agent", "physics_teacher_agent"],
            )
            serialized = json.dumps(exported_source, ensure_ascii=False)
            self.assertIn("初中实验应记录证据", serialized)
            self.assertNotIn("password_hash", serialized)
            self.assertNotIn("auth_sessions", serialized)

            ecology_export = admin_client.get(
                "/api/curriculum/export", params={"category": "ecology"}
            )
            self.assertEqual(ecology_export.status_code, 200, ecology_export.text)
            self.assertIn(
                "ecology-knowledge-base.zip",
                ecology_export.headers.get("content-disposition", ""),
            )
            with zipfile.ZipFile(BytesIO(ecology_export.content)) as archive:
                ecology_payload = json.loads(
                    archive.read("curriculum.json").decode("utf-8")
                )
            self.assertEqual(ecology_payload["category_filter"], "ecology")
            self.assertEqual(
                [item["source"] for item in ecology_payload["sources"]],
                [ecology_source],
            )
            rural_export = admin_client.get(
                "/api/curriculum/export",
                params={"category": "rural_revitalization"},
            )
            self.assertEqual(rural_export.status_code, 200, rural_export.text)
            self.assertIn(
                "rural_revitalization-knowledge-base.zip",
                rural_export.headers.get("content-disposition", ""),
            )
            with zipfile.ZipFile(BytesIO(rural_export.content)) as archive:
                rural_payload = json.loads(
                    archive.read("curriculum.json").decode("utf-8")
                )
            self.assertEqual(
                rural_payload["category_filter"], "rural_revitalization"
            )
            self.assertEqual(
                [item["source"] for item in rural_payload["sources"]],
                [rural_source],
            )
            self.assertEqual(
                admin_client.get(
                    "/api/curriculum/export", params={"category": "unknown"}
                ).status_code,
                400,
            )

            self.assertEqual(
                admin_client.delete("/api/curriculum/files", params={"source": source}).status_code,
                200,
            )
            with SessionLocal() as db:
                self.assertEqual(
                    db.query(CurriculumSourceAgentPermissionModel)
                    .filter(CurriculumSourceAgentPermissionModel.source == source)
                    .count(),
                    0,
                )
            imported = admin_client.post(
                "/api/curriculum/import",
                files={"file": ("curriculum-knowledge.zip", exported.content, "application/zip")},
            )
            self.assertEqual(imported.status_code, 200, imported.text)
            listed = admin_client.get("/api/curriculum/files").json()["data"]
            restored = next(item for item in listed if item["source"] == source)
            self.assertEqual(
                restored["allowed_expert_ids"],
                ["mathematics_teacher_agent", "physics_teacher_agent"],
            )
        finally:
            with SessionLocal() as db:
                CurriculumKnowledgeService(db).delete_source(source)
                CurriculumKnowledgeService(db).delete_source(ecology_source)
                CurriculumKnowledgeService(db).delete_source(rural_source)
                db.commit()
            admin_client.close()
            ordinary_client.close()

    def test_curriculum_v1_import_is_unassigned_and_invalid_v2_rolls_back(self):
        source_v1 = f"legacy_{uuid.uuid4().hex}.md"
        rejected_source = f"rejected_{uuid.uuid4().hex}.md"
        admin_client = TestClient(app)
        try:
            admin_client.post(
                "/api/auth/admin/register",
                json={
                    "username": f"bundle_admin_{uuid.uuid4().hex[:8]}",
                    "password": "valid-password-123",
                },
            )
            v1 = make_curriculum_bundle(
                {
                    "version": 1,
                    "sources": [
                        {
                            "source": source_v1,
                            "chunks": [{"source_index": 0, "content": "旧版知识内容"}],
                        }
                    ],
                }
            )
            imported = admin_client.post(
                "/api/curriculum/import",
                files={"file": ("v1.zip", v1, "application/zip")},
            )
            self.assertEqual(imported.status_code, 200, imported.text)
            listed = admin_client.get("/api/curriculum/files").json()["data"]
            legacy = next(item for item in listed if item["source"] == source_v1)
            self.assertEqual(legacy["allowed_expert_ids"], [])

            invalid_v2 = make_curriculum_bundle(
                {
                    "version": 2,
                    "sources": [
                        {
                            "source": rejected_source,
                            "allowed_expert_ids": ["unknown_agent"],
                            "chunks": [{"source_index": 0, "content": "不应导入"}],
                        }
                    ],
                }
            )
            rejected = admin_client.post(
                "/api/curriculum/import",
                files={"file": ("invalid-v2.zip", invalid_v2, "application/zip")},
            )
            self.assertEqual(rejected.status_code, 400)
            with SessionLocal() as db:
                self.assertEqual(
                    db.query(CurriculumChunkModel)
                    .filter(CurriculumChunkModel.source == rejected_source)
                    .count(),
                    0,
                )
        finally:
            with SessionLocal() as db:
                CurriculumKnowledgeService(db).delete_source(source_v1)
                CurriculumKnowledgeService(db).delete_source(rejected_source)
                db.commit()
            admin_client.close()

    def test_chat_injects_curriculum_reference_and_persists_sources(self):
        source = f"小学信息科技课标_{uuid.uuid4().hex}.md"
        with SessionLocal() as db:
            CurriculumKnowledgeService(db).ingest(
                source,
                "小学三年级学生适合使用图形化工具体验人工智能，任务步骤应简短，并设置安全边界。",
            )
            CurriculumPermissionService.replace_permissions(
                db,
                source,
                ["mathematics_teacher_agent"],
            )
            db.commit()

        session_id, _ = self.create_session(topic="小学三年级人工智能")
        try:
            response = self.client.post(
                f"/api/sessions/{session_id}/chat",
                json={
                    "type": "chat",
                    "message": "设计一个适合小学三年级的人工智能活动",
                    "expert_id": "mathematics_teacher_agent",
                },
            )
            self.assertEqual(response.status_code, 200)
            events = parse_sse(response.text)
            done = next(data for name, data in events if name == "done")
            self.assertEqual(done["rag_sources"], [source])
            self.assertTrue(done["rag_record_id"])

            messages = self.get_messages(session_id)
            self.assertIn(f"参考课标：{source}", messages[-1]["content"])

            with SessionLocal() as db:
                turn = (
                    db.query(ChatTurnModel)
                    .filter(ChatTurnModel.session_id == session_id)
                    .one()
                )
                record = db.query(RagRecordModel).filter(
                    RagRecordModel.id == turn.rag_record_id
                ).one()
                self.assertIn("<curriculum_reference>", record.context)
                metadata = json.loads(record.source_json)
                self.assertEqual(metadata["mode"], "local_bm25")
                self.assertEqual(metadata["records"][0]["source"], source)
        finally:
            self.delete_session(session_id)
            with SessionLocal() as db:
                db.query(CurriculumChunkModel).filter(
                    CurriculumChunkModel.source == source
                ).delete(synchronize_session=False)
                db.commit()

    def test_rag_permissions_isolate_bm25_vector_and_apply_immediately(self):
        physics_source = f"physics_{uuid.uuid4().hex}.md"
        math_source = f"math_{uuid.uuid4().hex}.md"
        vector_store = FakeCurriculumVectorStore()
        settings = get_settings()
        try:
            with SessionLocal() as db, patch.object(settings, "curriculum_vector_enabled", True):
                service = CurriculumKnowledgeService(db, settings, vector_store)
                service.ingest(physics_source, "共同检索词 物理变量控制与测量误差")
                service.ingest(math_source, "共同检索词 数学统计与图表分析")
                CurriculumPermissionService.replace_permissions(
                    db, physics_source, ["physics_teacher_agent"]
                )
                CurriculumPermissionService.replace_permissions(
                    db, math_source, ["mathematics_teacher_agent"]
                )
                db.commit()

                physics_sources = CurriculumPermissionService.allowed_sources(
                    db, "physics_teacher_agent"
                )
                physics_results = service.retrieve(
                    "共同检索词",
                    top_k=4,
                    allowed_sources=physics_sources,
                )
                self.assertTrue(physics_results)
                self.assertEqual({item.source for item in physics_results}, {physics_source})

                CurriculumPermissionService.replace_permissions(db, physics_source, [])
                db.commit()
                self.assertEqual(
                    CurriculumPermissionService.allowed_sources(db, "physics_teacher_agent"),
                    [],
                )
                self.assertEqual(service.retrieve("共同检索词", allowed_sources=[]), [])
        finally:
            with SessionLocal() as db:
                CurriculumKnowledgeService(db).delete_source(physics_source)
                CurriculumKnowledgeService(db).delete_source(math_source)
                db.commit()

    def test_chat_cancel_endpoint_marks_active_stream_as_cancelled(self):
        session_id, _ = self.create_session()
        request_id = f"cancel_{uuid.uuid4().hex}"
        try:
            with SessionLocal() as db:
                user_id = (
                    db.query(SessionModel)
                    .filter(SessionModel.id == session_id)
                    .one()
                    .owner_user_id
                )
            chat_interruptions.register(request_id, session_id, user_id)

            response = self.client.post(
                f"/api/sessions/{session_id}/chat/{request_id}/cancel"
            )

            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()["data"]["cancelled"])
            self.assertTrue(chat_interruptions.is_cancelled(request_id))
        finally:
            chat_interruptions.unregister(request_id)
            self.delete_session(session_id)

    def test_manual_draft_save(self):
        session_id, stage_id = self.create_session()
        try:
            content = "### 手动草稿\n教师已完成二次编辑。"
            response = self.client.put(
                f"/api/sessions/{session_id}/stages/{stage_id}/draft",
                json={"draft_content": content},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["data"]["draft_content"], content)

            session = self.get_session(session_id)
            output = next(item for item in session["outputs"] if item["stage_id"] == stage_id)
            self.assertEqual(output["draft_content"], content)
        finally:
            self.delete_session(session_id)

    def test_first_draft_generation_writes_directly_without_pending_proposal(self):
        session_id, stage_id = self.create_session()
        try:
            self.set_draft_mode(session_id, True)
            _, events = self.stream_chat(session_id, "请先生成一版观察阶段草案")

            event_names = [name for name, _ in events]
            self.assertIn("draft", event_names)
            self.assertNotIn("proposal", event_names)

            done_payload = events[-1][1]
            self.assertTrue(done_payload["draft_updated"])
            self.assertIsNone(done_payload["draft_proposal"])
            self.assertEqual(done_payload["draft_request_kind"], "generate")
            self.assertEqual(done_payload["proposal_kind"], "generate")

            session = self.get_session(session_id)
            output = next(item for item in session["outputs"] if item["stage_id"] == stage_id)
            self.assertTrue(output["draft_content"])

            proposal_response = self.client.get(
                f"/api/sessions/{session_id}/draft-proposal",
                params={"stage_id": stage_id},
            )
            self.assertEqual(proposal_response.status_code, 200)
            self.assertIsNone(proposal_response.json()["data"])

            with SessionLocal() as db:
                self.assertEqual(
                    db.query(DraftProposalModel)
                    .filter(
                        DraftProposalModel.session_id == session_id,
                        DraftProposalModel.stage_id == stage_id,
                        DraftProposalModel.status == "pending",
                    )
                    .count(),
                    0,
                )
        finally:
            self.delete_session(session_id)

    def test_existing_draft_edit_still_creates_pending_proposal(self):
        session_id, stage_id = self.create_session()
        try:
            self.set_draft_mode(session_id, True)
            base_content = "### 观察阶段草案\n\n1. 学生先记录现象。\n2. 教师组织交流。"
            response = self.client.put(
                f"/api/sessions/{session_id}/stages/{stage_id}/draft",
                json={"draft_content": base_content},
            )
            self.assertEqual(response.status_code, 200)

            edit_response = self.client.post(
                f"/api/sessions/{session_id}/chat",
                json={
                    "type": "chat",
                    "message": "把第一条改得更具体一点",
                    "draft_request_kind": "edit",
                    "selection": {
                        "selected_text": "1. 学生先记录现象。",
                        "start_offset": 15,
                        "end_offset": 27,
                        "stage_id": stage_id,
                    },
                },
            )
            self.assertEqual(edit_response.status_code, 200)
            events = parse_sse(edit_response.text)
            event_names = [name for name, _ in events]

            self.assertIn("draft", event_names)
            self.assertIn("proposal", event_names)

            done_payload = events[-1][1]
            self.assertTrue(done_payload["draft_updated"])
            self.assertIsNotNone(done_payload["draft_proposal"])
            self.assertEqual(done_payload["draft_request_kind"], "edit")
            self.assertEqual(done_payload["proposal_kind"], "edit")

            proposal_response = self.client.get(
                f"/api/sessions/{session_id}/draft-proposal",
                params={"stage_id": stage_id},
            )
            self.assertEqual(proposal_response.status_code, 200)
            proposal_data = proposal_response.json()["data"]
            self.assertIsNotNone(proposal_data)
            self.assertEqual(proposal_data["proposal_kind"], "edit")
            with SessionLocal() as db:
                self.assertEqual(
                    db.query(DraftProposalModel)
                    .filter(
                        DraftProposalModel.session_id == session_id,
                        DraftProposalModel.stage_id == stage_id,
                        DraftProposalModel.status == "pending",
                    )
                    .count(),
                    1,
                )
        finally:
            self.delete_session(session_id)

    def test_rollback_removes_three_messages_and_restores_previous_draft(self):
        session_id, stage_id = self.create_session()
        try:
            self.set_draft_mode(session_id, True)
            self.stream_chat(session_id, "第一版观察任务")
            first_session = self.get_session(session_id)
            first_draft = next(
                item["draft_content"]
                for item in first_session["outputs"]
                if item["stage_id"] == stage_id
            )
            self.assertTrue(first_draft)

            second_response = self.client.post(
                f"/api/sessions/{session_id}/chat",
                json={
                    "type": "chat",
                    "message": "第二版证据记录任务",
                    "draft_request_kind": "generate",
                },
            )
            self.assertEqual(second_response.status_code, 200)
            second_events = parse_sse(second_response.text)
            proposal = second_events[-1][1]["draft_proposal"]
            self.assertIsNotNone(proposal)
            actions = [
                {"hunk_id": segment["id"], "action": "accept"}
                for segment in proposal["segments"]
                if segment["kind"] != "equal"
            ]
            apply_response = self.client.post(
                f"/api/sessions/{session_id}/draft-proposals/{proposal['id']}/actions",
                json={"actions": actions},
            )
            self.assertEqual(apply_response.status_code, 200)

            second_session = self.get_session(session_id)
            second_draft = next(
                item["draft_content"]
                for item in second_session["outputs"]
                if item["stage_id"] == stage_id
            )
            self.assertNotEqual(first_draft, second_draft)
            self.assertEqual(len(self.get_messages(session_id)), 4)

            response = self.client.post(
                f"/api/sessions/{session_id}/rollback",
                json={"steps": 1, "stage_back": False},
            )
            self.assertEqual(response.status_code, 200)
            rollback_data = response.json()["data"]
            self.assertEqual(len(rollback_data["deleted_message_ids"]), 2)
            self.assertEqual(rollback_data["restored_drafts"][stage_id], first_draft)
            self.assertEqual(len(self.get_messages(session_id)), 2)

            with SessionLocal() as db:
                self.assertEqual(
                    db.query(ChatTurnModel)
                    .filter(ChatTurnModel.session_id == session_id)
                    .count(),
                    1,
                )
        finally:
            self.delete_session(session_id)

    def test_expert_selection_is_one_request_only(self):
        session_id, _ = self.create_session()
        try:
            self.set_draft_mode(session_id, True)
            response = self.client.post(
                f"/api/sessions/{session_id}/chat",
                json={
                    "type": "chat",
                    "message": "怎样控制实验变量？",
                    "expert_id": "physics_teacher_agent",
                },
            )
            self.assertEqual(response.status_code, 200)
            events = parse_sse(response.text)
            delta_types = [data["message_type"] for name, data in events if name == "delta"]
            self.assertTrue(delta_types)
            self.assertEqual(set(delta_types), {"expert_advice"})
            self.assertEqual(events[-1][1]["agent_id"], "physics_teacher_agent")
            self.assertEqual(events[-1][1]["rag_sources"], [])
            self.assertIsNone(events[-1][1]["rag_record_id"])

            messages = self.get_messages(session_id)
            self.assertEqual([item["message_type"] for item in messages], ["chat", "expert_advice"])
            self.assertFalse(self.get_session(session_id)["outputs"][0]["draft_content"])
            with SessionLocal() as db:
                history = ContextService.format_dialog_history(
                    ContextService.load_messages(db, session_id)
                )
                self.assertIn("领域专家-physics_teacher_agent", history)
                turn = (
                    db.query(ChatTurnModel)
                    .filter(ChatTurnModel.session_id == session_id)
                    .one()
                )
                self.assertTrue(turn.expert_message_id)
                self.assertEqual(turn.expert_message_id, turn.assistant_message_id)

            self.set_draft_mode(session_id, False)
            _, next_events = self.stream_chat(session_id, "继续推进教学设计")
            self.assertEqual(
                {data["message_type"] for name, data in next_events if name == "delta"},
                {"main_tutor"},
            )

            invalid = self.client.post(
                f"/api/sessions/{session_id}/chat",
                json={"type": "chat", "message": "错误专家", "expert_id": "main_tutor"},
            )
            self.assertEqual(invalid.status_code, 400)
        finally:
            self.delete_session(session_id)

    def test_stage_back_keeps_messages_and_reopens_previous_stage(self):
        session_id, stage_id = self.create_session()
        try:
            self.stream_chat(session_id, "保留这一轮对话")
            draft = next(
                item["draft_content"]
                for item in self.get_session(session_id)["outputs"]
                if item["stage_id"] == stage_id
            )
            advance_response = self.client.post(
                f"/api/sessions/{session_id}/chat",
                json={
                    "type": "sys_action",
                    "action": "next_stage",
                    "final_content": draft,
                },
            )
            self.assertEqual(advance_response.status_code, 200)
            message_count = len(self.get_messages(session_id))

            rollback_response = self.client.post(
                f"/api/sessions/{session_id}/rollback",
                json={"steps": 1, "stage_back": True},
            )
            self.assertEqual(rollback_response.status_code, 200)
            session = rollback_response.json()["data"]["session"]
            self.assertEqual(session["current_stage_index"], 0)
            self.assertEqual(len(self.get_messages(session_id)), message_count)

            output = next(item for item in session["outputs"] if item["stage_id"] == stage_id)
            self.assertFalse(output["confirmed"])
            self.assertEqual(output["final_content"], "")
            self.assertEqual(output["draft_content"], draft)
        finally:
            self.delete_session(session_id)

    def test_session_files_support_all_formats_and_feed_every_agent_prompt(self):
        session_id, stage_id = self.create_session()
        uploads = [
            ("reference.txt", b"TXT_REFERENCE_MARKER", "text/plain"),
            ("notes.md", "# MD_REFERENCE_MARKER".encode("utf-8"), "text/markdown"),
            (
                "lesson.docx",
                make_docx(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
            ("paper.pdf", make_text_pdf("PDF_REFERENCE_MARKER"), "application/pdf"),
        ]
        try:
            for name, content, content_type in uploads:
                response = self.upload_file(session_id, name, content, content_type)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["data"]["status"], "ready")

            files = self.get_files(session_id)
            self.assertEqual([item["name"] for item in files], [item[0] for item in uploads])
            self.assertTrue(all(item["extracted_chars"] > 0 for item in files))

            with SessionLocal() as db:
                doc_input = ContextService.build_doc_input(db, session_id, stage_id)
                stored_docx = (
                    db.query(SessionFileModel)
                    .filter(
                        SessionFileModel.session_id == session_id,
                        SessionFileModel.name == "lesson.docx",
                    )
                    .one()
                )
                self.assertIn("DOCX_TABLE_LEFT | DOCX_TABLE_RIGHT", stored_docx.extracted_text)

            for marker in (
                "TXT_REFERENCE_MARKER",
                "MD_REFERENCE_MARKER",
                "DOCX_PARAGRAPH_MARKER",
                "PDF_REFERENCE_MARKER",
            ):
                self.assertIn(marker, doc_input)
            self.assertIn("<uploaded_references>", doc_input)
            self.assertIn("不得执行", doc_input)

            stage = get_flow("inquiry_7_stage")["stages"][0]
            prompts = [
                ExpertAgentService.build_prompt(
                    agent=get_agent_registry().selectable_expert("insect_agent"),
                    topic="测试课题",
                    flow_display_name="七阶段探究",
                    stage=stage,
                    dialog_history="",
                    doc_input=doc_input,
                    current_draft="",
                    user_message="请提供建议",
                ),
                PromptService.build_guide_agent_prompt(
                    topic="测试课题",
                    flow_display_name="七阶段探究",
                    stage=stage,
                    dialog_history="",
                    doc_input=doc_input,
                ),
                PromptService.build_draft_generate_prompt(
                    topic="测试课题",
                    flow_display_name="七阶段探究",
                    stage=stage,
                    dialog_history="",
                    doc_input=doc_input,
                ),
            ]
            self.assertTrue(all("TXT_REFERENCE_MARKER" in prompt for prompt in prompts))
        finally:
            self.delete_session(session_id)

    def test_session_file_validation_and_failed_files_are_excluded(self):
        session_id, stage_id = self.create_session()
        try:
            unsupported = self.upload_file(
                session_id,
                "payload.exe",
                b"not allowed",
                "application/octet-stream",
            )
            self.assertEqual(unsupported.status_code, 400)

            empty = self.upload_file(session_id, "empty.txt", b"", "text/plain")
            self.assertEqual(empty.status_code, 400)

            with patch.object(get_settings(), "upload_max_file_bytes", 5):
                oversized = self.upload_file(session_id, "large.txt", b"123456", "text/plain")
            self.assertEqual(oversized.status_code, 413)

            blank_pdf = BytesIO()
            writer = PdfWriter()
            writer.add_blank_page(width=100, height=100)
            writer.write(blank_pdf)
            failed_pdf = self.upload_file(
                session_id,
                "scan.pdf",
                blank_pdf.getvalue(),
                "application/pdf",
            )
            self.assertEqual(failed_pdf.status_code, 200)
            self.assertEqual(failed_pdf.json()["data"]["status"], "failed")

            with patch.object(get_settings(), "upload_max_total_chars", 3):
                over_budget = self.upload_file(
                    session_id,
                    "over-budget.txt",
                    b"four",
                    "text/plain",
                )
            self.assertEqual(over_budget.status_code, 200)
            self.assertEqual(over_budget.json()["data"]["status"], "failed")

            with SessionLocal() as db:
                doc_input = ContextService.build_doc_input(db, session_id, stage_id)
            self.assertNotIn("<uploaded_references>", doc_input)
            self.assertEqual(
                [item["status"] for item in self.get_files(session_id)],
                ["failed", "failed"],
            )
        finally:
            self.delete_session(session_id)

    def test_session_file_count_limit_flow_preservation_and_cleanup(self):
        session_id, _ = self.create_session()
        session_path = None
        try:
            with patch.object(get_settings(), "upload_max_files_per_session", 1):
                first = self.upload_file(
                    session_id,
                    "keep.md",
                    b"FLOW_PRESERVED_REFERENCE",
                    "text/markdown",
                )
                self.assertEqual(first.status_code, 200)
                second = self.upload_file(
                    session_id,
                    "blocked.md",
                    b"blocked",
                    "text/markdown",
                )
                self.assertEqual(second.status_code, 409)

            with SessionLocal() as db:
                row = (
                    db.query(SessionFileModel)
                    .filter(SessionFileModel.session_id == session_id)
                    .one()
                )
                session_path = SessionFileService.absolute_storage_path(row.stored_path)
            self.assertTrue(session_path.exists())

            switched = self.client.post(
                f"/api/sessions/{session_id}/select_flow",
                json={"flow_name": "three_step_inquiry", "clear_messages": True},
            )
            self.assertEqual(switched.status_code, 409)
            self.assertEqual(len(self.get_files(session_id)), 1)

            file_id = self.get_files(session_id)[0]["id"]
            deleted = self.client.delete(f"/api/sessions/{session_id}/files/{file_id}")
            self.assertEqual(deleted.status_code, 200)
            self.assertFalse(session_path.exists())

            replacement = self.upload_file(
                session_id,
                "cleanup.txt",
                b"DELETE_WITH_SESSION",
                "text/plain",
            )
            self.assertEqual(replacement.status_code, 200)
            with SessionLocal() as db:
                row = (
                    db.query(SessionFileModel)
                    .filter(SessionFileModel.session_id == session_id)
                    .one()
                )
                session_path = SessionFileService.absolute_storage_path(row.stored_path)
            self.assertTrue(session_path.exists())

            self.delete_session(session_id)
            session_id = ""
            self.assertFalse(session_path.exists())
        finally:
            if session_id:
                self.delete_session(session_id)

    def test_knowledge_graph_candidates_neighbors_and_graph_rag_chat(self):
        session_id, _ = self.create_session(topic="校园月季昆虫观察")
        try:
            with SessionLocal() as db:
                service = KnowledgeGraphService(db)
                service.import_graph_json(
                    {
                        "entities": [
                            {
                                "id": "plant_rose",
                                "name": "月季",
                                "entity_type": "plant",
                                "aliases": ["玫瑰", "月季花"],
                                "description": "用于测试的植物节点。",
                                "source": "test",
                            },
                            {
                                "id": "insect_aphid",
                                "name": "蚜虫",
                                "entity_type": "insect",
                                "aliases": ["腻虫"],
                                "description": "用于测试的昆虫节点。",
                                "source": "test",
                            },
                            {
                                "id": "insect_ladybug",
                                "name": "七星瓢虫",
                                "entity_type": "insect",
                                "aliases": ["瓢虫"],
                                "description": "用于测试的捕食性昆虫节点。",
                                "source": "test",
                            },
                            {
                                "id": "plant_pine",
                                "name": "松树",
                                "entity_type": "plant",
                                "aliases": [],
                                "description": "与昆虫 Agent 默认图谱无关的测试植物。",
                                "source": "test",
                            },
                            {
                                "id": "concept_photosynthesis",
                                "name": "光合作用",
                                "entity_type": "concept",
                                "aliases": [],
                                "description": "植物合成有机物的过程。",
                                "source": "test",
                            },
                        ],
                        "relations": [
                            {
                                "id": "rel_aphid_feeds_on_rose",
                                "subject_entity_id": "insect_aphid",
                                "predicate": "feeds_on",
                                "object_entity_id": "plant_rose",
                                "description": "蚜虫取食月季。",
                                "evidence_source": "test",
                                "confidence": "high",
                            },
                            {
                                "id": "rel_ladybug_predator_of_aphid",
                                "subject_entity_id": "insect_ladybug",
                                "predicate": "predator_of",
                                "object_entity_id": "insect_aphid",
                                "description": "七星瓢虫捕食蚜虫。",
                                "evidence_source": "test",
                                "confidence": "high",
                            },
                            {
                                "id": "rel_pine_photosynthesis",
                                "subject_entity_id": "plant_pine",
                                "predicate": "performs",
                                "object_entity_id": "concept_photosynthesis",
                                "description": "松树可进行光合作用。",
                                "evidence_source": "test",
                                "confidence": "high",
                            }
                        ],
                    }
                )
                db.commit()

            candidate_response = self.client.post(
                "/api/knowledge/graph/candidates",
                json={
                    "session_id": session_id,
                    "message": "月季旁边为什么经常看到蚜虫和七星瓢虫？",
                    "expert_id": "insect_agent",
                },
            )
            self.assertEqual(candidate_response.status_code, 200)
            candidate_data = candidate_response.json()["data"]
            entity_names = {item["name"] for item in candidate_data["entities"]}
            self.assertTrue({"月季", "蚜虫", "七星瓢虫"}.issubset(entity_names))
            self.assertTrue(candidate_data["recommended_path_ids"])

            relation_ids = {
                relation["id"]
                for relation in candidate_data["relations"]
                if relation["predicate"] in {"feeds_on", "predator_of"}
            }
            self.assertTrue(relation_ids)
            aphid_id = next(
                item["id"] for item in candidate_data["entities"] if item["name"] == "蚜虫"
            )
            neighbor_response = self.client.get(
                f"/api/knowledge/graph/entities/{aphid_id}/neighbors?hops=1"
            )
            self.assertEqual(neighbor_response.status_code, 200)
            neighbor_data = neighbor_response.json()["data"]
            self.assertLessEqual(len(neighbor_data["entities"]), 20)
            self.assertLessEqual(len(neighbor_data["relations"]), 40)

            chat_response = self.client.post(
                f"/api/sessions/{session_id}/chat",
                json={
                    "type": "chat",
                    "message": "月季旁边为什么经常看到蚜虫和七星瓢虫？",
                    "expert_id": "insect_agent",
                    "graph_selection": {
                        "entity_ids": [aphid_id],
                        "relation_ids": list(relation_ids),
                        "path_ids": candidate_data["recommended_path_ids"],
                    },
                },
            )
            self.assertEqual(chat_response.status_code, 200)
            events = parse_sse(chat_response.text)
            self.assertFalse([event for event in events if event[0] == "warning"])

            with SessionLocal() as db:
                record = (
                    db.query(RagRecordModel)
                    .filter(RagRecordModel.session_id == session_id)
                    .order_by(RagRecordModel.created_at.desc())
                    .first()
                )
                self.assertIsNotNone(record)
                source = json.loads(record.source_json)
                graph = source.get("graph") or {}
                self.assertEqual(graph["selected_entity_ids"], [aphid_id])
                self.assertIn("蚜虫", "\n".join(graph["rag_node_queries"]))
                self.assertTrue(graph["paths"])
        finally:
            self.delete_session(session_id)

    def test_knowledge_entity_rag_sources_are_persisted(self):
        with SessionLocal() as db:
            entity = KnowledgeEntityModel(
                id="entity_rag",
                name="节点",
                entity_type="concept",
                aliases_json="[]",
                description="",
                source="test",
                created_at="now",
                updated_at="now",
            )
            source = CurriculumSourceModel(
                source="node-rag.txt",
                updated_at="now",
            )
            db.add_all([entity, source])
            db.flush()
            db.add(
                KnowledgeEntitySourceModel(
                    entity_id=entity.id,
                    source=source.source,
                    created_at="now",
                )
            )
            db.commit()
            rows = (
                db.query(KnowledgeEntitySourceModel)
                .filter(KnowledgeEntitySourceModel.entity_id == entity.id)
                .all()
            )
            self.assertEqual([row.source for row in rows], ["node-rag.txt"])

    def test_graph_import_rejects_unknown_rag_source(self):
        with SessionLocal() as db:
            service = KnowledgeGraphService(db)
            with self.assertRaises(ValueError):
                service.import_graph_json(
                    {
                        "entities": [
                            {
                                "id": "entity_missing_source",
                                "name": "节点",
                                "entity_type": "concept",
                                "rag_sources": ["missing.txt"],
                            }
                        ]
                    }
                )

    def test_graph_import_rejects_malformed_entities_and_relations(self):
        with SessionLocal() as db:
            service = KnowledgeGraphService(db)
            with self.assertRaises(ValueError):
                service.import_graph_json(
                    {"entities": [{"id": "malformed", "name": "", "entity_type": "concept"}]}
                )
            with self.assertRaises(ValueError):
                service.import_graph_json(
                    {
                        "entities": [
                            {
                                "id": "valid_entity",
                                "name": "节点",
                                "entity_type": "concept",
                            }
                        ],
                        "relations": [
                            {
                                "id": "bad_relation",
                                "subject_entity_id": "valid_entity",
                                "predicate": "关联",
                                "object_entity_id": "missing_entity",
                            }
                        ],
                    }
                )

    def test_graph_entity_serialization_includes_rag_sources(self):
        with SessionLocal() as db:
            db.add(
                CurriculumSourceModel(
                    source="serialized-rag.txt",
                    updated_at="now",
                )
            )
            db.commit()
            service = KnowledgeGraphService(db)
            service.import_graph_json(
                {
                    "entities": [
                        {
                            "id": "entity_serialized",
                            "name": "节点",
                            "entity_type": "concept",
                            "rag_sources": ["serialized-rag.txt"],
                        }
                    ]
                }
            )
            db.commit()
            entity = db.get(KnowledgeEntityModel, "entity_serialized")
            self.assertEqual(
                service.serialize_entity(entity)["rag_sources"],
                ["serialized-rag.txt"],
            )

    def test_graph_import_without_rag_sources_preserves_existing_binding(self):
        with SessionLocal() as db:
            db.add(CurriculumSourceModel(source="preserved-rag.txt", updated_at="now"))
            db.flush()
            service = KnowledgeGraphService(db)
            service.import_graph_json(
                {
                    "entities": [
                        {
                            "id": "entity_preserved",
                            "name": "节点",
                            "entity_type": "concept",
                            "rag_sources": ["preserved-rag.txt"],
                        }
                    ]
                }
            )
            db.commit()
            service.import_graph_json(
                {
                    "entities": [
                        {
                            "id": "entity_preserved",
                            "name": "更新后的节点",
                            "entity_type": "concept",
                        }
                    ]
                }
            )
            db.commit()
            entity = db.get(KnowledgeEntityModel, "entity_preserved")
            self.assertEqual(
                service.serialize_entity(entity)["rag_sources"],
                ["preserved-rag.txt"],
            )

    def test_graph_rag_uses_node_sources_intersected_with_expert_permissions(self):
        with SessionLocal() as db:
            entity = KnowledgeEntityModel(
                id="entity_source_resolution",
                name="节点",
                entity_type="concept",
                aliases_json="[]",
                description="",
                source="test",
                created_at="now",
                updated_at="now",
            )
            for source_name in ["allowed.txt", "other.txt", "fallback.txt"]:
                db.add(CurriculumSourceModel(source=source_name, updated_at="now"))
            db.add(entity)
            db.flush()
            db.add_all(
                [
                    KnowledgeEntitySourceModel(
                        entity_id=entity.id,
                        source="allowed.txt",
                        created_at="now",
                    ),
                    KnowledgeEntitySourceModel(
                        entity_id=entity.id,
                        source="other.txt",
                        created_at="now",
                    ),
                ]
            )
            db.commit()
            service = GraphRagService(db)
            resolved = service.resolve_sources(
                selected_entity_ids=[entity.id],
                allowed_sources=["allowed.txt", "fallback.txt"],
            )
            self.assertEqual(resolved["effective_sources"], ["allowed.txt"])
            self.assertEqual(resolved["source_resolution"], "node_configured")

            db.query(KnowledgeEntitySourceModel).delete(synchronize_session=False)
            db.commit()
            resolved = service.resolve_sources(
                selected_entity_ids=[entity.id],
                allowed_sources=["allowed.txt", "fallback.txt"],
            )
            self.assertEqual(resolved["effective_sources"], ["allowed.txt", "fallback.txt"])
            self.assertEqual(resolved["source_resolution"], "expert_fallback")

            db.add(
                KnowledgeEntitySourceModel(
                    entity_id=entity.id,
                    source="other.txt",
                    created_at="now",
                )
            )
            db.commit()
            resolved = service.resolve_sources(
                selected_entity_ids=[entity.id],
                allowed_sources=["allowed.txt", "fallback.txt"],
            )
            self.assertEqual(resolved["effective_sources"], [])
            self.assertEqual(resolved["source_resolution"], "configured_but_not_allowed")

    def test_graph_selection_uses_only_manually_selected_nodes(self):
        with SessionLocal() as db:
            timestamp = "now"
            for entity_id, name in [("entity_a", "节点 A"), ("entity_b", "节点 B"), ("entity_c", "节点 C")]:
                db.add(
                    KnowledgeEntityModel(
                        id=entity_id,
                        name=name,
                        entity_type="concept",
                        aliases_json="[]",
                        description="",
                        source="test",
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                )
            db.flush()
            db.add_all(
                [
                    KnowledgeRelationModel(
                        id="rel_a_b",
                        subject_entity_id="entity_a",
                        predicate="关联",
                        object_entity_id="entity_b",
                        description="",
                        evidence_source="test",
                        confidence="high",
                        created_at=timestamp,
                        updated_at=timestamp,
                    ),
                    KnowledgeRelationModel(
                        id="rel_b_c",
                        subject_entity_id="entity_b",
                        predicate="关联",
                        object_entity_id="entity_c",
                        description="",
                        evidence_source="test",
                        confidence="high",
                        created_at=timestamp,
                        updated_at=timestamp,
                    ),
                ]
            )
            db.commit()
            service = KnowledgeGraphService(db)
            selected = service.selected_graph_payload(
                selected_path_ids=[],
                selected_relation_ids=[],
                selected_entity_ids=["entity_a", "entity_b"],
            )
            self.assertEqual(
                {row["id"] for row in selected["entities"]},
                {"entity_a", "entity_b"},
            )
            self.assertEqual(
                [row["id"] for row in selected["relations"]],
                [],
            )
            self.assertTrue(
                service.validate_selection(
                    message="节点 A 和节点 B",
                    selected_path_ids=[],
                    selected_relation_ids=[],
                    selected_entity_ids=["entity_a", "entity_b"],
                ).valid
            )

    def test_graph_selection_supports_arbitrary_node_subgraphs(self):
        with SessionLocal() as db:
            timestamp = "now"
            for entity_id in ["chain_a", "chain_b", "chain_c"]:
                db.add(
                    KnowledgeEntityModel(
                        id=entity_id,
                        name=entity_id,
                        entity_type="concept",
                        aliases_json="[]",
                        description="",
                        source="test",
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                )
            db.flush()
            db.add_all(
                [
                    KnowledgeRelationModel(
                        id="chain_rel_a_b",
                        subject_entity_id="chain_a",
                        predicate="连接",
                        object_entity_id="chain_b",
                        description="",
                        evidence_source="test",
                        confidence="high",
                        created_at=timestamp,
                        updated_at=timestamp,
                    ),
                    KnowledgeRelationModel(
                        id="chain_rel_b_c",
                        subject_entity_id="chain_b",
                        predicate="连接",
                        object_entity_id="chain_c",
                        description="",
                        evidence_source="test",
                        confidence="high",
                        created_at=timestamp,
                        updated_at=timestamp,
                    ),
                ]
            )
            db.commit()
            service = KnowledgeGraphService(db)
            self.assertTrue(
                service.validate_selection(
                    message="",
                    selected_path_ids=[],
                    selected_relation_ids=[],
                    selected_entity_ids=["chain_a", "chain_c"],
                ).valid
            )
            selected = service.selected_graph_payload(
                selected_path_ids=[],
                selected_relation_ids=["chain_rel_a_b", "chain_rel_b_c"],
                selected_entity_ids=["chain_a", "chain_b", "chain_c"],
            )
            self.assertEqual(
                [row["id"] for row in selected["relations"]],
                ["chain_rel_a_b", "chain_rel_b_c"],
            )

    def test_ecology_alias_mentions_backfill_and_source_replacement_cleanup(self):
        source = f"ecology_alias_{uuid.uuid4().hex}.md"
        alias = f"试验腻虫{uuid.uuid4().hex[:6]}"
        with SessionLocal() as db:
            knowledge = CurriculumKnowledgeService(db)
            knowledge.ingest_chunks(
                source,
                [f"观察记录：月季叶背发现{alias}。"],
                category="ecology",
            )
            graph = KnowledgeGraphService(db)
            entity = graph.create_entity(
                name=f"测试蚜虫{uuid.uuid4().hex[:6]}",
                entity_type="insect",
                aliases=[alias],
                description="别名回填测试节点",
            )
            db.commit()

            state = db.get(CurriculumSourceModel, source)
            self.assertEqual(state.category, "ecology")
            mentions = (
                db.query(KnowledgeEntityMentionModel)
                .filter(KnowledgeEntityMentionModel.entity_id == entity["id"])
                .all()
            )
            self.assertEqual(len(mentions), 1)
            stale_chunk_id = mentions[0].chunk_id

            knowledge.ingest_chunks(
                source,
                ["替换后的资料不再包含原实体。"],
                category="ecology",
            )
            db.commit()
            replacement = db.get(CurriculumChunkModel, stale_chunk_id)
            if replacement is not None:
                self.assertEqual(replacement.content, "替换后的资料不再包含原实体。")
            self.assertEqual(
                db.query(KnowledgeEntityMentionModel)
                .filter(KnowledgeEntityMentionModel.entity_id == entity["id"])
                .count(),
                0,
            )
            knowledge.delete_source(source)
            db.commit()

    def test_lightrag_ecology_sync_validates_evidence_and_preserves_admin_control(self):
        suffix = uuid.uuid4().hex[:8]
        source = f"auto_ecology_{suffix}.md"
        aphid_name = f"测试蚜虫{suffix}"
        aphid_alias = f"测试腻虫{suffix}"
        rose = f"测试月季{suffix}"
        bee = f"测试蜜蜂{suffix}"
        ladybird = f"测试瓢虫{suffix}"
        ant = f"测试蚂蚁{suffix}"
        moss = f"测试苔藓{suffix}"
        result = EcologyExtractionResult(
            entities={
                aphid_alias: ExtractedEntity(aphid_alias, "昆虫"),
                rose: ExtractedEntity(rose, "植物"),
                bee: ExtractedEntity(bee, "insect"),
                ladybird: ExtractedEntity(ladybird, "insect"),
                ant: ExtractedEntity(ant, "insect"),
                moss: ExtractedEntity(moss, "plant"),
            },
            relations=[
                ExtractedRelation(aphid_alias, rose, "取食关系"),
                ExtractedRelation(bee, rose, "访花关系"),
                ExtractedRelation(aphid_alias, ladybird, "捕食关系"),
                ExtractedRelation(ant, moss, "模型误连了跨句实体"),
            ],
            document_id=f"fake-doc-{suffix}",
        )
        extractor = FakeEcologyExtractor(result)
        processor = EcologyGraphJobProcessor(get_settings(), extractor)

        with SessionLocal() as db:
            knowledge = CurriculumKnowledgeService(db)
            knowledge.ingest_chunks(
                source,
                [
                    f"{aphid_alias}取食{rose}的嫩叶。",
                    f"{bee}经常访花{rose}。",
                    f"{aphid_alias}被{ladybird}捕食。",
                    f"{ant}停在石头上。{moss}遭到危害。",
                ],
                category="ecology",
            )
            KnowledgeGraphService(db).create_entity(
                name=aphid_name,
                entity_type="insect",
                aliases=[aphid_alias],
            )
            db.commit()
            job_id = (
                db.query(EcologyGraphSyncJobModel.id)
                .filter(
                    EcologyGraphSyncJobModel.source == source,
                    EcologyGraphSyncJobModel.operation == "sync",
                )
                .one()[0]
            )

        asyncio.run(processor.process_job(job_id))

        with SessionLocal() as db:
            state = db.get(EcologyGraphSourceStateModel, source)
            self.assertEqual(state.status, "ready")
            self.assertEqual(state.relation_count, 3)
            self.assertEqual(state.rejected_count, 1)
            graph = KnowledgeGraphService(db)
            relations = (
                db.query(KnowledgeRelationModel)
                .filter(KnowledgeRelationModel.origin == "lightrag")
                .all()
            )
            source_relation_ids = {
                relation.id
                for relation in relations
                if source in graph.serialize_relation(relation)["evidence_source"]
            }
            self.assertEqual(len(source_relation_ids), 3)
            self.assertEqual(
                {row.predicate for row in relations if row.id in source_relation_ids},
                {"feeds_on", "visits", "predator_of"},
            )
            predator = next(
                row
                for row in relations
                if row.id in source_relation_ids and row.predicate == "predator_of"
            )
            entity_names = {
                row.id: row.name for row in db.query(KnowledgeEntityModel).all()
            }
            self.assertEqual(entity_names[predator.subject_entity_id], ladybird)
            self.assertEqual(entity_names[predator.object_entity_id], aphid_name)
            payload = graph.find_candidate_graph(message=aphid_alias)
            self.assertTrue(
                any(
                    len(path["relation_ids"]) == 2 and "同一植物" in path["reason"]
                    for path in payload["paths"]
                )
            )

            feed_relation = next(
                row
                for row in relations
                if row.id in source_relation_ids and row.predicate == "feeds_on"
            )
            feed_relation_id = feed_relation.id
            serialized = graph.serialize_relation(feed_relation)
            graph.update_relation(
                feed_relation.id,
                subject_entity_id=feed_relation.subject_entity_id,
                predicate=feed_relation.predicate,
                object_entity_id=feed_relation.object_entity_id,
                description="管理员确认后的说明",
                confidence="high",
                evidence_chunk_ids=[item["chunk_id"] for item in serialized["evidence"]],
            )
            db.commit()
            next_job = EcologyGraphSyncService(db).enqueue_source(source, force=True)
            db.commit()

        asyncio.run(processor.process_job(next_job["id"]))

        with SessionLocal() as db:
            feed_relation = db.get(KnowledgeRelationModel, feed_relation_id)
            self.assertEqual(feed_relation.description, "管理员确认后的说明")
            self.assertEqual(feed_relation.management_mode, "manual_override")
            graph = KnowledgeGraphService(db)
            graph.delete_relation(feed_relation.id)
            db.commit()
            suppressed_job = EcologyGraphSyncService(db).enqueue_source(source, force=True)
            db.commit()

        asyncio.run(processor.process_job(suppressed_job["id"]))

        with SessionLocal() as db:
            feed_relation = db.get(KnowledgeRelationModel, feed_relation_id)
            self.assertEqual(feed_relation.status, "suppressed")
            self.assertEqual(
                db.query(KnowledgeRelationModel)
                .filter(
                    KnowledgeRelationModel.subject_entity_id == feed_relation.subject_entity_id,
                    KnowledgeRelationModel.predicate == "feeds_on",
                    KnowledgeRelationModel.object_entity_id == feed_relation.object_entity_id,
                )
                .count(),
                1,
            )
            restored = KnowledgeGraphService(db).restore_auto_relation(feed_relation.id)
            self.assertEqual(restored["management_mode"], "auto")
            self.assertEqual(restored["status"], "active")
            CurriculumKnowledgeService(db).delete_source(source)
            db.commit()
            delete_job_id = (
                db.query(EcologyGraphSyncJobModel.id)
                .filter(
                    EcologyGraphSyncJobModel.source == source,
                    EcologyGraphSyncJobModel.operation == "delete",
                )
                .order_by(EcologyGraphSyncJobModel.created_at.desc())
                .first()[0]
            )

        asyncio.run(processor.process_job(delete_job_id))
        self.assertEqual(extractor.deleted_sources, [source])
        with SessionLocal() as db:
            self.assertIsNone(db.get(EcologyGraphSourceStateModel, source))
            for entity in db.query(KnowledgeEntityModel).filter(
                KnowledgeEntityModel.name.in_([aphid_name, rose, bee, ladybird, ant, moss])
            ):
                db.delete(entity)
            db.commit()

    def test_ecology_category_change_cancels_sync_and_queues_cleanup(self):
        source = f"ecology_category_change_{uuid.uuid4().hex}.md"
        with SessionLocal() as db:
            knowledge = CurriculumKnowledgeService(db)
            knowledge.ingest_chunks(
                source,
                ["测试昆虫取食测试植物。"],
                category="ecology",
            )
            db.commit()
            sync_job = (
                db.query(EcologyGraphSyncJobModel)
                .filter(
                    EcologyGraphSyncJobModel.source == source,
                    EcologyGraphSyncJobModel.operation == "sync",
                )
                .one()
            )
            self.assertEqual(sync_job.status, "queued")

            knowledge.ingest_chunks(
                source,
                ["已经转为普通课程资料。"],
                category="curriculum",
            )
            db.commit()
            self.assertEqual(sync_job.status, "cancelled")
            self.assertEqual(
                db.query(EcologyGraphSyncJobModel)
                .filter(
                    EcologyGraphSyncJobModel.source == source,
                    EcologyGraphSyncJobModel.operation == "delete",
                    EcologyGraphSyncJobModel.status == "queued",
                )
                .count(),
                1,
            )
            knowledge.delete_source(source)
            db.commit()

    def test_ecology_sync_api_is_admin_only_and_reports_jobs(self):
        source = f"ecology_sync_api_{uuid.uuid4().hex}.md"
        admin_client = TestClient(app)
        try:
            registered = admin_client.post(
                "/api/auth/admin/register",
                json={
                    "username": f"ecology_admin_{uuid.uuid4().hex[:8]}",
                    "password": "valid-password-123",
                },
            )
            self.assertEqual(registered.status_code, 200, registered.text)
            with SessionLocal() as db:
                CurriculumKnowledgeService(db).ingest_chunks(
                    source,
                    ["测试蜜蜂访花测试月季。"],
                    category="ecology",
                )
                db.commit()

            denied = self.client.get("/api/knowledge/ecology-graph/sync")
            self.assertEqual(denied.status_code, 403)
            queued = admin_client.post(
                "/api/knowledge/ecology-graph/sync",
                json={"source": source, "force": True},
            )
            self.assertEqual(queued.status_code, 200, queued.text)
            self.assertEqual(queued.json()["data"]["queued_count"], 1)
            status = admin_client.get("/api/knowledge/ecology-graph/sync")
            self.assertEqual(status.status_code, 200, status.text)
            source_jobs = [
                item
                for item in status.json()["data"]["jobs"]
                if item["source"] == source
            ]
            self.assertTrue(source_jobs)
            self.assertEqual(source_jobs[0]["status"], "queued")
        finally:
            with SessionLocal() as db:
                CurriculumKnowledgeService(db).delete_source(source)
                db.commit()
            admin_client.close()

    def test_globi_structured_import_normalizes_evidence_is_idempotent_and_rolls_back(self):
        source_path = TEST_DIR / f"globi_{uuid.uuid4().hex}.tsv.gz"
        with gzip.open(source_path, "wt", encoding="utf-8", newline="") as source_file:
            source_file.write(
                "\n".join(
                [
                    "sourceTaxonName\tsourceTaxonId\tsourceTaxonPath\ttargetTaxonName\ttargetTaxonId\ttargetTaxonPath\tinteractionTypeName\treferenceDoi\treferenceCitation\tlocalityName\tobservationDateTime",
                    "Coccinella septempunctata\tGBIF:1\tAnimalia | Insecta\tAphis fabae\tGBIF:2\tAnimalia | Insecta\tpreysOn\tstudy-1\tLadybird study\tBeijing\t2025-05-01",
                    "Apis mellifera\tGBIF:3\tAnimalia | Insecta\tRosa chinensis\tGBIF:4\tPlantae | Rosales\tpollinates\tstudy-2\tPollination study\t\t",
                    "Rosa chinensis\tGBIF:4\tPlantae | Rosales\tApis mellifera\tGBIF:3\tAnimalia | Insecta\tpollinatedBy\tstudy-3\tReverse pollination study\t\t",
                    "Pieris rapae\tGBIF:5\tAnimalia | Insecta\tBrassica oleracea\tGBIF:6\tPlantae | Brassicales\teats\tstudy-4\tFeeding study\tChina\t",
                    "Aphis fabae\tGBIF:2\tAnimalia | Insecta\tAphidius colemani\tGBIF:7\tAnimalia | Insecta\thasParasite\tstudy-5\tParasitoid study\t\t",
                    "Missing id insect\t\tAnimalia | Insecta\tRosa chinensis\tGBIF:4\tPlantae | Rosales\tpollinates\tstudy-6\tMissing id\t\t",
                    "Apis mellifera\tGBIF:3\tAnimalia | Insecta\tRosa chinensis\tGBIF:4\tPlantae | Rosales\tcoOccursWith\tstudy-7\tUnsupported\t\t",
                ]
                )
            )
        options = GlobiImportOptions()
        first_run_id = ""
        second_run_id = ""
        try:
            with SessionLocal() as db:
                service = GlobiImportService(db)
                preview = service.preview(source_path, options)
                self.assertEqual(preview["total_rows"], 7)
                self.assertEqual(preview["accepted_rows"], 5)
                self.assertEqual(preview["rejection_reasons"]["missing_external_id"], 1)
                self.assertEqual(preview["rejection_reasons"]["unsupported_interaction"], 1)
                first = service.create_run(
                    version="test-v1",
                    source_url="",
                    source_name=source_path.name,
                    staged_path=str(source_path),
                    options=options,
                    created_by="test-admin",
                )
                first_run_id = first["id"]
                db.commit()
                completed = service.process_run(first_run_id)
                self.assertEqual(completed["status"], "completed")
                self.assertEqual(completed["accepted_rows"], 5)
                self.assertEqual(completed["created_relations"], 4)

                graph = KnowledgeGraphService(db)
                payload = graph.find_candidate_graph(message="Apis mellifera")
                self.assertTrue(payload["relations"])
                bee_relation = next(
                    relation
                    for relation in payload["relations"]
                    if relation["predicate"] == "pollinates"
                )
                self.assertTrue(bee_relation["global_only"])
                self.assertEqual(bee_relation["globi_evidence_count"], 2)
                self.assertEqual(bee_relation["evidence_types"], ["globi"])
                self.assertEqual(bee_relation["geographic_scope"], "global")
                selected = graph.selected_graph_payload(
                    selected_path_ids=[],
                    selected_relation_ids=[bee_relation["id"]],
                    selected_entity_ids=[],
                )
                graph_context = graph.format_selected_graph_context(selected)
                self.assertIn("GloBI 全球关系证据", graph_context)
                self.assertIn("不能据此声称", graph_context)

                taxa = db.query(KnowledgeEntityTaxonModel).all()
                self.assertTrue(any(row.external_id == "GBIF:3" for row in taxa))
                self.assertEqual(db.query(GlobiInteractionModel).count(), 5)
                self.assertEqual(db.query(KnowledgeRelationGlobiEvidenceModel).count(), 5)

                second = service.create_run(
                    version="test-v1",
                    source_url="",
                    source_name=source_path.name,
                    staged_path=str(source_path),
                    options=options,
                    created_by="test-admin",
                )
                second_run_id = second["id"]
                db.commit()
                repeated = service.process_run(second_run_id)
                self.assertEqual(repeated["created_entities"], 0)
                self.assertEqual(repeated["created_relations"], 0)
                self.assertEqual(repeated["stats"]["duplicate_rows"], 5)
                self.assertEqual(db.query(GlobiInteractionModel).count(), 5)

                service.rollback(second_run_id)
                db.commit()
                self.assertEqual(db.query(GlobiInteractionModel).count(), 5)
                service.rollback(first_run_id)
                db.commit()
                self.assertEqual(db.query(GlobiInteractionModel).count(), 0)
                self.assertEqual(
                    db.query(KnowledgeRelationModel)
                    .filter(KnowledgeRelationModel.origin == "globi")
                    .count(),
                    0,
                )
                self.assertEqual(
                    db.query(KnowledgeEntityModel)
                    .filter(KnowledgeEntityModel.origin == "globi")
                    .count(),
                    0,
                )
        finally:
            source_path.unlink(missing_ok=True)
            with SessionLocal() as db:
                if first_run_id:
                    db.query(GlobiImportRunModel).filter(GlobiImportRunModel.id == first_run_id).delete()
                if second_run_id:
                    db.query(GlobiImportRunModel).filter(GlobiImportRunModel.id == second_run_id).delete()
                db.commit()

    def test_globi_import_api_is_admin_only_previews_queues_and_rolls_back(self):
        suffix = uuid.uuid4().hex[:8]
        csv_data = (
            "sourceTaxonName,sourceTaxonId,sourceTaxonPath,targetTaxonName,targetTaxonId,targetTaxonPath,interactionTypeName,referenceDoi\n"
            f"API bee {suffix},GBIF:{suffix}1,Animalia | Insecta,API rose {suffix},GBIF:{suffix}2,Plantae | Rosales,pollinates,api-study-{suffix}\n"
        ).encode("utf-8")
        admin_client = TestClient(app)
        run_id = ""
        try:
            registered = admin_client.post(
                "/api/auth/admin/register",
                json={
                    "username": f"globi_admin_{suffix}",
                    "password": "valid-password-123",
                },
            )
            self.assertEqual(registered.status_code, 200, registered.text)
            denied = self.client.get("/api/knowledge/globi/import")
            self.assertEqual(denied.status_code, 403)
            preview = admin_client.post(
                "/api/knowledge/globi/import/preview",
                data={"version": "api-test", "include_insect_insect": "true"},
                files={"file": ("globi.csv", csv_data, "text/csv")},
            )
            self.assertEqual(preview.status_code, 200, preview.text)
            self.assertEqual(preview.json()["data"]["stats"]["accepted_rows"], 1)
            queued = admin_client.post(
                "/api/knowledge/globi/import",
                data={"version": "api-test", "include_insect_insect": "true"},
                files={"file": ("globi.csv", csv_data, "text/csv")},
            )
            self.assertEqual(queued.status_code, 200, queued.text)
            run_id = queued.json()["data"]["id"]
            self.assertEqual(queued.json()["data"]["status"], "queued")
            with SessionLocal() as db:
                run = db.get(GlobiImportRunModel, run_id)
                run.status = "failed"
                run.last_error = "forced retry test"
                db.commit()
            retried = admin_client.post(f"/api/knowledge/globi/import/{run_id}/retry")
            self.assertEqual(retried.status_code, 200, retried.text)
            self.assertEqual(retried.json()["data"]["status"], "queued")
            self.assertEqual(GlobiImportWorker._claim_next_run(), run_id)
            with SessionLocal() as db:
                completed = GlobiImportService(db).process_run(run_id, claimed=True)
                self.assertEqual(completed["status"], "completed")
                self.assertEqual(completed["attempts"], 1)
            summary = admin_client.get(f"/api/knowledge/globi/import/{run_id}/summary")
            self.assertEqual(summary.status_code, 200, summary.text)
            self.assertEqual(summary.json()["data"]["created_relations"], 1)
            rolled_back = admin_client.post(f"/api/knowledge/globi/import/{run_id}/rollback")
            self.assertEqual(rolled_back.status_code, 200, rolled_back.text)
            self.assertEqual(rolled_back.json()["data"]["status"], "rolled_back")
        finally:
            with SessionLocal() as db:
                if run_id:
                    db.query(GlobiImportRunModel).filter(GlobiImportRunModel.id == run_id).delete()
                    db.commit()
            admin_client.close()

    def test_insect_plant_insect_path_prefers_chunk_evidence(self):
        suffix = uuid.uuid4().hex[:8]
        source = f"ecology_path_{suffix}.md"
        with SessionLocal() as db:
            knowledge = CurriculumKnowledgeService(db)
            knowledge.ingest_chunks(
                source,
                [f"昆虫甲{suffix}取食共享植物{suffix}；昆虫乙{suffix}访问共享植物{suffix}。"],
                category="ecology",
            )
            chunk = (
                db.query(CurriculumChunkModel)
                .filter(CurriculumChunkModel.source == source)
                .one()
            )
            graph = KnowledgeGraphService(db)
            insect_a = graph.create_entity(
                name=f"昆虫甲{suffix}", entity_type="insect", aliases=[]
            )
            plant = graph.create_entity(
                name=f"共享植物{suffix}", entity_type="plant", aliases=[]
            )
            insect_b = graph.create_entity(
                name=f"昆虫乙{suffix}", entity_type="insect", aliases=[]
            )
            relation_a = graph.create_relation(
                subject_entity_id=insect_a["id"],
                predicate="feeds_on",
                object_entity_id=plant["id"],
                confidence="high",
                evidence_chunk_ids=[chunk.id],
            )
            relation_b = graph.create_relation(
                subject_entity_id=insect_b["id"],
                predicate="visits",
                object_entity_id=plant["id"],
                confidence="high",
                evidence_chunk_ids=[chunk.id],
            )
            db.commit()

            payload = graph.find_candidate_graph(message=insect_a["name"])
            expected_relations = {relation_a["id"], relation_b["id"]}
            bridge = next(
                path
                for path in payload["paths"]
                if set(path["relation_ids"]) == expected_relations
            )
            self.assertEqual(
                bridge["entity_ids"],
                [insect_a["id"], plant["id"], insect_b["id"]],
            )
            self.assertEqual(bridge["evidence_status"], "verified")
            self.assertIn("同一植物", bridge["reason"])
            self.assertIn(bridge["id"], payload["recommended_path_ids"])

            selected = graph.selected_graph_payload(
                selected_path_ids=[bridge["id"]],
                selected_relation_ids=bridge["relation_ids"],
                selected_entity_ids=bridge["entity_ids"],
            )
            context = graph.format_selected_graph_context(selected)
            self.assertIn("已关联证据", context)
            self.assertIn(source, context)
            self.assertIn("不代表两种昆虫之间存在直接作用", context)

            knowledge.delete_source(source)
            db.commit()
            self.assertEqual(
                db.query(KnowledgeRelationEvidenceModel)
                .filter(KnowledgeRelationEvidenceModel.relation_id.in_(bridge["relation_ids"]))
                .count(),
                0,
            )
            self.assertEqual(
                graph.serialize_relation(db.get(KnowledgeRelationModel, relation_a["id"]))[
                    "evidence_status"
                ],
                "unverified",
            )

    def test_graph_rag_queries_linked_chunks_before_source_fallback(self):
        suffix = uuid.uuid4().hex[:8]
        source = f"linked_first_{suffix}.md"
        with SessionLocal() as db:
            knowledge = CurriculumKnowledgeService(db)
            knowledge.ingest_chunks(source, [f"链路昆虫{suffix}生活在叶片上。"], category="ecology")
            graph = KnowledgeGraphService(db)
            entity = graph.create_entity(
                name=f"链路昆虫{suffix}", entity_type="insect", aliases=[]
            )
            db.commit()
            linked_ids = graph.linked_chunk_ids(
                entity_ids=[entity["id"]], relation_ids=[], allowed_sources=[source]
            )["linked_chunk_ids"]
            self.assertTrue(linked_ids)

            service = GraphRagService(db)
            with patch(
                "app.services.graph_rag_service.CurriculumKnowledgeService.retrieve",
                return_value=[],
            ) as retrieve:
                _, metadata = service.retrieve_for_selection(
                    message="它在哪里生活？",
                    selected_entity_ids=[entity["id"]],
                    allowed_sources=[source],
                )
            self.assertGreaterEqual(retrieve.call_count, 2)
            self.assertEqual(retrieve.call_args_list[0].args[3], linked_ids)
            self.assertIsNone(retrieve.call_args_list[1].args[3])
            self.assertEqual(metadata["retrieval_strategy"], "knowledge_fallback")
            knowledge.delete_source(source)
            db.commit()

    def test_chunk_scoped_retrieval_includes_adjacent_chunks(self):
        suffix = uuid.uuid4().hex[:8]
        source = f"adjacent_chunks_{suffix}.md"
        with SessionLocal() as db:
            knowledge = CurriculumKnowledgeService(db)
            knowledge.ingest_chunks(
                source,
                [
                    f"相邻证据关键词{suffix}",
                    "实体命中的中心片段",
                    "另一个相邻片段",
                ],
                category="ecology",
            )
            chunks = (
                db.query(CurriculumChunkModel)
                .filter(CurriculumChunkModel.source == source)
                .order_by(CurriculumChunkModel.source_index.asc())
                .all()
            )
            results = knowledge.retrieve(
                f"相邻证据关键词{suffix}",
                top_k=1,
                allowed_sources=[source],
                allowed_chunk_ids=[chunks[1].id],
            )
            self.assertEqual(len(results), 1)
            self.assertIn(f"相邻证据关键词{suffix}", results[0].content)
            knowledge.delete_source(source)
            db.commit()

    def test_graph_rag_respects_global_disable_switch(self):
        with SessionLocal() as db:
            entity = KnowledgeEntityModel(
                id="entity_disabled_graph_rag",
                name="节点",
                entity_type="concept",
                aliases_json="[]",
                description="",
                source="test",
                created_at="now",
                updated_at="now",
            )
            db.add(entity)
            db.commit()
            service = GraphRagService(db)
            with patch.object(service.settings, "curriculum_rag_enabled", False):
                context, source = service.retrieve_for_selection(
                    message="节点背景",
                    selected_entity_ids=[entity.id],
                    allowed_sources=["source.txt"],
                )
            self.assertEqual(context, "")
            self.assertEqual(source["mode"], "disabled")

    def test_graph_rag_retrieval_errors_degrade_without_raising(self):
        with SessionLocal() as db:
            entity = KnowledgeEntityModel(
                id="entity_error_graph_rag",
                name="异常节点",
                entity_type="concept",
                aliases_json="[]",
                description="",
                source="test",
                created_at="now",
                updated_at="now",
            )
            db.add(entity)
            db.commit()
            service = GraphRagService(db)
            with patch(
                "app.services.graph_rag_service.CurriculumKnowledgeService.retrieve",
                side_effect=RuntimeError("retrieval failed"),
            ):
                context, source = service.retrieve_for_selection(
                    message="异常节点背景",
                    selected_entity_ids=[entity.id],
                    allowed_sources=["source.txt"],
                )
            self.assertEqual(context, "")
            self.assertEqual(source["mode"], "local_bm25_error")
            self.assertIn("retrieval failed", source["error"])

    def test_knowledge_graph_empty_and_unmatched_messages_return_empty(self):
        session_id, _ = self.create_session(topic="光的折射")
        try:
            with SessionLocal() as db:
                service = KnowledgeGraphService(db)
                service.import_graph_json(
                    {
                        "entities": [
                            {
                                "id": "plant_pine",
                                "name": "松树",
                                "entity_type": "plant",
                                "aliases": [],
                                "description": "与昆虫 Agent 默认图谱无关的测试植物。",
                                "source": "test",
                            },
                            {
                                "id": "concept_photosynthesis",
                                "name": "光合作用",
                                "entity_type": "concept",
                                "aliases": [],
                                "description": "植物合成有机物的过程。",
                                "source": "test",
                            },
                            {
                                "id": "habitat_orphan",
                                "name": "孤立生境",
                                "entity_type": "habitat",
                                "aliases": [],
                                "description": "用于验证全量图谱保留孤立节点。",
                                "source": "test",
                            },
                        ],
                        "relations": [
                            {
                                "id": "rel_pine_photosynthesis",
                                "subject_entity_id": "plant_pine",
                                "predicate": "performs",
                                "object_entity_id": "concept_photosynthesis",
                                "description": "松树可进行光合作用。",
                                "evidence_source": "test",
                                "confidence": "high",
                            }
                        ],
                    }
                )
                relation = db.get(KnowledgeRelationModel, "rel_pine_photosynthesis")
                relation.status = "suppressed"
                db.commit()

                full_graph = service.all_graph()
                self.assertIn("孤立生境", {item["name"] for item in full_graph["entities"]})
                self.assertIn(
                    "rel_pine_photosynthesis",
                    {item["id"] for item in full_graph["relations"]},
                )
                self.assertEqual(full_graph["paths"], [])
                self.assertEqual(full_graph["recommended_path_ids"], [])

            response = self.client.post(
                "/api/knowledge/graph/candidates",
                json={
                    "session_id": session_id,
                    "message": "",
                    "expert_id": "insect_agent",
                },
            )
            self.assertEqual(response.status_code, 200)
            data = response.json()["data"]
            self.assertEqual(data["entities"], [])
            self.assertEqual(data["relations"], [])
            self.assertEqual(data["recommended_path_ids"], [])

            unmatched = self.client.post(
                "/api/knowledge/graph/candidates",
                json={
                    "session_id": session_id,
                    "message": "银河系边缘的量子卫星",
                    "expert_id": "insect_agent",
                },
            )
            self.assertEqual(unmatched.status_code, 200)
            self.assertEqual(unmatched.json()["data"]["entities"], [])
        finally:
            self.delete_session(session_id)

    def test_rural_policy_parser_matches_existing_corpus_structure(self):
        corpus_dir = Path(__file__).resolve().parents[1] / "docs" / "乡村振兴知识库"
        regulation = corpus_dir / "北京市乡村振兴促进条例.docx"
        action_plan = corpus_dir / "关于锚定农业农村现代化扎实做好2026年乡村全面振兴重点工作的实施方案.docx"

        regulation_units = policy_structural_units(
            CurriculumKnowledgeService.extract_text(regulation)
        )
        articles = [unit for unit in regulation_units if unit.chunk_type == "article"]
        self.assertEqual(len(articles), 62)
        self.assertEqual(len({unit.heading_path for unit in articles}), 9)
        self.assertEqual(articles[0].article_number, "第一条")
        self.assertEqual(articles[-1].article_number, "第六十二条")

        action_units = policy_structural_units(
            CurriculumKnowledgeService.extract_text(action_plan)
        )
        tasks = [unit for unit in action_units if unit.chunk_type == "item"]
        self.assertEqual(len(tasks), 24)
        self.assertEqual(len({unit.heading_path for unit in tasks}), 6)

        long_policy = "第一章 总则\n第一条 " + "甲。" * 300 + "\n第二条 乙。"
        chunks = chunk_policy_text(long_policy, size=128, overlap=20)
        self.assertGreater(len(chunks), 2)
        self.assertTrue(all(chunk.article_number in {"第一条", "第二条"} for chunk in chunks))
        self.assertFalse(any("第二条" in chunk.content for chunk in chunks if chunk.article_number == "第一条"))

    def test_knowledge_source_review_filters_and_v4_roundtrip(self):
        admin_client = TestClient(app)
        ordinary_client = TestClient(app)
        password = "valid-password-123"
        source_name = f"rural-policy-{uuid.uuid4().hex[:8]}.txt"
        try:
            self.assertEqual(
                admin_client.post(
                    "/api/auth/admin/register",
                    json={"username": f"knowledge_admin_{uuid.uuid4().hex[:8]}", "password": password},
                ).status_code,
                200,
            )
            self.assertEqual(
                ordinary_client.post(
                    "/api/auth/register",
                    json={"username": f"knowledge_user_{uuid.uuid4().hex[:8]}", "password": password},
                ).status_code,
                200,
            )
            metadata = {
                "title": "北京市乡村测试条例",
                "policy_layer": "foundation",
                "document_type": "local_regulation",
                "authority_scope": "beijing",
                "region_code": "110000",
                "issuing_authority": "北京市人民代表大会常务委员会",
                "document_number": "测试〔2026〕1号",
                "source_url": "https://www.beijing.gov.cn/test/rural-policy",
                "publish_date": "2026-01-01",
                "effective_date": "2026-02-01",
                "validity_status": "current",
                "last_verified_at": "2026-09-15",
                "topics": ["organization_governance", "industry_development"],
            }
            uploaded = admin_client.post(
                "/api/knowledge/sources",
                files={"file": (source_name, "第一章 总则\n第一条 测试职责。\n第二条 测试程序。".encode(), "text/plain")},
                data={"category": "rural_revitalization", "metadata_json": json.dumps(metadata, ensure_ascii=False)},
            )
            self.assertEqual(uploaded.status_code, 200, uploaded.text)
            item = uploaded.json()["data"]
            source_id = item["id"]
            self.assertEqual(item["review_status"], "draft")
            self.assertEqual(item["topics"], ["industry_development", "organization_governance"])
            chunk_ids_before = [
                chunk["id"]
                for chunk in admin_client.get(
                    f"/api/knowledge/sources/{source_id}/chunks"
                ).json()["data"]
            ]
            metadata_only = admin_client.patch(
                f"/api/knowledge/sources/{source_id}",
                data={"metadata_json": json.dumps({"title": "北京市乡村测试条例（核对稿）"}, ensure_ascii=False)},
            )
            self.assertEqual(metadata_only.status_code, 200, metadata_only.text)
            self.assertEqual(
                chunk_ids_before,
                [
                    chunk["id"]
                    for chunk in admin_client.get(
                        f"/api/knowledge/sources/{source_id}/chunks"
                    ).json()["data"]
                ],
            )

            ordinary_list = ordinary_client.get(
                "/api/knowledge/sources", params={"category": "rural_revitalization"}
            )
            self.assertFalse(any(row["id"] == source_id for row in ordinary_list.json()["data"]))
            legacy_list = ordinary_client.get(
                "/api/curriculum/files", params={"category": "rural_revitalization"}
            )
            self.assertFalse(any(row["source"] == source_name for row in legacy_list.json()["data"]))
            self.assertEqual(
                admin_client.post(f"/api/knowledge/sources/{source_id}/review", json={"action": "submit"}).status_code,
                200,
            )
            published = admin_client.post(
                f"/api/knowledge/sources/{source_id}/review", json={"action": "publish", "note": "结构抽查通过"}
            )
            self.assertEqual(published.status_code, 200, published.text)
            self.assertEqual(published.json()["data"]["review_status"], "published")

            filtered = ordinary_client.get(
                "/api/knowledge/sources",
                params={"policy_layer": "foundation", "topic": "organization_governance", "review_status": "draft"},
            )
            self.assertTrue(any(row["id"] == source_id for row in filtered.json()["data"]))
            invalid_topic = ordinary_client.get(
                "/api/knowledge/sources", params={"topic": "unknown_topic"}
            )
            self.assertEqual(invalid_topic.status_code, 400)
            detail = admin_client.get(f"/api/knowledge/sources/{source_id}").json()["data"]
            self.assertEqual([event["action"] for event in detail["review_events"]], ["submit", "publish"])
            chunks = admin_client.get(f"/api/knowledge/sources/{source_id}/chunks").json()["data"]
            self.assertEqual([chunk["article_number"] for chunk in chunks], ["第一条", "第二条"])

            body_updated = admin_client.patch(
                f"/api/knowledge/sources/{source_id}",
                files={"file": (source_name, "第一章 总则\n第一条 更新后职责。\n第二条 更新后程序。".encode(), "text/plain")},
                data={"metadata_json": "{}"},
            )
            self.assertEqual(body_updated.status_code, 200, body_updated.text)
            self.assertEqual(body_updated.json()["data"]["review_status"], "draft")
            updated_chunks = admin_client.get(
                f"/api/knowledge/sources/{source_id}/chunks"
            ).json()["data"]
            self.assertTrue(all("测试职责" not in chunk["content"] for chunk in updated_chunks))
            self.assertTrue(any("更新后职责" in chunk["content"] for chunk in updated_chunks))
            updated_detail = admin_client.get(f"/api/knowledge/sources/{source_id}").json()["data"]
            self.assertEqual(updated_detail["review_events"][-1]["action"], "content_update")
            self.assertEqual(
                admin_client.post(f"/api/knowledge/sources/{source_id}/review", json={"action": "submit"}).status_code,
                200,
            )
            self.assertEqual(
                admin_client.post(f"/api/knowledge/sources/{source_id}/review", json={"action": "publish"}).status_code,
                200,
            )

            exported = admin_client.get(
                "/api/knowledge/sources/export", params={"category": "rural_revitalization"}
            )
            self.assertEqual(exported.status_code, 200, exported.text)
            with zipfile.ZipFile(BytesIO(exported.content)) as archive:
                self.assertIn("knowledge.json", archive.namelist())
                self.assertIn("review-manifest.json", archive.namelist())
                payload = json.loads(archive.read("knowledge.json"))
                exported_item = next(row for row in payload["sources"] if row["id"] == source_id)
                self.assertEqual(exported_item["policy_layer"], "foundation")
                self.assertEqual(len(exported_item["review_events"]), 5)

            self.assertEqual(admin_client.delete(f"/api/knowledge/sources/{source_id}").status_code, 200)
            bad_bundle = BytesIO()
            with zipfile.ZipFile(BytesIO(exported.content)) as source_archive:
                bad_payload = json.loads(source_archive.read("knowledge.json"))
                bad_payload["sources"][0]["checksum"] = "invalid-checksum"
                with zipfile.ZipFile(bad_bundle, "w", compression=zipfile.ZIP_DEFLATED) as target_archive:
                    for name in source_archive.namelist():
                        target_archive.writestr(
                            name,
                            json.dumps(bad_payload, ensure_ascii=False).encode("utf-8")
                            if name == "knowledge.json"
                            else source_archive.read(name),
                        )
            rejected = admin_client.post(
                "/api/knowledge/sources/import",
                files={"file": ("invalid-v4.zip", bad_bundle.getvalue(), "application/zip")},
            )
            self.assertEqual(rejected.status_code, 400, rejected.text)
            self.assertEqual(admin_client.get(f"/api/knowledge/sources/{source_id}").status_code, 404)
            imported = admin_client.post(
                "/api/knowledge/sources/import",
                files={"file": ("knowledge-v4.zip", exported.content, "application/zip")},
            )
            self.assertEqual(imported.status_code, 200, imported.text)
            restored = admin_client.get(f"/api/knowledge/sources/{source_id}")
            self.assertEqual(restored.status_code, 200, restored.text)
            self.assertEqual(restored.json()["data"]["topics"], item["topics"])
            self.assertEqual(len(restored.json()["data"]["review_events"]), 5)
        finally:
            with SessionLocal() as db:
                row = db.get(CurriculumSourceModel, source_name)
                if row:
                    CurriculumKnowledgeService(db).delete_source(source_name)
                    db.commit()
            admin_client.close()
            ordinary_client.close()


    def test_globi_runtime_query_is_cached_and_never_writes_graph_tables(self):
        csv_body = "\n".join(
            [
                "source_taxon_external_id,source_taxon_name,source_taxon_path,source_taxon_rank,interaction_type,target_taxon_external_id,target_taxon_name,target_taxon_path,target_taxon_rank,referenceCitation,locality",
                "EOL:1045608,Apis mellifera,Animalia | Arthropoda | Insecta,species,visitsFlowersOf,EOL:328672,Rosa chinensis,Plantae | Tracheophyta,species,Sample study,",
                "EOL:1045608,Apis mellifera,Animalia | Arthropoda | Insecta,species,preysOn,EOL:1174737,Aphis gossypii,Animalia | Arthropoda | Insecta,species,Sample study,",
                "EOL:1045608,Apis mellifera,Animalia | Arthropoda | Insecta,species,interactsWith,EOL:328672,Rosa chinensis,Plantae | Tracheophyta,species,Ignored study,",
            ]
        )
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(str(request.url))
            return httpx.Response(200, content=csv_body.encode("utf-8"), request=request)

        async def extract(_system, _history, _message, **_kwargs):
            return json.dumps(
                {
                    "entities": [
                        {
                            "mention": "蜜蜂",
                            "scientific_name": "Apis mellifera",
                            "entity_type": "insect",
                            "taxon_rank": "species",
                            "confidence": 0.99,
                        }
                    ]
                }
            )

        settings = SimpleNamespace(
            globi_runtime_enabled=True,
            globi_runtime_cache_seconds=86400,
            globi_runtime_timeout_seconds=2,
            globi_runtime_max_entities=3,
            globi_runtime_result_limit=250,
            globi_runtime_relation_limit=40,
            globi_runtime_concurrency=2,
            globi_runtime_max_response_bytes=1024 * 1024,
        )
        GlobiRuntimeService.clear_cache()
        with SessionLocal() as db:
            before = (
                db.query(KnowledgeEntityModel).count(),
                db.query(KnowledgeRelationModel).count(),
                db.query(GlobiInteractionModel).count(),
                db.query(GlobiImportRunModel).count(),
            )
            service = GlobiRuntimeService(
                db,
                settings=settings,
                llm_complete=extract,
                http_client_factory=lambda: httpx.AsyncClient(
                    transport=httpx.MockTransport(handler)
                ),
            )
            first = asyncio.run(
                service.query(
                    message="蜜蜂和哪些植物、昆虫有关系？",
                    expert_id="insect_agent",
                    user_id="user-test",
                    session_id="session-test",
                )
            )
            second = asyncio.run(
                service.query(
                    message="蜜蜂和哪些植物、昆虫有关系？",
                    expert_id="insect_agent",
                    user_id="user-test",
                    session_id="session-test",
                )
            )
            after = (
                db.query(KnowledgeEntityModel).count(),
                db.query(KnowledgeRelationModel).count(),
                db.query(GlobiInteractionModel).count(),
                db.query(GlobiImportRunModel).count(),
            )

        self.assertEqual(before, after)
        self.assertEqual(len(requests), 2)
        self.assertFalse(first["globi_runtime"]["cache_hit"])
        self.assertTrue(second["globi_runtime"]["cache_hit"])
        self.assertEqual(
            {row["predicate"] for row in first["relations"]},
            {"visits", "predator_of"},
        )
        self.assertTrue(all(row["origin"] == "globi_runtime" for row in first["relations"]))
        self.assertTrue(all(row["global_only"] for row in first["relations"]))
        self.assertNotIn("interactsWith", json.dumps(first))

        query_id = first["globi_runtime"]["query_id"]
        selected, warning = service.select_snapshot(
            query_id=query_id,
            user_id="user-test",
            session_id="session-test",
            entity_ids=[first["entities"][0]["id"]],
            relation_ids=[first["relations"][0]["id"]],
            path_ids=[],
        )
        self.assertFalse(warning)
        context = service.format_context(selected or {})
        self.assertIn("GloBI 全球数据库显示", context)
        self.assertIn("不等同于九龙山或门头沟本地观察", context)

    def test_globi_runtime_skips_other_agents_without_llm_or_http(self):
        calls = []

        async def extract(*_args, **_kwargs):
            calls.append("llm")
            return "{}"

        settings = SimpleNamespace(
            globi_runtime_enabled=True,
            globi_runtime_cache_seconds=86400,
            globi_runtime_timeout_seconds=2,
            globi_runtime_max_entities=3,
            globi_runtime_result_limit=250,
            globi_runtime_relation_limit=40,
            globi_runtime_concurrency=2,
            globi_runtime_max_response_bytes=1024 * 1024,
        )
        with SessionLocal() as db:
            payload = asyncio.run(
                GlobiRuntimeService(db, settings=settings, llm_complete=extract).query(
                    message="蜜蜂",
                    expert_id="curriculum_agent",
                    user_id="user-test",
                    session_id="session-test",
                )
            )
        self.assertEqual(payload["globi_runtime"]["status"], "skipped")
        self.assertEqual(calls, [])

    def test_ecology_chat_emits_runtime_graph_and_uses_it_without_persisting_payload(self):
        session_id, _stage_id = self.create_session(topic="蜜蜂与月季")
        entity_a = "globi_runtime_entity_bee"
        entity_b = "globi_runtime_entity_rose"
        relation_id = "globi_runtime_relation_bee_rose"
        path_id = f"globi_runtime_path_{relation_id}"
        runtime_graph = {
            "entities": [
                {
                    "id": entity_a,
                    "name": "Apis mellifera",
                    "entity_type": "insect",
                    "aliases": ["蜜蜂"],
                    "description": "",
                    "source": "GloBI API",
                    "rag_sources": [],
                    "mention_count": 0,
                    "origin": "globi_runtime",
                    "management_mode": "auto",
                    "extractor_model": "GloBI API",
                    "extractor_version": "runtime",
                    "last_auto_sync_at": "",
                    "taxa": [],
                },
                {
                    "id": entity_b,
                    "name": "Rosa chinensis",
                    "entity_type": "plant",
                    "aliases": ["月季"],
                    "description": "",
                    "source": "GloBI API",
                    "rag_sources": [],
                    "mention_count": 0,
                    "origin": "globi_runtime",
                    "management_mode": "auto",
                    "extractor_model": "GloBI API",
                    "extractor_version": "runtime",
                    "last_auto_sync_at": "",
                    "taxa": [],
                },
            ],
            "relations": [
                {
                    "id": relation_id,
                    "subject_entity_id": entity_a,
                    "predicate": "pollinates",
                    "predicate_label": "授粉",
                    "object_entity_id": entity_b,
                    "description": "全球关系",
                    "evidence_source": "GloBI API",
                    "confidence": "medium",
                    "evidence_status": "verified",
                    "evidence": [],
                    "evidence_types": ["globi"],
                    "geographic_scope": "global",
                    "global_only": True,
                    "globi_evidence_count": 1,
                    "globi_evidence": [
                        {
                            "id": "runtime-evidence",
                            "raw_interaction_type": "pollinates",
                            "study_source_id": "study",
                            "study_source_citation": "Sample study",
                            "study_url": "",
                            "study_doi": "",
                            "study_source_archive_uri": "",
                            "locality": "",
                            "latitude": "",
                            "longitude": "",
                            "event_date": "",
                            "region_status": "global",
                        }
                    ],
                    "origin": "globi_runtime",
                    "management_mode": "auto",
                    "status": "active",
                    "extractor_model": "GloBI API",
                    "extractor_version": "runtime",
                    "last_auto_sync_at": "",
                }
            ],
            "paths": [
                {
                    "id": path_id,
                    "entity_ids": [entity_a, entity_b],
                    "relation_ids": [relation_id],
                    "score": 2,
                    "evidence_status": "verified",
                    "reason": "GloBI 全球数据库关系",
                }
            ],
            "recommended_path_ids": [path_id],
            "globi_runtime": {
                "query_id": "globi_query_chat_test",
                "status": "success",
                "cache_hit": False,
                "queried_entities": [
                    {
                        "mention": "蜜蜂",
                        "scientific_name": "Apis mellifera",
                        "entity_type": "insect",
                    }
                ],
                "relation_count": 1,
                "warning": "",
            },
        }
        prompts = []

        async def fake_query(_service, **_kwargs):
            return runtime_graph

        async def fake_expert_stream(*, agent, system_prompt, message):
            prompts.append(system_prompt)
            yield "GloBI 全球数据库显示蜜蜂与月季存在授粉关系；该记录不等同于本地观察。"

        try:
            with SessionLocal() as db:
                before = (
                    db.query(KnowledgeEntityModel).count(),
                    db.query(KnowledgeRelationModel).count(),
                    db.query(GlobiInteractionModel).count(),
                    db.query(GlobiImportRunModel).count(),
                )
            with patch(
                "app.api.chat.GlobiRuntimeService.query",
                new=fake_query,
            ), patch(
                "app.api.chat.ExpertAgentService.chat_stream",
                new=fake_expert_stream,
            ):
                response = self.client.post(
                    f"/api/sessions/{session_id}/chat",
                    json={
                        "type": "chat",
                        "message": "蜜蜂和月季有什么关系？",
                        "expert_id": "insect_agent",
                    },
                )
            self.assertEqual(response.status_code, 200, response.text)
            events = parse_sse(response.text)
            event_names = [name for name, _payload in events]
            self.assertIn("graph_progress", event_names)
            self.assertIn("graph", event_names)
            self.assertLess(event_names.index("graph_progress"), event_names.index("graph"))
            self.assertLess(event_names.index("graph"), event_names.index("delta"))
            graph_event = next(payload for name, payload in events if name == "graph")
            self.assertEqual(graph_event["graph"]["globi_runtime"]["query_id"], "globi_query_chat_test")
            self.assertTrue(prompts)
            self.assertIn("GloBI 全球数据库显示", prompts[0])
            self.assertIn("不等同于九龙山或门头沟本地观察", prompts[0])

            with SessionLocal() as db:
                after = (
                    db.query(KnowledgeEntityModel).count(),
                    db.query(KnowledgeRelationModel).count(),
                    db.query(GlobiInteractionModel).count(),
                    db.query(GlobiImportRunModel).count(),
                )
                record = (
                    db.query(RagRecordModel)
                    .filter(RagRecordModel.session_id == session_id)
                    .order_by(RagRecordModel.created_at.desc())
                    .first()
                )
                if record is not None:
                    self.assertNotIn("globi_runtime_reference", record.context)
            self.assertEqual(before, after)
        finally:
            self.delete_session(session_id)


if __name__ == "__main__":
    unittest.main()
