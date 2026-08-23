const ID = 'project-groups'
const GROUPING_AREA = 'projects.grouping'
const STORAGE_KEY = 'state.v1'
const DEFAULT_GROUPS = [
  { id: 'cue', name: 'CUE++', collapsed: false },
  { id: 'rgc-labs', name: 'RGC-LABS', collapsed: false },
  { id: 'rgc-legacy', name: 'RGC Legacy', collapsed: false }
]

const cleanText = value => (typeof value === 'string' ? value.trim().replace(/\s+/gu, ' ') : '')
const utf16Length = value => value.length

function normalizeState(input = {}) {
  const source = input && typeof input === 'object' && input.state && !input.groups ? input.state : input
  const groups = []
  const groupIds = new Set()
  const groupNames = new Set()

  for (const raw of Array.isArray(source?.groups) ? source.groups : []) {
    const id = cleanText(raw?.id)
    const name = cleanText(raw?.name ?? raw?.label)
    const foldedName = name.toLocaleLowerCase()
    if (!id || !name || utf16Length(name) > 100 || groupIds.has(id) || groupNames.has(foldedName)) continue
    groupIds.add(id)
    groupNames.add(foldedName)
    groups.push({ id, name, collapsed: raw?.collapsed === true })
  }

  const assignments = {}
  const rawAssignments = source?.assignments && typeof source.assignments === 'object' ? source.assignments : {}
  for (const [rawProjectId, rawGroupId] of Object.entries(rawAssignments)) {
    const projectId = cleanText(rawProjectId)
    const groupId = cleanText(rawGroupId)
    if (projectId && groupIds.has(groupId)) assignments[projectId] = groupId
  }

  const projectOrder = {}
  const rawOrder = source?.projectOrder && typeof source.projectOrder === 'object' ? source.projectOrder : {}
  for (const [groupId, rawProjectIds] of Object.entries(rawOrder)) {
    if (!groupIds.has(groupId) || !Array.isArray(rawProjectIds)) continue
    const seen = new Set()
    projectOrder[groupId] = rawProjectIds.flatMap(rawProjectId => {
      const projectId = cleanText(rawProjectId)
      if (!projectId || seen.has(projectId)) return []
      seen.add(projectId)
      return [projectId]
    })
  }

  return { version: 1, groups, assignments, projectOrder }
}

function toSnapshot(state) {
  const groups = state.groups.map(group => {
    const assigned = Object.entries(state.assignments)
      .filter(([, groupId]) => groupId === group.id)
      .map(([projectId]) => projectId)
    const assignedSet = new Set(assigned)
    const ordered = (state.projectOrder[group.id] ?? []).filter(projectId => assignedSet.has(projectId))
    const orderedSet = new Set(ordered)
    return Object.freeze({
      collapsed: group.collapsed,
      id: group.id,
      label: group.name,
      projectIds: Object.freeze([...ordered, ...assigned.filter(projectId => !orderedSet.has(projectId))])
    })
  })
  return Object.freeze({ groups: Object.freeze(groups) })
}

function responseState(response) {
  if (!response?.state || typeof response.state !== 'object' || !Array.isArray(response.state.groups)) {
    throw new Error('Project Groups backend returned invalid state')
  }
  return normalizeState(response.state)
}

function createProvider(ctx) {
  const cached = normalizeState(ctx.storage.get(STORAGE_KEY, { groups: DEFAULT_GROUPS }))
  const listeners = new Set()
  let snapshot = toSnapshot(cached)
  let mutationQueue = Promise.resolve()

  const provider = {
    getSnapshot: () => snapshot,
    subscribe: listener => {
      listeners.add(listener)
      return () => listeners.delete(listener)
    }
  }

  const publishBackendState = state => {
    ctx.storage.set(STORAGE_KEY, state)
    snapshot = toSnapshot(state)
    for (const listener of [...listeners]) listener()
  }

  const mutate = (path, method, body) => {
    const request = async () => {
      const response = await ctx.rest(path, { method, body, timeoutMs: 5_000 })
      const state = responseState(response)
      publishBackendState(state)
    }
    const pending = mutationQueue.then(request, request)
    mutationQueue = pending.catch(() => undefined)
    return pending
  }

  const createGroup = name => mutate('/groups', 'POST', { name })
  const assignProject = (projectId, groupId) =>
    mutate('/assign', 'PUT', { project_id: projectId, group_id: groupId })
  const setGroupCollapsed = (groupId, collapsed) =>
    mutate('/groups/collapsed', 'PUT', { group_id: groupId, collapsed })

  const enableMutations = () => {
    provider.createGroup = createGroup
    provider.assignProject = assignProject
    provider.setGroupCollapsed = setGroupCollapsed
  }

  const start = async () => {
    try {
      let response = await ctx.rest('/state', { timeoutMs: 5_000 })
      if (response?.state == null) {
        response = await ctx.rest('/state/migrate', {
          method: 'POST',
          body: { state: cached },
          timeoutMs: 5_000
        })
      }
      const state = responseState(response)
      enableMutations()
      publishBackendState(state)
    } catch {
      // The cached snapshot remains available, without mutation callbacks.
    }
  }

  return { provider, start }
}

export default {
  id: ID,
  name: 'Project Groups',
  description: 'Group Projects inside the native Hermes Projects sidebar.',
  register(ctx) {
    const { provider, start } = createProvider(ctx)
    ctx.register({
      id: 'native-grouping',
      area: GROUPING_AREA,
      data: provider
    })
    void start()
  }
}
