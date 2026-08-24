"""Profile-scoped persistence API for Hermes Project Groups."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any

try:
    from fastapi import APIRouter, HTTPException  # type: ignore[assignment]
    from pydantic import BaseModel  # type: ignore[assignment]
except ImportError:  # Allows pure state tests without dashboard dependencies.
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class APIRouter:
        def get(self, *_args, **_kwargs):
            return lambda fn: fn

        def post(self, *_args, **_kwargs):
            return lambda fn: fn

        def put(self, *_args, **_kwargs):
            return lambda fn: fn

        def delete(self, *_args, **_kwargs):
            return lambda fn: fn

    class BaseModel:
        def __init__(self, **values):
            for key, value in values.items():
                setattr(self, key, value)

try:
    from hermes_constants import get_hermes_home
except ImportError:  # pragma: no cover - standalone development fallback
    def get_hermes_home() -> Path:
        value = (os.environ.get("HERMES_HOME") or "").strip()
        return Path(value) if value else Path.home() / ".hermes"

router = APIRouter()
_LOCK = threading.RLock()
_SCHEMA_VERSION = 1
_MAX_GROUPS = 200
_MAX_ASSIGNMENTS = 20_000
_MAX_ORDER = 20_000
_MAX_DELETE_OPERATIONS = 256
_MAX_TEXT = 200
_MAX_GROUP_NAME = 100


class StateEnvelope(BaseModel):
    state: dict[str, Any]


class CreateGroupEnvelope(BaseModel):
    name: str


class AssignProjectEnvelope(BaseModel):
    project_id: str
    group_id: str | None = None


class CollapseGroupEnvelope(BaseModel):
    group_id: str
    collapsed: bool


class DeleteGroupEnvelope(BaseModel):
    group_id: str
    expected_project_ids: list[str]
    operation_id: str


def _state_path() -> Path:
    return get_hermes_home() / "project-groups" / "state.json"


def _utf16_units(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


def _clean_text(value: Any, *, field: str, max_units: int = _MAX_TEXT) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    text = " ".join(value.strip().split())
    if not text or _utf16_units(text) > max_units:
        raise ValueError(f"{field} must be 1-{max_units} UTF-16 code units")
    return text


def _truncate_utf16(value: str, max_units: int) -> str:
    result = ""
    units = 0
    for character in value:
        character_units = _utf16_units(character)
        if units + character_units > max_units:
            break
        result += character
        units += character_units
    return result


def _unique_legacy_text(value: str, used: set[str], *, max_units: int, label: bool) -> str:
    base = _truncate_utf16(value, max_units)
    candidate = base
    index = 2
    while candidate.casefold() in used:
        suffix = f" ({index})" if label else f"-{index}"
        candidate = f"{_truncate_utf16(base, max_units - _utf16_units(suffix))}{suffix}"
        index += 1
    used.add(candidate.casefold())
    return candidate


def normalize_state(raw: Any, *, repair_legacy: bool = False) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("state must be an object")
    version = raw.get("version")
    if (
        isinstance(version, (int, float))
        and not isinstance(version, bool)
        and version > _SCHEMA_VERSION
    ):
        raise ValueError(
            f"newer schema version {version} is not supported (maximum {_SCHEMA_VERSION})"
        )

    groups: list[dict[str, Any]] = []
    group_ids: set[str] = set()
    legacy_group_ids: set[str] = set()
    group_names: set[str] = set()
    id_aliases: dict[str, str] = {}
    for index, item in enumerate(raw.get("groups", [])):
        if len(groups) >= _MAX_GROUPS:
            raise ValueError(f"groups exceeds {_MAX_GROUPS}")
        if not isinstance(item, dict):
            continue
        if repair_legacy:
            raw_group_id = " ".join(item.get("id", "").strip().split()) if isinstance(item.get("id"), str) else ""
            raw_name = item.get("name", item.get("label"))
            raw_name = " ".join(raw_name.strip().split()) if isinstance(raw_name, str) else ""
            group_id = _unique_legacy_text(
                raw_group_id or f"group-{index + 1}", legacy_group_ids, max_units=_MAX_TEXT, label=False
            )
            name = _unique_legacy_text(
                raw_name or "Untitled group", group_names, max_units=_MAX_GROUP_NAME, label=True
            )
            if raw_group_id and raw_group_id not in id_aliases:
                id_aliases[raw_group_id] = group_id
            group_ids.add(group_id)
            groups.append({"id": group_id, "name": name, "collapsed": item.get("collapsed") is True})
            continue

        group_id = _clean_text(item.get("id"), field="group id")
        name = _clean_text(item.get("name"), field="group name", max_units=_MAX_GROUP_NAME)
        folded_name = name.casefold()
        if group_id in group_ids or folded_name in group_names:
            continue
        group_ids.add(group_id)
        group_names.add(folded_name)
        groups.append({"id": group_id, "name": name, "collapsed": item.get("collapsed") is True})

    assignments: dict[str, str] = {}
    raw_assignments = raw.get("assignments", {})
    if isinstance(raw_assignments, dict):
        if len(raw_assignments) > _MAX_ASSIGNMENTS:
            raise ValueError(f"assignments exceeds {_MAX_ASSIGNMENTS}")
        for project_id, group_id in raw_assignments.items():
            resolved_group_id = (
                id_aliases.get(" ".join(group_id.strip().split()))
                if repair_legacy and isinstance(group_id, str)
                else group_id
            )
            if isinstance(project_id, str) and isinstance(resolved_group_id, str) and resolved_group_id in group_ids:
                assignments[_clean_text(project_id, field="project id")] = resolved_group_id

    project_order: dict[str, list[str]] = {}
    raw_order = raw.get("projectOrder", {})
    if isinstance(raw_order, dict):
        total = 0
        for raw_group_id, project_ids in raw_order.items():
            clean_group_id = " ".join(raw_group_id.strip().split()) if isinstance(raw_group_id, str) else raw_group_id
            group_id = (
                "__ungrouped__"
                if clean_group_id == "__ungrouped__"
                else id_aliases.get(clean_group_id) if repair_legacy else raw_group_id
            )
            if group_id not in group_ids and group_id != "__ungrouped__":
                continue
            if not isinstance(project_ids, list):
                continue
            unique: list[str] = []
            seen: set[str] = set()
            for project_id in project_ids:
                if not isinstance(project_id, str):
                    continue
                clean = _clean_text(project_id, field="project id")
                if clean not in seen:
                    seen.add(clean)
                    unique.append(clean)
                    total += 1
                    if total > _MAX_ORDER:
                        raise ValueError(f"projectOrder exceeds {_MAX_ORDER}")
            project_order[group_id] = unique

    result = {
        "version": _SCHEMA_VERSION,
        "groups": groups,
        "assignments": assignments,
        "projectOrder": project_order,
    }
    if "deleteOperations" in raw:
        raw_operations = raw["deleteOperations"]
        if not isinstance(raw_operations, list):
            raise ValueError("deleteOperations must be an array")
        if len(raw_operations) > _MAX_DELETE_OPERATIONS:
            raise ValueError(f"deleteOperations exceeds {_MAX_DELETE_OPERATIONS}")
        operations: list[dict[str, str]] = []
        operation_ids: set[str] = set()
        for item in raw_operations:
            if not isinstance(item, dict):
                raise ValueError("delete operation must be an object")
            operation_id = _clean_text(item.get("operationId"), field="operation id")
            request_hash = item.get("requestHash")
            if (
                not isinstance(request_hash, str)
                or len(request_hash) != 64
                or any(character not in "0123456789abcdef" for character in request_hash)
            ):
                raise ValueError("delete operation request hash is invalid")
            if operation_id in operation_ids:
                raise ValueError(f"duplicate delete operation id: {operation_id}")
            operation_ids.add(operation_id)
            operations.append({"operationId": operation_id, "requestHash": request_hash})
        result["deleteOperations"] = operations
    return result


def _atomic_write(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state, indent=2, sort_keys=True) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=".state-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _read_state() -> dict[str, Any] | None:
    with _LOCK:
        path = _state_path()
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            state = normalize_state(raw, repair_legacy=True)
            if state != raw:
                _atomic_write(path, state)
            return state
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(status_code=500, detail=f"Stored Project Groups state is invalid: {exc}") from exc


def _empty_state() -> dict[str, Any]:
    return {"version": _SCHEMA_VERSION, "groups": [], "assignments": {}, "projectOrder": {}}


def _response(state: dict[str, Any]) -> dict[str, Any]:
    return {"state": state, "storage": "backend", "version": _SCHEMA_VERSION}


def _validation_error(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


@router.get("/capabilities")
async def get_capabilities():
    return {
        "mutations": ["createGroup", "assignProject", "setGroupCollapsed", "deleteGroup"],
        "version": _SCHEMA_VERSION,
    }


@router.get("/state")
async def get_state():
    with _LOCK:
        state = _read_state()
    return {"state": state, "storage": "backend", "version": _SCHEMA_VERSION}


@router.post("/state/migrate")
async def migrate_state(envelope: StateEnvelope):
    try:
        migrated = normalize_state(envelope.state, repair_legacy=True)
        migrated.pop("deleteOperations", None)
    except ValueError as exc:
        raise _validation_error(exc) from exc
    with _LOCK:
        current = _read_state()
        if current is None:
            current = migrated
            _atomic_write(_state_path(), current)
    return _response(current)


@router.post("/groups")
async def create_group(envelope: CreateGroupEnvelope):
    try:
        name = _clean_text(envelope.name, field="group name", max_units=_MAX_GROUP_NAME)
    except ValueError as exc:
        raise _validation_error(exc) from exc

    with _LOCK:
        current = _read_state() or _empty_state()
        if any(group["name"].casefold() == name.casefold() for group in current["groups"]):
            raise HTTPException(status_code=409, detail=f"Project group already exists: {name}")
        if len(current["groups"]) >= _MAX_GROUPS:
            raise HTTPException(status_code=422, detail=f"groups exceeds {_MAX_GROUPS}")
        group_id = f"group-{uuid.uuid4().hex}"
        current = {
            **current,
            "groups": [*current["groups"], {"id": group_id, "name": name, "collapsed": False}],
        }
        _atomic_write(_state_path(), current)
    return _response(current)


@router.put("/assign")
async def assign_project(envelope: AssignProjectEnvelope):
    try:
        project_id = _clean_text(envelope.project_id, field="project id")
        group_id = None if envelope.group_id is None else _clean_text(envelope.group_id, field="group id")
    except ValueError as exc:
        raise _validation_error(exc) from exc

    with _LOCK:
        current = _read_state() or _empty_state()
        if group_id is not None and not any(group["id"] == group_id for group in current["groups"]):
            raise HTTPException(status_code=404, detail=f"Unknown Project group: {group_id}")
        assignments = dict(current["assignments"])
        if group_id is None:
            assignments.pop(project_id, None)
        else:
            if project_id not in assignments and len(assignments) >= _MAX_ASSIGNMENTS:
                raise HTTPException(status_code=422, detail=f"assignments exceeds {_MAX_ASSIGNMENTS}")
            assignments[project_id] = group_id
        current = {**current, "assignments": assignments}
        _atomic_write(_state_path(), current)
    return _response(current)


@router.put("/groups/collapsed")
async def set_group_collapsed(envelope: CollapseGroupEnvelope):
    try:
        group_id = _clean_text(envelope.group_id, field="group id")
    except ValueError as exc:
        raise _validation_error(exc) from exc

    with _LOCK:
        current = _read_state() or _empty_state()
        if not any(group["id"] == group_id for group in current["groups"]):
            raise HTTPException(status_code=404, detail=f"Unknown Project group: {group_id}")
        current = {
            **current,
            "groups": [
                {**group, "collapsed": envelope.collapsed} if group["id"] == group_id else group
                for group in current["groups"]
            ],
        }
        _atomic_write(_state_path(), current)
    return _response(current)


def _delete_request(envelope: DeleteGroupEnvelope) -> tuple[str, list[str], str, str]:
    try:
        group_id = _clean_text(envelope.group_id, field="group id")
        operation_id = _clean_text(envelope.operation_id, field="operation id")
        raw_project_ids = envelope.expected_project_ids
        if not isinstance(raw_project_ids, list):
            raise ValueError("expected project ids must be an array")
        if len(raw_project_ids) > _MAX_ASSIGNMENTS:
            raise ValueError(f"expected project ids exceeds {_MAX_ASSIGNMENTS}")
        expected_project_ids = [
            _clean_text(project_id, field="project id") for project_id in raw_project_ids
        ]
        if len(set(expected_project_ids)) != len(expected_project_ids):
            raise ValueError("expected project ids must be unique")
    except ValueError as exc:
        raise _validation_error(exc) from exc
    fingerprint = json.dumps(
        {"groupId": group_id, "expectedProjectIds": sorted(expected_project_ids)},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    request_hash = hashlib.sha256(fingerprint).hexdigest()
    return group_id, expected_project_ids, operation_id, request_hash


@router.delete("/groups")
async def delete_group(envelope: DeleteGroupEnvelope):
    group_id, expected_project_ids, operation_id, request_hash = _delete_request(envelope)

    with _LOCK:
        current = _read_state() or _empty_state()
        operations = current.get("deleteOperations", [])
        prior = next(
            (item for item in operations if item["operationId"] == operation_id),
            None,
        )
        if prior is not None:
            if prior["requestHash"] != request_hash:
                raise HTTPException(
                    status_code=409,
                    detail=f"Delete operation id was already used for another request: {operation_id}",
                )
            return _response(current)

        if not any(group["id"] == group_id for group in current["groups"]):
            raise HTTPException(status_code=404, detail=f"Unknown Project group: {group_id}")
        actual_project_ids = {
            project_id
            for project_id, assigned_group_id in current["assignments"].items()
            if assigned_group_id == group_id
        }
        if actual_project_ids != set(expected_project_ids):
            raise HTTPException(
                status_code=409,
                detail=f"Project group member set changed: {group_id}",
            )

        project_order = dict(current["projectOrder"])
        project_order.pop(group_id, None)
        current = {
            **current,
            "groups": [group for group in current["groups"] if group["id"] != group_id],
            "assignments": {
                project_id: assigned_group_id
                for project_id, assigned_group_id in current["assignments"].items()
                if assigned_group_id != group_id
            },
            "projectOrder": project_order,
            "deleteOperations": [
                *operations,
                {"operationId": operation_id, "requestHash": request_hash},
            ][-_MAX_DELETE_OPERATIONS:],
        }
        _atomic_write(_state_path(), current)
    return _response(current)
