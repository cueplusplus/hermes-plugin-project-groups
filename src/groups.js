export const SCHEMA_VERSION = 1

export const DEFAULT_GROUPS = Object.freeze([
  Object.freeze({ id: 'cue', name: 'CUE++', collapsed: false }),
  Object.freeze({ id: 'rgc-labs', name: 'RGC-LABS', collapsed: false }),
  Object.freeze({ id: 'rgc-legacy', name: 'RGC Legacy', collapsed: false })
])

const RULES = [
  { id: 'cue', path: /(?:^|[\\/])work[\\/]cue\+\+(?:[\\/]|$)/i, name: /^CUE\+\+\s*[·:]/i },
  { id: 'rgc-labs', path: /(?:^|[\\/])work[\\/]rgc-labs(?:[\\/]|$)/i, name: /^RGC-LABS\s*[·:]/i },
  { id: 'rgc-legacy', path: /(?:^|[\\/])work[\\/]rgc(?:[\\/]|$)/i, name: /^RGC Legacy\s*[·:]/i }
]

const cleanId = value => String(value ?? '').trim().toLowerCase().replace(/[^a-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '')
const cleanName = value => String(value ?? '').trim().replace(/\s+/g, ' ')

export function normalizeState(input = {}) {
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
  const rawAssignments = input.assignments && typeof input.assignments === 'object' ? input.assignments : {}

  for (const [projectId, groupId] of Object.entries(rawAssignments)) {
    if (typeof groupId === 'string' && ids.has(groupId)) assignments[projectId] = groupId
  }

  return { version: SCHEMA_VERSION, groups, assignments }
}

export function createGroup(state, group) {
  const current = normalizeState(state)
  const id = cleanId(group?.id || group?.name)
  const name = cleanName(group?.name)

  if (!id || !name) throw new Error('Group name is required')
  if (current.groups.some(item => item.id === id)) throw new Error(`Group already exists: ${id}`)

  return { ...current, groups: [...current.groups, { id, name, collapsed: false }] }
}

export function renameGroup(state, groupId, name) {
  const current = normalizeState(state)
  const nextName = cleanName(name)
  if (!nextName) throw new Error('Group name is required')

  return {
    ...current,
    groups: current.groups.map(group => (group.id === groupId ? { ...group, name: nextName } : group))
  }
}

export function toggleGroup(state, groupId) {
  const current = normalizeState(state)
  return {
    ...current,
    groups: current.groups.map(group => (group.id === groupId ? { ...group, collapsed: !group.collapsed } : group))
  }
}

export function moveGroup(state, groupId, delta) {
  const current = normalizeState(state)
  const index = current.groups.findIndex(group => group.id === groupId)
  if (index < 0) return current
  const target = Math.max(0, Math.min(current.groups.length - 1, index + delta))
  if (target === index) return current

  const groups = [...current.groups]
  const [group] = groups.splice(index, 1)
  groups.splice(target, 0, group)
  return { ...current, groups }
}

export function deleteGroup(state, groupId) {
  const current = normalizeState(state)
  return {
    ...current,
    groups: current.groups.filter(group => group.id !== groupId),
    assignments: Object.fromEntries(Object.entries(current.assignments).filter(([, id]) => id !== groupId))
  }
}

export function assignProject(state, projectId, groupId) {
  const current = normalizeState(state)
  if (!current.groups.some(group => group.id === groupId)) throw new Error(`Unknown group: ${groupId}`)
  return { ...current, assignments: { ...current.assignments, [projectId]: groupId } }
}

export function unassignProject(state, projectId) {
  const current = normalizeState(state)
  const assignments = { ...current.assignments }
  delete assignments[projectId]
  return { ...current, assignments }
}

export function suggestedGroup(project) {
  const paths = [project?.primary_path, ...(project?.folders ?? []).map(folder => folder?.path)].filter(Boolean)
  const name = String(project?.name ?? '')
  return RULES.find(rule => paths.some(path => rule.path.test(path)) || rule.name.test(name))?.id
}

export function autoGroupProjects(projects, state) {
  const current = normalizeState(state)
  const assignments = { ...current.assignments }
  const groupIds = new Set(current.groups.map(group => group.id))

  for (const project of projects ?? []) {
    if (!project?.id || assignments[project.id]) continue
    const groupId = suggestedGroup(project)
    if (groupId && groupIds.has(groupId)) assignments[project.id] = groupId
  }

  return { ...current, assignments }
}

export function projectsByGroup(projects, state) {
  const current = normalizeState(state)
  const byGroup = Object.fromEntries(current.groups.map(group => [group.id, []]))
  const ungrouped = []

  for (const project of projects ?? []) {
    const groupId = current.assignments[project.id]
    if (groupId && byGroup[groupId]) byGroup[groupId].push(project)
    else ungrouped.push(project)
  }

  const sort = rows => rows.sort((a, b) => String(a.name).localeCompare(String(b.name)))
  Object.values(byGroup).forEach(sort)
  sort(ungrouped)
  return { byGroup, ungrouped }
}
