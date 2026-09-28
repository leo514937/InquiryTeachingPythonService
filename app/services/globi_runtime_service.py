from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import json
import re
import time
import uuid
from dataclasses import dataclass
from typing import Awaitable, Callable

import httpx
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import KnowledgeEntityTaxonModel
from app.services.globi_import_service import (
    DEFAULT_INTERACTION_TYPES,
    GlobiImportOptions,
    GlobiImportService,
    NormalizedInteraction,
    _common_names,
    _external_key,
)
from app.services.knowledge_graph_service import KnowledgeGraphService, PREDICATE_LABELS
from app.services.llm_service import LLMService


SUPPORTED_EXPERTS = {"insect_agent", "nature_agent"}
GLOBI_API_URL = "https://api.globalbioticinteractions.org/interaction.csv"
RUNTIME_ENTITY_PREFIX = "globi_runtime_entity_"
RUNTIME_RELATION_PREFIX = "globi_runtime_relation_"
RUNTIME_PATH_PREFIX = "globi_runtime_path_"
GLOBI_QUERY_INTERACTION_TYPES = (
    "eats",
    "preysOn",
    "eatenBy",
    "preyedUponBy",
    "pollinates",
    "pollinatedBy",
    "visitsFlowersOf",
    "flowersVisitedBy",
    "hasHabitat",
    "parasiteOf",
    "hasParasite",
)


@dataclass(frozen=True)
class RuntimeTaxon:
    mention: str
    scientific_name: str
    entity_type: str
    taxon_rank: str = ""
    confidence: float = 0.0


@dataclass(frozen=True)
class RuntimeInteraction:
    interaction: NormalizedInteraction
    anchor_key: str
    queried_scientific_name: str


@dataclass
class _CacheEntry:
    value: object
    expires_at: float


class GlobiRuntimeService:
    """Read-only, process-local GloBI lookup used by ecology agents.

    This service deliberately has no SQL write path. It uses the database only to
    resolve existing scientific-name mappings before asking the LLM.
    """

    _direction_cache: dict[tuple[str, str, tuple[str, ...]], _CacheEntry] = {}
    _direction_inflight: dict[
        tuple[str, str, tuple[str, ...]],
        asyncio.Task[list[RuntimeInteraction]],
    ] = {}
    _snapshot_cache: dict[str, _CacheEntry] = {}
    _cache_lock: asyncio.Lock | None = None

    def __init__(
        self,
        db: Session,
        *,
        settings: Settings | None = None,
        llm_complete: Callable[..., Awaitable[str]] | None = None,
        http_client_factory: Callable[[], httpx.AsyncClient] | None = None,
        clock: Callable[[], float] | None = None,
    ):
        self.db = db
        self.settings = settings or get_settings()
        self.llm_complete = llm_complete or LLMService.complete_text
        self.http_client_factory = http_client_factory or self._default_http_client
        self.clock = clock or time.monotonic
        self._semaphore = asyncio.Semaphore(self.settings.globi_runtime_concurrency)

    @classmethod
    def clear_cache(cls) -> None:
        cls._direction_cache.clear()
        cls._direction_inflight.clear()
        cls._snapshot_cache.clear()

    @classmethod
    def _lock(cls) -> asyncio.Lock:
        if cls._cache_lock is None:
            cls._cache_lock = asyncio.Lock()
        return cls._cache_lock

    def _default_http_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=self.settings.globi_runtime_timeout_seconds,
            follow_redirects=True,
            headers={"Accept": "text/csv"},
        )

    async def query(
        self,
        *,
        message: str,
        expert_id: str,
        user_id: str,
        session_id: str,
        progress: Callable[[dict], Awaitable[None]] | None = None,
    ) -> dict:
        async def report(phase: str, percent: int, message: str, **extra) -> None:
            if progress is not None:
                await progress(
                    {
                        "phase": phase,
                        "percent": percent,
                        "message": message,
                        **extra,
                    }
                )

        if expert_id not in SUPPORTED_EXPERTS:
            return self.empty_payload(status="skipped")
        if not self.settings.globi_runtime_enabled:
            return self.empty_payload(status="disabled", warning="GloBI 实时查询未启用")

        await report("extracting", 15, "正在识别问题中的昆虫和植物")
        taxa = await self.extract_taxa(message)
        if not taxa:
            await report("complete", 100, "未识别到可查询的物种实体")
            return self.empty_payload(
                status="empty",
                warning="未从问题中识别出可查询的昆虫或植物实体",
            )

        await report(
            "resolved",
            30,
            f"已识别 {len(taxa)} 个实体，准备查询双向关系",
            queried_entities=[
                {
                    "mention": item.mention,
                    "scientific_name": item.scientific_name,
                    "entity_type": item.entity_type,
                }
                for item in taxa
            ],
        )
        tasks = []
        for taxon in taxa[: self.settings.globi_runtime_max_entities]:
            tasks.append(self._cached_direction(taxon.scientific_name, "source"))
            tasks.append(self._cached_direction(taxon.scientific_name, "target"))
        interactions: list[RuntimeInteraction] = []
        cache_flags: list[bool] = []
        errors: list[str] = []
        completed = 0
        for pending in asyncio.as_completed(tasks):
            try:
                result = await pending
            except Exception as exc:  # preserve successful directions on partial failure
                result = exc
            if isinstance(result, Exception):
                errors.append(self._safe_error(result))
            else:
                rows, cache_hit = result
                interactions.extend(rows)
                cache_flags.append(cache_hit)
            completed += 1
            await report(
                "querying",
                30 + round(50 * completed / max(len(tasks), 1)),
                f"正在获取全球关系（{completed}/{len(tasks)}）",
                completed=completed,
                total=len(tasks),
            )

        await report("building", 88, "正在去重并生成可交互子图")
        payload = self._build_graph(taxa, interactions)
        status = "success" if payload["relations"] else ("failed" if errors and not cache_flags else "empty")
        warning = "；".join(dict.fromkeys(errors))
        query_id = f"globi_query_{uuid.uuid4().hex}"
        payload["globi_runtime"] = {
            "query_id": query_id,
            "status": status,
            "cache_hit": bool(cache_flags) and all(cache_flags),
            "queried_entities": [
                {
                    "mention": item.mention,
                    "scientific_name": item.scientific_name,
                    "entity_type": item.entity_type,
                }
                for item in taxa
            ],
            "relation_count": len(payload["relations"]),
            "warning": warning,
        }
        self._store_snapshot(query_id, user_id, session_id, payload)
        await report(
            "complete",
            100,
            f"GloBI 查询完成，共整理 {len(payload['relations'])} 条关系",
            relation_count=len(payload["relations"]),
            status=status,
        )
        return payload

    async def extract_taxa(self, message: str) -> list[RuntimeTaxon]:
        message = (message or "").strip()
        if not message:
            return []
        resolved: list[RuntimeTaxon] = []
        graph = KnowledgeGraphService(self.db)
        for entity in graph.match_entities(message):
            if entity.entity_type not in {"insect", "plant"}:
                continue
            mappings = (
                self.db.query(KnowledgeEntityTaxonModel)
                .filter(KnowledgeEntityTaxonModel.entity_id == entity.id)
                .order_by(KnowledgeEntityTaxonModel.match_confidence.desc())
                .all()
            )
            scientific_name = next(
                (row.scientific_name.strip() for row in mappings if row.scientific_name.strip()),
                "",
            )
            if scientific_name:
                resolved.append(
                    RuntimeTaxon(
                        mention=entity.name,
                        scientific_name=scientific_name,
                        entity_type=entity.entity_type,
                        taxon_rank=mappings[0].taxon_rank if mappings else "",
                        confidence=1.0,
                    )
                )

        if len(self._dedupe_taxa(resolved)) < self.settings.globi_runtime_max_entities:
            prompt = (
                "你是生物分类名称解析器。只提取用户问题中明确提到的昆虫或植物，最多 3 个；"
                "为每个实体给出最可能的规范拉丁学名。不要提取地点、概念、泛称（如‘昆虫’‘植物’），"
                "不确定到可查询学名时不要输出。只返回 JSON，不要解释。格式："
                '{"entities":[{"mention":"中文原词","scientific_name":"Genus species",'
                '"entity_type":"insect|plant","taxon_rank":"species|genus","confidence":0.0}]}'
            )
            try:
                raw = await self.llm_complete(prompt, [], message, response_kind="expert")
                resolved.extend(self._parse_extraction(raw))
            except Exception:
                pass
        return self._dedupe_taxa(resolved)[: self.settings.globi_runtime_max_entities]

    @staticmethod
    def _parse_extraction(raw: str) -> list[RuntimeTaxon]:
        text = (raw or "").strip()
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S | re.I)
        if fenced:
            text = fenced.group(1)
        else:
            match = re.search(r"\{.*\}", text, re.S)
            if match:
                text = match.group(0)
        try:
            payload = json.loads(text)
        except (TypeError, json.JSONDecodeError):
            return []
        rows = payload.get("entities", []) if isinstance(payload, dict) else []
        result = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            name = str(row.get("scientific_name") or "").strip()
            entity_type = str(row.get("entity_type") or "").strip().casefold()
            if entity_type not in {"insect", "plant"} or not name or name.casefold() == "no:match":
                continue
            try:
                confidence = float(row.get("confidence") or 0.0)
            except (TypeError, ValueError):
                confidence = 0.0
            result.append(
                RuntimeTaxon(
                    mention=str(row.get("mention") or name).strip(),
                    scientific_name=name,
                    entity_type=entity_type,
                    taxon_rank=str(row.get("taxon_rank") or "").strip(),
                    confidence=max(0.0, min(confidence, 1.0)),
                )
            )
        return result

    @staticmethod
    def _dedupe_taxa(rows: list[RuntimeTaxon]) -> list[RuntimeTaxon]:
        result: list[RuntimeTaxon] = []
        seen: set[str] = set()
        for row in rows:
            key = re.sub(r"\s+", " ", row.scientific_name).strip().casefold()
            if not key or key in seen:
                continue
            seen.add(key)
            result.append(row)
        return result

    async def _cached_direction(
        self,
        scientific_name: str,
        direction: str,
    ) -> tuple[list[RuntimeInteraction], bool]:
        whitelist = tuple(sorted(DEFAULT_INTERACTION_TYPES))
        key = (scientific_name.strip().casefold(), direction, whitelist)
        now = self.clock()
        async with self._lock():
            entry = self._direction_cache.get(key)
            if entry is not None and entry.expires_at > now:
                return list(entry.value), True
            if entry is not None:
                self._direction_cache.pop(key, None)
            task = self._direction_inflight.get(key)
            if task is None:
                task = asyncio.create_task(
                    self._fetch_direction(scientific_name, direction)
                )
                self._direction_inflight[key] = task
        try:
            rows = await asyncio.shield(task)
        finally:
            if task.done():
                async with self._lock():
                    if self._direction_inflight.get(key) is task:
                        self._direction_inflight.pop(key, None)
        async with self._lock():
            self._direction_cache[key] = _CacheEntry(
                value=tuple(rows),
                expires_at=self.clock() + self.settings.globi_runtime_cache_seconds,
            )
        return rows, False

    async def _fetch_direction(
        self,
        scientific_name: str,
        direction: str,
    ) -> list[RuntimeInteraction]:
        parameter = "sourceTaxon" if direction == "source" else "targetTaxon"
        params = [
            (parameter, scientific_name),
            *(("interactionType", value) for value in GLOBI_QUERY_INTERACTION_TYPES),
            ("includeObservations", "true"),
            ("limit", str(self.settings.globi_runtime_result_limit)),
        ]
        response_bytes = b""
        max_attempts = max(1, int(getattr(self.settings, "globi_runtime_max_attempts", 3)))
        for attempt in range(max_attempts):
            try:
                async with self._semaphore:
                    async with self.http_client_factory() as client:
                        async with client.stream("GET", GLOBI_API_URL, params=params) as response:
                            response.raise_for_status()
                            chunks: list[bytes] = []
                            size = 0
                            max_bytes = self.settings.globi_runtime_max_response_bytes
                            async for chunk in response.aiter_bytes():
                                if size + len(chunk) > max_bytes:
                                    chunks.append(chunk[: max_bytes - size])
                                    break
                                chunks.append(chunk)
                                size += len(chunk)
                            response_bytes = b"".join(chunks)
                break
            except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
                retryable = not isinstance(exc, httpx.HTTPStatusError) or (
                    exc.response.status_code == 429 or exc.response.status_code >= 500
                )
                if not retryable or attempt + 1 >= max_attempts:
                    raise
                await asyncio.sleep(0.2 * (2**attempt))

        text = response_bytes.decode("utf-8-sig", errors="replace")
        # A byte cap may cut the final CSV record. Dropping the final partial line
        # keeps all complete records instead of failing the entire direction.
        if len(response_bytes) >= self.settings.globi_runtime_max_response_bytes:
            text = text.rsplit("\n", 1)[0]
        reader = csv.DictReader(io.StringIO(text))
        normalizer = GlobiImportService(self.db)
        options = GlobiImportOptions(
            include_insect_insect=True,
            keep_unknown_region=True,
            batch_size=1000,
            interaction_types=tuple(sorted(DEFAULT_INTERACTION_TYPES)),
        )
        result: list[RuntimeInteraction] = []
        for row in reader:
            external_ids = (
                str(row.get("source_taxon_external_id") or row.get("sourceTaxonId") or ""),
                str(row.get("target_taxon_external_id") or row.get("targetTaxonId") or ""),
            )
            if any(not value.strip() or "no:match" in value.casefold() for value in external_ids):
                continue
            item, _reason, _candidate = normalizer.normalize_row(row, options)
            if item is not None:
                query_side = "source" if direction == "source" else "target"
                query_external_id = str(
                    row.get(f"{query_side}_taxon_external_id")
                    or row.get(f"{query_side}TaxonId")
                    or ""
                )
                query_name = str(
                    row.get(f"{query_side}_taxon_name")
                    or row.get(f"{query_side}TaxonName")
                    or scientific_name
                )
                result.append(
                    RuntimeInteraction(
                        interaction=item,
                        anchor_key=self._entity_key(query_external_id, query_name),
                        queried_scientific_name=scientific_name,
                    )
                )
        return result

    def _build_graph(
        self,
        taxa: list[RuntimeTaxon],
        interactions: list[RuntimeInteraction],
    ) -> dict:
        relation_records: dict[tuple[str, str, str], dict] = {}
        entity_records: dict[str, dict] = {}
        anchor_names = {row.scientific_name.casefold(): row for row in taxa}
        anchor_by_key = {
            row.anchor_key: anchor_names[row.queried_scientific_name.casefold()]
            for row in interactions
            if row.queried_scientific_name.casefold() in anchor_names
        }

        for runtime_item in interactions:
            item = runtime_item.interaction
            subject_key = self._entity_key(item.subject.external_id, item.subject.name)
            object_key = self._entity_key(item.object.external_id, item.object.name)
            if subject_key == object_key:
                continue
            subject_id = f"{RUNTIME_ENTITY_PREFIX}{self._digest(subject_key)}"
            object_id = f"{RUNTIME_ENTITY_PREFIX}{self._digest(object_key)}"
            entity_records.setdefault(subject_id, self._serialize_taxon(subject_id, item.subject, anchor_by_key))
            entity_records.setdefault(object_id, self._serialize_taxon(object_id, item.object, anchor_by_key))
            relation_key = (subject_id, item.predicate, object_id)
            relation = relation_records.get(relation_key)
            if relation is None:
                relation_id = f"{RUNTIME_RELATION_PREFIX}{self._digest('|'.join(relation_key))}"
                relation = {
                    "id": relation_id,
                    "subject_entity_id": subject_id,
                    "predicate": item.predicate,
                    "predicate_label": PREDICATE_LABELS.get(item.predicate, item.predicate),
                    "object_entity_id": object_id,
                    "description": "GloBI 全球数据库记录；不能据此单独证明九龙山、门头沟或其他具体地点存在同样关系。",
                    "evidence_source": "GloBI API",
                    "confidence": "medium",
                    "evidence_status": "verified",
                    "evidence": [],
                    "evidence_types": ["globi"],
                    "geographic_scope": "global",
                    "global_only": True,
                    "globi_evidence_count": 0,
                    "globi_evidence": [],
                    "origin": "globi_runtime",
                    "management_mode": "auto",
                    "status": "active",
                    "extractor_model": "GloBI API",
                    "extractor_version": "runtime",
                    "last_auto_sync_at": "",
                }
                relation_records[relation_key] = relation
            evidence_id = f"globi_runtime_evidence_{item.record_hash[:20]}"
            if not any(row["id"] == evidence_id for row in relation["globi_evidence"]):
                relation["globi_evidence"].append(
                    {
                        "id": evidence_id,
                        "raw_interaction_type": item.raw_interaction_type,
                        "study_source_id": item.study_source_id,
                        "study_source_citation": item.study_source_citation,
                        "study_url": item.study_url,
                        "study_doi": item.study_doi,
                        "study_source_archive_uri": item.study_source_archive_uri,
                        "locality": item.locality,
                        "latitude": item.latitude,
                        "longitude": item.longitude,
                        "event_date": item.event_date,
                        "region_status": item.region_status,
                    }
                )
                relation["globi_evidence"] = relation["globi_evidence"][:5]
                relation["globi_evidence_count"] += 1

        anchor_ids = {
            entity_id
            for entity_id, entity in entity_records.items()
            if self._entity_key(
                entity.get("taxa", [{}])[0].get("external_id", ""),
                entity.get("name", ""),
            ) in anchor_by_key
        }
        relation_groups: dict[str, list[dict]] = {}
        for relation in relation_records.values():
            relation_groups.setdefault(relation["predicate"], []).append(relation)
        for rows in relation_groups.values():
            rows.sort(
                key=lambda row: (
                    0 if row["subject_entity_id"] in anchor_ids or row["object_entity_id"] in anchor_ids else 1,
                    -row["globi_evidence_count"],
                    row["id"],
                )
            )
        relations: list[dict] = []
        while relation_groups and len(relations) < self.settings.globi_runtime_relation_limit:
            for predicate in sorted(list(relation_groups)):
                rows = relation_groups[predicate]
                if rows:
                    relations.append(rows.pop(0))
                if not rows:
                    relation_groups.pop(predicate, None)
                if len(relations) >= self.settings.globi_runtime_relation_limit:
                    break
        visible_entity_ids = {
            entity_id
            for relation in relations
            for entity_id in (relation["subject_entity_id"], relation["object_entity_id"])
        }
        entities = [entity_records[entity_id] for entity_id in visible_entity_ids]
        entities.sort(key=lambda row: (0 if row["id"] in anchor_ids else 1, row["name"]))
        paths = self._build_paths(anchor_ids, entities, relations)
        return {
            "entities": entities,
            "relations": relations,
            "paths": paths,
            "recommended_path_ids": [row["id"] for row in paths[:5]],
        }

    @staticmethod
    def _entity_key(external_id: str, name: str) -> str:
        authority, value = _external_key(external_id)
        return f"{authority}:{value}" if value else name.casefold()

    def _serialize_taxon(self, entity_id: str, taxon, anchors: dict[str, RuntimeTaxon]) -> dict:
        authority, external_id = _external_key(taxon.external_id)
        common_names = _common_names(taxon.common_names)
        anchor = anchors.get(self._entity_key(taxon.external_id, taxon.name))
        aliases = list(dict.fromkeys([*common_names, *( [anchor.mention] if anchor and anchor.mention != taxon.name else [])]))
        return {
            "id": entity_id,
            "name": taxon.name,
            "entity_type": taxon.entity_type,
            "aliases": aliases,
            "description": "GloBI API 本轮临时实体",
            "source": "GloBI API",
            "rag_sources": [],
            "mention_count": 0,
            "origin": "globi_runtime",
            "management_mode": "auto",
            "extractor_model": "GloBI API",
            "extractor_version": "runtime",
            "last_auto_sync_at": "",
            "taxa": [
                {
                    "authority": authority,
                    "external_id": external_id,
                    "scientific_name": taxon.name,
                    "taxon_rank": taxon.rank,
                    "common_names": common_names,
                    "match_method": "globi_runtime",
                    "match_confidence": "high",
                }
            ],
        }

    @staticmethod
    def _build_paths(anchor_ids: set[str], entities: list[dict], relations: list[dict]) -> list[dict]:
        entity_by_id = {row["id"]: row for row in entities}
        adjacency: dict[str, list[dict]] = {}
        for relation in relations:
            adjacency.setdefault(relation["subject_entity_id"], []).append(relation)
            adjacency.setdefault(relation["object_entity_id"], []).append(relation)
        paths: dict[tuple[str, ...], dict] = {}

        def other(relation: dict, entity_id: str) -> str:
            return relation["object_entity_id"] if relation["subject_entity_id"] == entity_id else relation["subject_entity_id"]

        def register(path_relations: list[dict], entity_ids: list[str]) -> None:
            relation_ids = [row["id"] for row in path_relations]
            key = tuple(sorted(relation_ids))
            types = [entity_by_id.get(entity_id, {}).get("entity_type") for entity_id in entity_ids]
            bridge = len(types) == 3 and types == ["insect", "plant", "insect"]
            reason = (
                "GloBI 显示两种昆虫通过同一植物形成全球生态关联"
                if bridge
                else "GloBI 全球数据库中与问题实体直接或间接相连的关系"
            )
            score = len(path_relations) * 2 + (3 if bridge else 0)
            candidate = {
                "id": f"{RUNTIME_PATH_PREFIX}{'__'.join(relation_ids)}",
                "entity_ids": entity_ids,
                "relation_ids": relation_ids,
                "score": score,
                "evidence_status": "verified",
                "reason": reason,
            }
            if key not in paths or paths[key]["score"] < score:
                paths[key] = candidate

        starts = sorted(anchor_ids) or sorted(adjacency)
        for start in starts:
            for first in adjacency.get(start, []):
                middle = other(first, start)
                register([first], [start, middle])
                for second in adjacency.get(middle, []):
                    if second["id"] == first["id"]:
                        continue
                    end = other(second, middle)
                    if end != start:
                        register([first, second], [start, middle, end])
        result = list(paths.values())
        result.sort(key=lambda row: (-row["score"], -len(row["relation_ids"]), row["id"]))
        return result[:10]

    @classmethod
    def merge_graphs(cls, local: dict, runtime: dict) -> dict:
        return {
            "entities": [*local.get("entities", []), *runtime.get("entities", [])],
            "relations": [*local.get("relations", []), *runtime.get("relations", [])],
            "paths": [*local.get("paths", []), *runtime.get("paths", [])],
            "recommended_path_ids": [
                *local.get("recommended_path_ids", [])[:5],
                *runtime.get("recommended_path_ids", [])[:5],
            ],
            "globi_runtime": runtime.get("globi_runtime"),
        }

    def _store_snapshot(self, query_id: str, user_id: str, session_id: str, payload: dict) -> None:
        self._snapshot_cache[query_id] = _CacheEntry(
            value={"user_id": user_id, "session_id": session_id, "payload": payload},
            expires_at=self.clock() + self.settings.globi_runtime_cache_seconds,
        )

    def select_snapshot(
        self,
        *,
        query_id: str,
        user_id: str,
        session_id: str,
        entity_ids: list[str],
        relation_ids: list[str],
        path_ids: list[str],
    ) -> tuple[dict | None, str]:
        entry = self._snapshot_cache.get(query_id)
        if entry is None or entry.expires_at <= self.clock():
            self._snapshot_cache.pop(query_id, None)
            return None, "GloBI 临时图谱已过期，请刷新图谱后重新选择。"
        snapshot = entry.value
        if snapshot["user_id"] != user_id or snapshot["session_id"] != session_id:
            return None, "GloBI 临时图谱不属于当前会话，请重新查询。"
        graph = snapshot["payload"]
        entity_set = {row["id"] for row in graph.get("entities", [])}
        relation_set = {row["id"] for row in graph.get("relations", [])}
        path_set = {row["id"] for row in graph.get("paths", [])}
        if (
            any(row not in entity_set for row in entity_ids)
            or any(row not in relation_set for row in relation_ids)
            or any(row not in path_set for row in path_ids)
        ):
            return None, "选择中包含无效或已过期的 GloBI 临时关系。"
        selected_relations = [row for row in graph["relations"] if row["id"] in set(relation_ids)]
        selected_entity_ids = set(entity_ids)
        for relation in selected_relations:
            selected_entity_ids.update((relation["subject_entity_id"], relation["object_entity_id"]))
        selected = {
            "entities": [row for row in graph["entities"] if row["id"] in selected_entity_ids],
            "relations": selected_relations,
            "paths": [row for row in graph["paths"] if row["id"] in set(path_ids)],
            "selected_entity_ids": list(selected_entity_ids),
            "selected_relation_ids": [row["id"] for row in selected_relations],
            "selected_path_ids": path_ids,
        }
        if not selected["entities"]:
            return None, "请先选择至少一个 GloBI 临时图谱节点。"
        return selected, ""

    def snapshot_payload(
        self,
        *,
        query_id: str,
        user_id: str,
        session_id: str,
    ) -> tuple[dict | None, str]:
        entry = self._snapshot_cache.get(query_id)
        if entry is None or entry.expires_at <= self.clock():
            self._snapshot_cache.pop(query_id, None)
            return None, "GloBI 临时图谱已过期，请刷新图谱后重新选择。"
        snapshot = entry.value
        if snapshot["user_id"] != user_id or snapshot["session_id"] != session_id:
            return None, "GloBI 临时图谱不属于当前会话，请重新查询。"
        return snapshot["payload"], ""

    @staticmethod
    def default_selection(payload: dict) -> dict:
        path_ids = payload.get("recommended_path_ids", [])[:1]
        paths = [row for row in payload.get("paths", []) if row["id"] in set(path_ids)]
        relation_ids = {value for path in paths for value in path.get("relation_ids", [])}
        if not relation_ids:
            relation_ids = {row["id"] for row in payload.get("relations", [])[:5]}
        relations = [row for row in payload.get("relations", []) if row["id"] in relation_ids]
        entity_ids = {
            value
            for relation in relations
            for value in (relation["subject_entity_id"], relation["object_entity_id"])
        }
        return {
            "entities": [row for row in payload.get("entities", []) if row["id"] in entity_ids],
            "relations": relations,
            "paths": paths,
            "selected_entity_ids": list(entity_ids),
            "selected_relation_ids": [row["id"] for row in relations],
            "selected_path_ids": path_ids,
        }

    @staticmethod
    def format_context(payload: dict) -> str:
        if not payload.get("relations"):
            return ""
        entity_by_id = {row["id"]: row for row in payload.get("entities", [])}
        lines = [
            "<globi_runtime_reference>",
            "以下关系来自本轮 GloBI 全球数据库实时查询，仅作为外部参考。回答引用时必须明确说‘GloBI 全球数据库显示’，并说明该记录不等同于九龙山或门头沟本地观察。",
            "经共享植物连接的昆虫只表示生态关联，不代表两种昆虫之间存在直接作用。",
        ]
        for index, relation in enumerate(payload.get("relations", [])[:8], start=1):
            subject = entity_by_id.get(relation["subject_entity_id"], {})
            obj = entity_by_id.get(relation["object_entity_id"], {})
            lines.append(
                f"[{index}] {subject.get('name', relation['subject_entity_id'])} "
                f"--{relation.get('predicate_label') or relation['predicate']}--> "
                f"{obj.get('name', relation['object_entity_id'])}"
            )
            for evidence in relation.get("globi_evidence", [])[:2]:
                citation = evidence.get("study_source_citation") or evidence.get("study_source_id") or "GloBI"
                location = evidence.get("locality") or "未提供具体地域"
                lines.append(
                    f"来源：{citation}；地域：{location}；原始关系：{evidence.get('raw_interaction_type') or relation['predicate']}"
                )
        lines.append("</globi_runtime_reference>")
        return "\n".join(lines)

    @staticmethod
    def empty_payload(*, status: str, warning: str = "") -> dict:
        return {
            "entities": [],
            "relations": [],
            "paths": [],
            "recommended_path_ids": [],
            "globi_runtime": {
                "query_id": "",
                "status": status,
                "cache_hit": False,
                "queried_entities": [],
                "relation_count": 0,
                "warning": warning,
            },
        }

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        if isinstance(exc, httpx.TimeoutException):
            return "GloBI 查询超时，已继续使用本地知识库"
        if isinstance(exc, httpx.HTTPStatusError):
            return f"GloBI 接口返回 {exc.response.status_code}，已继续使用本地知识库"
        return "GloBI 查询暂时不可用，已继续使用本地知识库"
