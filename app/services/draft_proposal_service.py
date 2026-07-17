import datetime as dt
import difflib
import json
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import DraftProposalModel, StageOutputModel


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class DraftProposalService:
    @staticmethod
    def parse_diff_payload(diff_json: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        try:
            payload = json.loads(diff_json or "[]")
        except json.JSONDecodeError:
            return [], {}

        if isinstance(payload, list):
            return payload, {}
        if isinstance(payload, dict):
            segments = payload.get("segments") or []
            meta = payload.get("meta") or {}
            return segments, meta
        return [], {}

    @staticmethod
    def build_diff_payload(segments: list[dict[str, Any]], meta: dict[str, Any] | None = None) -> str:
        payload = {
            "segments": segments,
            "meta": meta or {},
        }
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def build_segments(base_content: str, candidate_content: str) -> list[dict[str, Any]]:
        base_lines = base_content.splitlines(keepends=True)
        candidate_lines = candidate_content.splitlines(keepends=True)
        matcher = difflib.SequenceMatcher(a=base_lines, b=candidate_lines)

        segments: list[dict[str, Any]] = []
        for index, opcode in enumerate(matcher.get_opcodes()):
            tag, i1, i2, j1, j2 = opcode
            base_text = "".join(base_lines[i1:i2])
            candidate_text = "".join(candidate_lines[j1:j2])
            segments.append(
                {
                    "id": f"hunk_{index}",
                    "kind": tag,
                    "base_start": i1,
                    "base_end": i2,
                    "candidate_start": j1,
                    "candidate_end": j2,
                    "base_text": base_text,
                    "candidate_text": candidate_text,
                    "status": "accepted" if tag == "equal" else "pending",
                }
            )
        return segments

    @staticmethod
    def serialize(row: DraftProposalModel | None) -> dict[str, Any] | None:
        if not row:
            return None
        segments, meta = DraftProposalService.parse_diff_payload(row.diff_json or "[]")
        return {
            "id": row.id,
            "session_id": row.session_id,
            "stage_id": row.stage_id,
            "base_content": row.base_content or "",
            "candidate_content": row.candidate_content or "",
            "segments": segments,
            "status": row.status,
            "proposal_kind": meta.get("proposal_kind") or "generate",
            "target_mode": meta.get("target_mode"),
            "target_summary": meta.get("target_summary"),
            "target_range": meta.get("target_range"),
            "highlight_segment_ids": meta.get("highlight_segment_ids") or [],
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    @staticmethod
    def get_active_proposal(db: Session, session_id: str, stage_id: str) -> DraftProposalModel | None:
        return (
            db.query(DraftProposalModel)
            .filter(
                DraftProposalModel.session_id == session_id,
                DraftProposalModel.stage_id == stage_id,
                DraftProposalModel.status == "pending",
            )
            .order_by(DraftProposalModel.updated_at.desc(), DraftProposalModel.created_at.desc())
            .first()
        )

    @staticmethod
    def create_proposal(
        db: Session,
        *,
        session_id: str,
        stage_id: str,
        base_content: str,
        candidate_content: str,
        meta: dict[str, Any] | None = None,
        allow_equal: bool = False,
    ) -> DraftProposalModel | None:
        if candidate_content == base_content and not allow_equal:
            return None

        now = now_iso()
        db.query(DraftProposalModel).filter(
            DraftProposalModel.session_id == session_id,
            DraftProposalModel.stage_id == stage_id,
            DraftProposalModel.status == "pending",
        ).update({DraftProposalModel.status: "rejected", DraftProposalModel.updated_at: now})

        segments = DraftProposalService.build_segments(base_content or "", candidate_content or "")
        enriched_meta = dict(meta or {})
        if not enriched_meta.get("highlight_segment_ids"):
            enriched_meta["highlight_segment_ids"] = [
                segment["id"] for segment in segments if segment.get("kind") != "equal"
            ]

        proposal = DraftProposalModel(
            id=new_id("draftp"),
            session_id=session_id,
            stage_id=stage_id,
            base_content=base_content or "",
            candidate_content=candidate_content or "",
            diff_json=DraftProposalService.build_diff_payload(segments, enriched_meta),
            status="pending",
            created_at=now,
            updated_at=now,
        )
        db.add(proposal)
        db.flush()
        return proposal

    @staticmethod
    def recompute_working_content(segments: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        for segment in segments:
            if segment.get("kind") == "equal" or segment.get("status") == "accepted":
                parts.append(segment.get("candidate_text", ""))
            else:
                parts.append(segment.get("base_text", ""))
        return "".join(parts).strip()

    @staticmethod
    def finalize_actions(
        db: Session,
        *,
        proposal_id: str,
        actions: list[dict[str, str]],
        stage_output: StageOutputModel | None,
    ) -> dict[str, Any] | None:
        proposal = db.query(DraftProposalModel).filter(DraftProposalModel.id == proposal_id).first()
        if not proposal:
            return None

        segments, meta = DraftProposalService.parse_diff_payload(proposal.diff_json or "[]")

        action_map = {item["hunk_id"]: item["action"] for item in actions}
        for segment in segments:
            if segment.get("kind") == "equal":
                continue
            action = action_map.get(segment.get("id"))
            if action == "accept":
                segment["status"] = "accepted"
            elif action == "reject":
                segment["status"] = "rejected"

        proposal.diff_json = DraftProposalService.build_diff_payload(segments, meta)
        proposal.updated_at = now_iso()

        change_segments = [segment for segment in segments if segment.get("kind") != "equal"]
        accepted_count = sum(1 for segment in change_segments if segment.get("status") == "accepted")
        rejected_count = sum(1 for segment in change_segments if segment.get("status") == "rejected")
        pending_count = sum(1 for segment in change_segments if segment.get("status") == "pending")

        if pending_count == 0:
            if accepted_count > 0 and rejected_count == 0:
                proposal.status = "accepted"
            elif rejected_count > 0 and accepted_count == 0:
                proposal.status = "rejected"
            elif accepted_count > 0:
                proposal.status = "accepted"
            else:
                proposal.status = "rejected"

        working_content = DraftProposalService.recompute_working_content(segments)
        if stage_output:
            stage_output.draft_content = working_content
            stage_output.updated_at = proposal.updated_at

        return DraftProposalService.serialize(proposal)

    @staticmethod
    def reject_pending_proposals(db: Session, *, session_id: str, stage_id: str) -> None:
        now = now_iso()
        db.query(DraftProposalModel).filter(
            DraftProposalModel.session_id == session_id,
            DraftProposalModel.stage_id == stage_id,
            DraftProposalModel.status == "pending",
        ).update({DraftProposalModel.status: "rejected", DraftProposalModel.updated_at: now})
