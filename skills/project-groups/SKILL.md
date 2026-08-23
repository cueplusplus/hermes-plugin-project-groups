---
name: project-groups
description: "Use when choosing or explaining Hermes Project groups."
version: 0.2.0
---

# Hermes Project Groups

Project Groups are an organizational layer over Hermes Projects. A **Project** remains the executable workspace and owns its folders, sessions, worktrees, board binding, and active context. A **group** is only a parent/category that collects Project IDs for navigation and explanation.

## Agent rules

1. Use `project_groups_list` to retrieve current groups and memberships before making claims about them.
2. Use `project_group_get` when the user names one group and you need its Projects and paths.
3. Do not infer group membership solely from a path or display-name prefix when stored membership exists.
4. Do not confuse additional folders/worktrees inside one Project with child Projects.
5. Local and remote Hermes profiles have independent Project IDs and assignments. A shared group label such as `CUE++` does not make local and remote Project records identical.
6. To work in a Project, use its actual primary path or the ordinary Hermes Project controls. The group itself is not a working directory.
7. If backend state is unavailable, say the grouping data could not be retrieved; do not reconstruct it from memory as if authoritative.

## Model

```text
Project Group (presentation/organization)
└── Hermes Project (workspace/session authority)
    ├── primary folder
    ├── optional worktree or publication folders
    ├── sessions
    └── optional board
```

The Desktop plugin currently provides a dedicated grouped page. Newer Hermes builds may also render the same data through the native Projects presentation contribution area.
