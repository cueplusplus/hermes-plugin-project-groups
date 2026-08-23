import {
  Button,
  Codicon,
  EmptyState,
  Input,
  ROUTES_AREA,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  SIDEBAR_NAV_AREA,
  host
} from '@hermes/plugin-sdk'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const ID = 'project-groups'
const STORAGE_KEY = 'state.v1'
const DEFAULT_GROUPS = [
  { id: 'cue', name: 'CUE++', collapsed: false },
  { id: 'rgc-labs', name: 'RGC-LABS', collapsed: false },
  { id: 'rgc-legacy', name: 'RGC Legacy', collapsed: false }
]
const RULES = [
  { id: 'cue', path: /(?:^|[\\/])work[\\/]cue\+\+(?:[\\/]|$)/i, name: /^CUE\+\+\s*[·:]/i },
  { id: 'rgc-labs', path: /(?:^|[\\/])work[\\/]rgc-labs(?:[\\/]|$)/i, name: /^RGC-LABS\s*[·:]/i },
  { id: 'rgc-legacy', path: /(?:^|[\\/])work[\\/]rgc(?:[\\/]|$)/i, name: /^RGC Legacy\s*[·:]/i }
]

const cleanId = value =>
  String(value ?? '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, '-')
    .replace(/^-+|-+$/g, '')
const cleanName = value => String(value ?? '').trim().replace(/\s+/g, ' ')

function normalizeState(input = {}) {
  const groups = []
  const ids = new Set()
  for (const raw of Array.isArray(input.groups) ? input.groups : []) {
    const id = cleanId(raw?.id)
    const name = cleanName(raw?.name)
    if (!id || !name || ids.has(id)) continue
    ids.add(id)
    groups.push({ id, name, collapsed: raw?.collapsed === true })
  }
  const assignments = {}
  for (const [projectId, groupId] of Object.entries(input.assignments ?? {})) {
    if (typeof groupId === 'string' && ids.has(groupId)) assignments[projectId] = groupId
  }
  const projectOrder = {}
  for (const [groupId, projectIds] of Object.entries(input.projectOrder ?? {})) {
    if (groupId !== '__ungrouped__' && !ids.has(groupId)) continue
    if (Array.isArray(projectIds)) {
      projectOrder[groupId] = [...new Set(projectIds.filter(projectId => typeof projectId === 'string'))]
    }
  }
  return { version: 1, groups, assignments, projectOrder }
}

function suggestedGroup(project) {
  const paths = [project?.primary_path, ...(project?.folders ?? []).map(folder => folder?.path)].filter(Boolean)
  const name = String(project?.name ?? '')
  return RULES.find(rule => paths.some(path => rule.path.test(path)) || rule.name.test(name))?.id
}

function seedState(projects, stored) {
  const base = normalizeState(
    stored && Array.isArray(stored.groups) ? stored : { groups: DEFAULT_GROUPS, assignments: {}, projectOrder: {} }
  )
  const assignments = { ...base.assignments }
  const ids = new Set(base.groups.map(group => group.id))
  for (const project of projects) {
    if (assignments[project.id]) continue
    const groupId = suggestedGroup(project)
    if (groupId && ids.has(groupId)) assignments[project.id] = groupId
  }
  return { ...base, assignments }
}

function ProjectRow({ groups, groupId, index, onAssign, onMove, onOpen, project, selectedGroup, total }) {
  return jsxs('div', {
    className: 'flex items-center gap-3 border-t border-(--ui-stroke-secondary) px-3 py-2 first:border-t-0',
    children: [
      jsx(Codicon, { className: 'shrink-0 text-(--ui-text-tertiary)', name: 'repo' }),
      jsxs('div', {
        className: 'min-w-0 flex-1',
        children: [
          jsx('div', { className: 'truncate text-sm font-medium', children: project.name }),
          jsx('div', {
            className: 'truncate text-xs text-(--ui-text-tertiary)',
            children: project.primary_path || project.folders?.[0]?.path || 'No folder'
          })
        ]
      }),
      jsx(Select, {
        onValueChange: value => onAssign(project.id, value),
        value: selectedGroup || '__ungrouped__',
        children: [
          jsx(SelectTrigger, {
            'aria-label': `Group for ${project.name}`,
            className: 'w-40',
            children: jsx(SelectValue, {})
          }),
          jsx(SelectContent, {
            children: [
              jsx(SelectItem, { value: '__ungrouped__', children: 'Ungrouped' }),
              ...groups.map(group => jsx(SelectItem, { value: group.id, children: group.name }, group.id))
            ]
          })
        ]
      }),
      jsx(Button, {
        'aria-label': `Move ${project.name} up`,
        disabled: index === 0,
        onClick: () => onMove(groupId, project.id, -1),
        size: 'icon-sm',
        variant: 'ghost',
        children: jsx(Codicon, { name: 'arrow-up' })
      }),
      jsx(Button, {
        'aria-label': `Move ${project.name} down`,
        disabled: index === total - 1,
        onClick: () => onMove(groupId, project.id, 1),
        size: 'icon-sm',
        variant: 'ghost',
        children: jsx(Codicon, { name: 'arrow-down' })
      }),
      jsx(Button, { onClick: () => onOpen(project), size: 'sm', variant: 'secondary', children: 'Activate' })
    ]
  })
}

function GroupCard({ group, groups, immutable = false, onAssign, onDelete, onMove, onOpen, onRename, onToggle, projects, selected }) {
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(group.name)

  const validRename = cleanName(name)

  return jsxs('section', {
    className: 'overflow-hidden rounded-md border border-(--ui-stroke-secondary)',
    children: [
      jsxs('header', {
        className: 'flex items-center gap-2 bg-(--ui-surface-secondary) px-3 py-2',
        children: [
          jsx(Button, {
            'aria-label': group.collapsed ? `Expand ${group.name}` : `Collapse ${group.name}`,
            onClick: () => onToggle(group.id),
            size: 'icon-sm',
            variant: 'ghost',
            children: jsx(Codicon, { name: group.collapsed ? 'chevron-right' : 'chevron-down' })
          }),
          editing
            ? jsx(Input, {
                autoFocus: true,
                className: 'h-7 max-w-xs',
                onChange: event => setName(event.target.value),
                onKeyDown: event => {
                  if (event.key === 'Enter' && validRename) {
                    onRename(group.id, validRename)
                    setEditing(false)
                  }
                  if (event.key === 'Escape') setEditing(false)
                },
                value: name
              })
            : jsx('h2', { className: 'flex-1 text-sm font-semibold', children: `${group.name} (${projects.length})` }),
          !immutable &&
            jsx(Button, {
              onClick: () => setEditing(value => !value),
              size: 'icon-sm',
              variant: 'ghost',
              children: jsx(Codicon, { name: editing ? 'close' : 'edit' })
            }),
          !immutable &&
            jsx(Button, {
              'aria-label': `Delete ${group.name}`,
              onClick: () => onDelete(group.id),
              size: 'icon-sm',
              variant: 'ghost',
              children: jsx(Codicon, { name: 'trash' })
            })
        ]
      }),
      !group.collapsed &&
        (projects.length
          ? jsx('div', {
              children: projects.map((project, index) =>
                jsx(
                  ProjectRow,
                  {
                    groups,
                    groupId: group.id,
                    index,
                    onAssign,
                    onMove,
                    onOpen,
                    project,
                    selectedGroup: selected[project.id],
                    total: projects.length
                  },
                  project.id
                )
              )
            })
          : jsx('div', {
              className: 'px-4 py-5 text-sm text-(--ui-text-tertiary)',
              children: 'No Projects in this group.'
            }))
    ]
  })
}

function ProjectGroupsPage({ ctx, publishPresentation }) {
  const [projects, setProjects] = useState([])
  const [state, setState] = useState(() => normalizeState(ctx.storage.get(STORAGE_KEY, { groups: DEFAULT_GROUPS })))
  const [storageMode, setStorageMode] = useState('local fallback')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [newGroup, setNewGroup] = useState('')

  const persist = useCallback(
    updater =>
      setState(current => {
        const next = normalizeState(typeof updater === 'function' ? updater(current) : updater)
        ctx.storage.set(STORAGE_KEY, next)
        publishPresentation(next)
        void ctx
          .rest('/state', { method: 'PUT', body: { state: next }, timeoutMs: 5_000 })
          .then(() => setStorageMode('backend synced'))
          .catch(() => setStorageMode('local fallback'))
        return next
      }),
    [ctx, publishPresentation]
  )

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [payload, backend] = await Promise.all([
        host.request('projects.list', {}),
        ctx.rest('/state', { timeoutMs: 5_000 }).catch(() => null)
      ])
      const rows = Array.isArray(payload?.projects) ? payload.projects.filter(project => !project.archived) : []
      setProjects(rows)
      if (backend?.state) {
        const seeded = seedState(rows, backend.state)
        ctx.storage.set(STORAGE_KEY, seeded)
        setState(seeded)
        setStorageMode('backend synced')
      } else {
        const seeded = seedState(rows, normalizeState(ctx.storage.get(STORAGE_KEY, { groups: DEFAULT_GROUPS })))
        ctx.storage.set(STORAGE_KEY, seeded)
        setState(seeded)
        publishPresentation(seeded)
        setStorageMode('local fallback')
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setLoading(false)
    }
  }, [ctx, publishPresentation])

  useEffect(() => {
    void load()
  }, [load])

  const grouped = useMemo(() => {
    const byGroup = Object.fromEntries(state.groups.map(group => [group.id, []]))
    const ungrouped = []
    for (const project of projects) {
      const groupId = state.assignments[project.id]
      if (groupId && byGroup[groupId]) byGroup[groupId].push(project)
      else ungrouped.push(project)
    }
    const ordered = (rows, groupId) => {
      const rank = new Map((state.projectOrder[groupId] ?? []).map((id, index) => [id, index]))
      rows.sort((a, b) => {
        const aRank = rank.get(a.id) ?? Number.MAX_SAFE_INTEGER
        const bRank = rank.get(b.id) ?? Number.MAX_SAFE_INTEGER
        return aRank - bRank || String(a.name).localeCompare(String(b.name))
      })
    }
    for (const [groupId, rows] of Object.entries(byGroup)) ordered(rows, groupId)
    ordered(ungrouped, '__ungrouped__')
    return { byGroup, ungrouped }
  }, [projects, state])

  const assign = (projectId, groupId) =>
    persist(current => {
      const assignments = { ...current.assignments }
      if (groupId === '__ungrouped__') delete assignments[projectId]
      else assignments[projectId] = groupId
      return { ...current, assignments }
    })

  const moveProject = (groupId, projectId, delta) =>
    persist(current => {
      const visible = groupId === '__ungrouped__' ? grouped.ungrouped : grouped.byGroup[groupId] ?? []
      const order = visible.map(project => project.id)
      const index = order.indexOf(projectId)
      const target = Math.max(0, Math.min(order.length - 1, index + delta))
      if (index < 0 || target === index) return current
      const [moved] = order.splice(index, 1)
      order.splice(target, 0, moved)
      return { ...current, projectOrder: { ...current.projectOrder, [groupId]: order } }
    })

  const activate = async project => {
    try {
      await host.request('projects.set_active', { id: project.id })
      host.notify({ kind: 'success', message: `Active Project: ${project.name}` })
    } catch (cause) {
      host.notify({ kind: 'error', message: cause instanceof Error ? cause.message : String(cause) })
    }
  }

  const addGroup = () => {
    const name = cleanName(newGroup)
    const id = cleanId(name)
    if (!name || !id) return
    if (state.groups.some(group => group.id === id)) {
      host.notify({ kind: 'warning', message: `Group already exists: ${name}` })
      return
    }
    persist(current => ({ ...current, groups: [...current.groups, { id, name, collapsed: false }] }))
    setNewGroup('')
  }

  if (loading) return jsx('div', { className: 'p-6 text-sm text-(--ui-text-tertiary)', children: 'Loading Projects…' })
  if (error)
    return jsxs('div', {
      className: 'flex flex-col items-start gap-3 p-6',
      children: [jsx('div', { className: 'text-sm text-(--ui-danger)', children: error }), jsx(Button, { onClick: load, children: 'Retry' })]
    })

  return jsxs('div', {
    className: 'flex h-full flex-col overflow-hidden',
    children: [
      jsxs('header', {
        className: 'flex flex-wrap items-center gap-3 border-b border-(--ui-stroke-secondary) px-5 py-4',
        children: [
          jsxs('div', {
            className: 'mr-auto',
            children: [
              jsx('h1', { className: 'text-lg font-semibold', children: 'Project Groups' }),
              jsx('p', {
                className: 'text-xs text-(--ui-text-tertiary)',
                children: `${projects.length} Projects · ${storageMode}`
              })
            ]
          }),
          jsx(Input, {
            className: 'w-52',
            onChange: event => setNewGroup(event.target.value),
            onKeyDown: event => event.key === 'Enter' && addGroup(),
            placeholder: 'New group name',
            value: newGroup
          }),
          jsx(Button, { disabled: !cleanName(newGroup), onClick: addGroup, children: 'Add group' }),
          jsx(Button, { onClick: load, variant: 'secondary', children: 'Refresh' })
        ]
      }),
      jsx('main', {
        className: 'flex-1 overflow-auto p-5',
        children: projects.length
          ? jsxs('div', {
              className: 'flex flex-col gap-4',
              children: [
                ...state.groups.map(group =>
                  jsx(
                    GroupCard,
                    {
                      group,
                      groups: state.groups,
                      onAssign: assign,
                      onDelete: groupId =>
                        persist(current => ({
                          ...current,
                          groups: current.groups.filter(item => item.id !== groupId),
                          assignments: Object.fromEntries(
                            Object.entries(current.assignments).filter(([, value]) => value !== groupId)
                          )
                        })),
                      onMove: moveProject,
                      onOpen: activate,
                      onRename: (groupId, name) =>
                        persist(current => ({
                          ...current,
                          groups: current.groups.map(item => (item.id === groupId ? { ...item, name: cleanName(name) } : item))
                        })),
                      onToggle: groupId =>
                        persist(current => ({
                          ...current,
                          groups: current.groups.map(item =>
                            item.id === groupId ? { ...item, collapsed: !item.collapsed } : item
                          )
                        })),
                      projects: grouped.byGroup[group.id],
                      selected: state.assignments
                    },
                    group.id
                  )
                ),
                grouped.ungrouped.length > 0 &&
                  jsx(GroupCard, {
                    group: { id: '__ungrouped__', name: 'Ungrouped', collapsed: false },
                    immutable: true,
                    groups: state.groups,
                    onAssign: assign,
                    onDelete: () => {},
                    onMove: moveProject,
                    onOpen: activate,
                    onRename: () => {},
                    onToggle: () => {},
                    projects: grouped.ungrouped,
                    selected: state.assignments
                  })
              ]
            })
          : jsx(EmptyState, { title: 'No Projects', description: 'Create a Hermes Project, then refresh this page.' })
      })
    ]
  })
}

export default {
  id: ID,
  name: 'Project Groups',
  description: 'Organize Hermes Projects into collapsible groups without changing repositories.',
  register(ctx) {
    const presentationArea = 'projects.presentation'
    const toPresentation = state => ({
      groups: state.groups.map(group => ({
        collapsed: group.collapsed,
        id: group.id,
        label: group.name,
        projectIds:
          state.projectOrder[group.id] ??
          Object.entries(state.assignments)
            .filter(([, groupId]) => groupId === group.id)
            .map(([projectId]) => projectId)
      }))
    })
    let disposePresentation = () => {}
    const publishPresentation = state => {
      disposePresentation()
      disposePresentation = ctx.register({
        id: 'native-presentation',
        area: presentationArea,
        data: toPresentation(state)
      })
    }
    publishPresentation(normalizeState(ctx.storage.get(STORAGE_KEY, { groups: DEFAULT_GROUPS })))

    ctx.registerMany([
      {
        id: 'page',
        area: ROUTES_AREA,
        data: { path: '/project-groups' },
        render: () => jsx(ProjectGroupsPage, { ctx, publishPresentation })
      },
      {
        id: 'nav',
        area: SIDEBAR_NAV_AREA,
        data: { path: '/project-groups', label: 'Project Groups', codicon: 'folder-library' }
      }
    ])
  }
}
