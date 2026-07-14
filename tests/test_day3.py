import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path


TEST_DIR = Path(tempfile.mkdtemp(prefix="inquiry-agent-architecture-"))
TEST_DB = TEST_DIR / "agents.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["LLM_API_KEY"] = ""
os.environ["DIFY_DATASET_API_KEY"] = ""
os.environ["DIFY_DATASET_ID"] = ""
os.environ["DIFY_STAGE_AGENT_MODE"] = "mock"
os.environ["DIFY_STAGE_AGENTS_JSON"] = ""

from fastapi.testclient import TestClient

from app.db.database import SessionLocal, engine
from app.db.models import (
    AgentConversationModel,
    ChatTurnModel,
    RagRecordModel,
)
from app.main import app


EXPECTED_STAGE_AGENTS = [
    "stage_observation_start",
    "stage_question_refine",
    "stage_hypothesis",
    "stage_experiment_design",
    "stage_new_questions",
    "stage_conclusion",
    "stage_extension",
]


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


class AgentArchitectureApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        engine.dispose()
        shutil.rmtree(TEST_DIR, ignore_errors=True)

    def create_session(self) -> tuple[str, str]:
        response = self.client.post(
            "/api/sessions",
            json={"topic": "光的折射", "flow_name": "inquiry_7_stage"},
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

    def test_seven_stages_bind_to_seven_stage_agents(self):
        flow_response = self.client.get("/api/flows")
        self.assertEqual(flow_response.status_code, 200)
        inquiry_flow = next(
            item
            for item in flow_response.json()["data"]
            if item["name"] == "inquiry_7_stage"
        )
        self.assertEqual(
            [stage["agent_id"] for stage in inquiry_flow["stages"]],
            EXPECTED_STAGE_AGENTS,
        )

        session_id, _ = self.create_session()
        try:
            agent_response = self.client.get(f"/api/sessions/{session_id}/dify_agents")
            self.assertEqual(agent_response.status_code, 200)
            agents = agent_response.json()["data"]
            self.assertEqual([item["id"] for item in agents], EXPECTED_STAGE_AGENTS)
            self.assertTrue(all("stage_id" in item for item in agents))
            self.assertTrue(all(item["configured"] for item in agents))
            self.assertTrue(all(item["mode"] == "prompt" for item in agents))
        finally:
            self.delete_session(session_id)

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
            self.assertIn("draft", event_names)
            self.assertEqual(event_names[-1], "done")
            self.assertFalse(events[-1][1]["degraded"])
            self.assertEqual(response.headers["cache-control"], "no-cache")
            self.assertEqual(response.headers["x-accel-buffering"], "no")

            messages = self.get_messages(session_id)
            self.assertEqual(
                [item["message_type"] for item in messages],
                ["chat", "main_tutor"],
            )
            self.assertEqual(
                [item["agent_id"] for item in messages],
                [None, "main_agent"],
            )
            self.assertNotIn("===DRAFT_START===", messages[1]["content"])

            session = self.get_session(session_id)
            output = next(item for item in session["outputs"] if item["stage_id"] == stage_id)
            self.assertTrue(output["draft_content"])

            with SessionLocal() as db:
                turn = (
                    db.query(ChatTurnModel)
                    .filter(ChatTurnModel.session_id == session_id)
                    .one()
                )
                self.assertFalse(turn.expert_message_id)
                self.assertEqual(
                    db.query(RagRecordModel)
                    .filter(RagRecordModel.session_id == session_id)
                    .count(),
                    0,
                )
                self.assertEqual(
                    db.query(AgentConversationModel)
                    .filter(AgentConversationModel.session_id == session_id)
                    .count(),
                    0,
                )
        finally:
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

    def test_rollback_removes_three_messages_and_restores_previous_draft(self):
        session_id, stage_id = self.create_session()
        try:
            self.stream_chat(session_id, "第一版观察任务")
            first_session = self.get_session(session_id)
            first_draft = next(
                item["draft_content"]
                for item in first_session["outputs"]
                if item["stage_id"] == stage_id
            )

            self.stream_chat(session_id, "第二版证据记录任务")
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

    def test_conversation_ids_are_reused_per_stage_and_isolated_between_stages(self):
        session_id, _ = self.create_session()
        try:
            self.client.put("/api/settings/chat-mode", json={"chat_mode": "subagent"})
            self.stream_chat(session_id, "观察问题一")
            self.stream_chat(session_id, "观察问题二")
            with SessionLocal() as db:
                observation_row = (
                    db.query(AgentConversationModel)
                    .filter(
                        AgentConversationModel.session_id == session_id,
                        AgentConversationModel.agent_id == "stage_observation_start",
                    )
                    .one()
                )
                observation_conversation_id = observation_row.conversation_id
                self.assertEqual(
                    db.query(AgentConversationModel)
                    .filter(AgentConversationModel.session_id == session_id)
                    .count(),
                    1,
                )

            current = self.get_session(session_id)
            current_draft = current["outputs"][0]["draft_content"]
            advance = self.client.post(
                f"/api/sessions/{session_id}/chat",
                json={
                    "type": "sys_action",
                    "action": "next_stage",
                    "final_content": current_draft,
                },
            )
            self.assertEqual(advance.status_code, 200)
            self.stream_chat(session_id, "请提炼核心问题")

            with SessionLocal() as db:
                rows = (
                    db.query(AgentConversationModel)
                    .filter(AgentConversationModel.session_id == session_id)
                    .all()
                )
                self.assertEqual({row.agent_id for row in rows}, {
                    "stage_observation_start",
                    "stage_question_refine",
                })

            stage_back = self.client.post(
                f"/api/sessions/{session_id}/rollback",
                json={"steps": 1, "stage_back": True},
            )
            self.assertEqual(stage_back.status_code, 200)
            self.stream_chat(session_id, "回到观察阶段继续补充")

            with SessionLocal() as db:
                observation_row = (
                    db.query(AgentConversationModel)
                    .filter(
                        AgentConversationModel.session_id == session_id,
                        AgentConversationModel.agent_id == "stage_observation_start",
                    )
                    .one()
                )
                self.assertEqual(
                    observation_row.conversation_id,
                    observation_conversation_id,
                )
                self.assertEqual(
                    db.query(AgentConversationModel)
                    .filter(AgentConversationModel.session_id == session_id)
                    .count(),
                    2,
                )
        finally:
            self.client.put("/api/settings/chat-mode", json={"chat_mode": "main"})
            self.delete_session(session_id)

    def test_subagent_mode_streams_without_main_reply(self):
        session_id, _ = self.create_session()
        try:
            response = self.client.put(
                "/api/settings/chat-mode",
                json={"chat_mode": "subagent"},
            )
            self.assertEqual(response.status_code, 200)
            _, events = self.stream_chat(session_id, "专家不可用时继续")
            warning_events = [data for name, data in events if name == "warning"]
            self.assertEqual(warning_events, [])
            done = events[-1][1]
            self.assertFalse(done["degraded"])
            self.assertIsNone(done["failed_agent_id"])
            self.assertEqual(done["chat_mode"], "subagent")

            messages = self.get_messages(session_id)
            self.assertEqual([item["message_type"] for item in messages], ["chat", "stage_expert"])
            with SessionLocal() as db:
                self.assertEqual(
                    db.query(AgentConversationModel)
                    .filter(AgentConversationModel.session_id == session_id)
                    .count(),
                    1,
                )
                row = (
                    db.query(AgentConversationModel)
                    .filter(AgentConversationModel.session_id == session_id)
                    .one()
                )
                self.assertEqual(row.agent_id, "stage_observation_start")
                self.assertTrue(row.conversation_id.startswith("mock_stage_observation_start"))
        finally:
            self.client.put("/api/settings/chat-mode", json={"chat_mode": "main"})
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


if __name__ == "__main__":
    unittest.main()
