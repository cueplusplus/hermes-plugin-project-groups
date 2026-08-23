"""Profile-scoped persistence API for Hermes Project Groups."""
from __future__ import annotations

import json
import os
import tempfile
import threading
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

        def put(self, *_args, **_kwargs):
            return lambda fn: fn

    class BaseModel:
        pass

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


class StateEnvelope(BaseModel):
    state: dict[str, Any]


def _state_path() -> Path:
    return get_hermes_home() / "project-groups" / "state.json"


def _clean_text(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    text = " ".join(value.strip().split())
    if not text or len(text) > _MAX_TEXT:
        raise ValueError(f"{field} must be 1-{_MAX_TEXT} characters")
    return text


def normalize_state(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("state must be an object")

    groups: list[dict[str, Any]] = []
    group_ids: set[str] = set()
    for item in raw.get("groups", []):
        if len(groups) >= _MAX_GROUPS:
            raise ValueError(f"groups exceeds {_MAX_GROUPS}")
        if not isinstance(item, dict):
            continue
        group_id = _clean_text(item.get("id"), field="group id")
        name = _clean_text(item.get("name"), field="group name")
        if group_id in group_ids:
            continue
        group_ids.add(group_id)
        groups.append({"id": group_id, "name": name, "collapsed": item.get("collapsed") is True})

    assignments: dict[str, str] = {}
    raw_assignments = raw.get("assignments", {})
    if isinstance(raw_assignments, dict):
        if len(raw_assignments) > _MAX_ASSIGNMENTS:
            raise ValueError(f"assignments exceeds {_MAX_ASSIGNMENTS}")
        for project_id, group_id in raw_assignments.items():
            if isinstance(project_id, str) and isinstance(group_id, str) and group_id in group_ids:
                assignments[_clean_text(project_id, field="project id")] = group_id

    project_order: dict[str, list[str]] = {}
    raw_order = raw.get("projectOrder", {})
    if isinstance(raw_order, dict):
        total = 0
        for group_id, project_ids in raw_order.items():
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
        return normalize_state(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=f"Stored Project Groups state is invalid: {exc}") from exc


@router.get("/state")
async def get_state():
    with _LOCK:
        return {"state": _read_state(), "storage": "backend", "version": _SCHEMA_VERSION}


@router.put("/state")
async def put_state(envelope: StateEnvelope):
    try:
        state = normalize_state(envelope.state)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    with _LOCK:
        _atomic_write(_state_path(), state)
    return {"state": state, "storage": "backend", "version": _SCHEMA_VERSION}
