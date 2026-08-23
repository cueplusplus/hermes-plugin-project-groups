"""Agent-facing Project Groups tools and guidance."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _hermes_home() -> Path:
    try:
        from hermes_constants import get_hermes_home
        return get_hermes_home()
    except ImportError:  # pragma: no cover
        value = (os.environ.get("HERMES_HOME") or "").strip()
        return Path(value) if value else Path.home() / ".hermes"


def _load_state() -> dict[str, Any]:
    path = _hermes_home() / "project-groups" / "state.json"
    if not path.is_file():
        return {"version": 1, "groups": [], "assignments": {}, "projectOrder": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Project Groups state is unreadable: {exc}") from exc
    if not isinstance(raw, dict):
        raise RuntimeError("Project Groups state is not an object")
    return raw


def _projects() -> list[dict[str, Any]]:
    try:
        from hermes_cli import projects_db as pdb
        with pdb.connect_closing() as conn:
            return [project.to_dict() for project in pdb.list_projects(conn) if not project.archived]
    except Exception as exc:
        raise RuntimeError(f"Hermes Projects are unavailable: {exc}") from exc


def list_groups() -> dict[str, Any]:
    state = _load_state()
    projects = {project["id"]: project for project in _projects()}
    raw_assignments = state.get("assignments")
    assignments: dict[str, Any] = raw_assignments if isinstance(raw_assignments, dict) else {}
    groups = []
    for group in state.get("groups", []):
        if not isinstance(group, dict) or not isinstance(group.get("id"), str):
            continue
        group_id = group["id"]
        members = [projects[project_id] for project_id, assigned in assignments.items() if assigned == group_id and project_id in projects]
        groups.append({
            "id": group_id,
            "name": group.get("name", group_id),
            "collapsed": group.get("collapsed") is True,
            "project_count": len(members),
            "projects": [{"id": item["id"], "name": item["name"], "primary_path": item.get("primary_path")} for item in members],
        })
    grouped_ids = {project_id for project_id, group_id in assignments.items() if group_id and project_id in projects}
    return {
        "success": True,
        "groups": groups,
        "ungrouped": [
            {"id": item["id"], "name": item["name"], "primary_path": item.get("primary_path")}
            for project_id, item in projects.items()
            if project_id not in grouped_ids
        ],
        "scope": "current Hermes profile/backend",
    }


def get_group(group: str) -> dict[str, Any]:
    target = group.strip().lower()
    data = list_groups()
    matches = [item for item in data["groups"] if item["id"].lower() == target or str(item["name"]).lower() == target]
    if not matches:
        return {"success": False, "error": f"Project group not found: {group}"}
    if len(matches) > 1:
        return {"success": False, "error": f"Project group is ambiguous: {group}"}
    return {"success": True, "group": matches[0], "scope": data["scope"]}


def register(ctx):
    root = Path(__file__).resolve().parent
    ctx.register_skill(
        "project-groups",
        root / "skills" / "project-groups" / "SKILL.md",
        "Use when choosing or explaining Hermes Project groups.",
    )
    ctx.register_system_prompt_section(
        "project-groups.model",
        "Project Groups organize Hermes Projects. Groups are not working directories: Projects remain the authority for folders, sessions, worktrees and boards. Use project_groups_list/project_group_get before asserting membership; local and remote profiles have independent Project IDs.",
        max_chars=600,
    )
    ctx.register_tool(
        name="project_groups_list",
        toolset="project_groups",
        schema={
            "name": "project_groups_list",
            "description": "List Project Groups, member Hermes Projects, paths, and ungrouped Projects for the current profile/backend.",
            "parameters": {"type": "object", "properties": {}},
        },
        handler=lambda _args, **_kwargs: json.dumps(list_groups()),
    )
    ctx.register_tool(
        name="project_group_get",
        toolset="project_groups",
        schema={
            "name": "project_group_get",
            "description": "Get one Project Group by id or name, including its member Hermes Projects and primary paths.",
            "parameters": {
                "type": "object",
                "properties": {"group": {"type": "string", "description": "Group id or display name."}},
                "required": ["group"],
            },
        },
        handler=lambda args, **_kwargs: json.dumps(get_group(str(args.get("group") or ""))),
    )
