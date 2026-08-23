"""Profile-scoped persistence API for Hermes Project Groups."""
from __future__ import annotations

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
            group_id = (
                id_aliases.get(" ".join(raw_group_id.strip().split()))
                if repair_legacy and isinstance(raw_group_id, str)
                else raw_group_id
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

    return {
        "version": _SCHEMA_VERSION,
        "groups": groups,
        "assignments": assignments,
        "projectOrder": project_order,
    }


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
    path = _state_path()
    if not path.exists():
        return None
    try:
        return normalize_state(json.loads(path.read_text(encoding="utf-8")), repair_legacy=True)
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
        "mutations": ["createGroup", "assignProject", "setGroupCollapsed"],
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
