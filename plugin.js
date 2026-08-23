import { host } from '@hermes/plugin-sdk'

const ID = 'project-groups'
const GROUPING_AREA = 'projects.grouping'
const STORAGE_KEY = 'state.v1'
const MUTATION_CAPABILITIES = ['createGroup', 'assignProject', 'setGroupCollapsed']
const DEFAULT_GROUPS = [
  { id: 'cue', name: 'CUE++', collapsed: false },
  { id: 'rgc-labs', name: 'RGC-LABS', collapsed: false },
  { id: 'rgc-legacy', name: 'RGC Legacy', collapsed: false }
]

const cleanText = value => (typeof value === 'string' ? value.trim().replace(/\s+/gu, ' ') : '')
const utf16Length = value => value.length
const truncateUtf16 = (value, maxUnits) => {
  let result = ''
  for (const character of value) {
    if (utf16Length(result) + utf16Length(character) > maxUnits) break
    result += character
  }
  return result
}

const uniqueLegacyText = (value, used, maxUnits, label) => {
  const base = truncateUtf16(value, maxUnits)
  let candidate = base
  let index = 2
  while (used.has(candidate.toLowerCase())) {
    const suffix = label ? ` (${index})` : `-${index}`
    candidate = `${truncateUtf16(base, maxUnits - utf16Length(suffix))}${suffix}`
    index += 1
  }
  used.add(candidate.toLowerCase())
  return candidate
}

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
  for (const [rawGroupId, rawProjectIds] of Object.entries(rawOrder)) {
    const groupId = cleanText(rawGroupId)
    const isSyntheticGroup = groupId === '__ungrouped__'
    if ((!groupIds.has(groupId) && !isSyntheticGroup) || !Array.isArray(rawProjectIds)) continue
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

function normalizeLegacyState(input = {}) {
  const source = input && typeof input === 'object' && input.state && !input.groups ? input.state : input
  const groups = []
  const groupIds = new Set()
  const groupNames = new Set()
  const idAliases = new Map()

  for (const [index, raw] of (Array.isArray(source?.groups) ? source.groups : []).entries()) {
    const rawId = cleanText(raw?.id)
    const rawName = cleanText(raw?.name ?? raw?.label)
    const id = uniqueLegacyText(rawId || `group-${index + 1}`, groupIds, 200, false)
    const name = uniqueLegacyText(rawName || 'Untitled group', groupNames, 100, true)
    if (rawId && !idAliases.has(rawId)) idAliases.set(rawId, id)
    groups.push({ id, name, collapsed: raw?.collapsed === true })
  }

  const assignments = {}
  const rawAssignments = source?.assignments && typeof source.assignments === 'object' ? source.assignments : {}
  for (const [rawProjectId, rawGroupId] of Object.entries(rawAssignments)) {
    const projectId = cleanText(rawProjectId)
    const groupId = idAliases.get(cleanText(rawGroupId))
    if (projectId && groupId) assignments[projectId] = groupId
  }

  const projectOrder = {}
  const rawOrder = source?.projectOrder && typeof source.projectOrder === 'object' ? source.projectOrder : {}
  for (const [rawGroupId, rawProjectIds] of Object.entries(rawOrder)) {
    const cleanGroupId = cleanText(rawGroupId)
    const groupId = cleanGroupId === '__ungrouped__' ? cleanGroupId : idAliases.get(cleanGroupId)
    if (!groupId || !Array.isArray(rawProjectIds)) continue
    const seen = new Set(projectOrder[groupId] ?? [])
    projectOrder[groupId] = [...seen]
    for (const rawProjectId of rawProjectIds) {
      const projectId = cleanText(rawProjectId)
      if (!projectId || seen.has(projectId)) continue
      seen.add(projectId)
      projectOrder[groupId].push(projectId)
    }
  }

  return { version: 1, groups, assignments, projectOrder }
}

function toSnapshot(state, revision) {
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
  return Object.freeze({ groups: Object.freeze(groups), revision })
}

function responseState(response) {
  if (!response?.state || typeof response.state !== 'object' || !Array.isArray(response.state.groups)) {
    throw new Error('Project Groups backend returned invalid state')
  }
  return normalizeLegacyState(response.state)
}

function createProvider(ctx) {
  const cached = normalizeLegacyState(ctx.storage.get(STORAGE_KEY, { groups: DEFAULT_GROUPS }))
  const listeners = new Set()
  let currentState = cached
  let revision = 0
  let snapshot = toSnapshot(cached, revision)
  let mutationQueue = Promise.resolve()
  let authority = `${host.state.connectionId?.get?.() ?? ''}\u0000${host.state.profile?.get?.() ?? ''}`
  let generation = 0

  const provider = {
    getSnapshot: () => snapshot,
    subscribe: listener => {
      listeners.add(listener)
      return () => listeners.delete(listener)
    }
  }

  const nextRevision = () => {
    revision = revision === Number.MAX_SAFE_INTEGER ? 0 : revision + 1
    return revision
  }

  const publishBackendState = state => {
    currentState = state
    ctx.storage.set(STORAGE_KEY, state)
    snapshot = toSnapshot(state, nextRevision())
    for (const listener of [...listeners]) listener()
  }

  const publishTransientState = state => {
    currentState = state
    snapshot = toSnapshot(state, nextRevision())
    for (const listener of [...listeners]) listener()
  }

  const mutate = (path, method, body) => {
    const requestGeneration = generation
    const requestAuthority = authority
    const request = async () => {
      if (generation !== requestGeneration || authority !== requestAuthority) {
        throw new Error('Active Project Groups backend changed before mutation')
      }
      const response = await ctx.rest(path, { method, body, timeoutMs: 5_000 })
      if (generation !== requestGeneration || authority !== requestAuthority) {
        throw new Error('Active Project Groups backend changed during mutation')
      }
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

  const disableMutations = () => {
    delete provider.createGroup
    delete provider.assignProject
    delete provider.setGroupCollapsed
  }

  const load = async (requestGeneration, migrationState) => {
    let state
    try {
      let response = await ctx.rest('/state', { timeoutMs: 5_000 })
      if (response?.state == null) {
        if (generation !== requestGeneration) return
        response = await ctx.rest('/state/migrate', {
          method: 'POST',
          body: { state: migrationState },
          timeoutMs: 5_000
        })
      }
      if (generation !== requestGeneration) return
      state = responseState(response)
    } catch {
      // The cached snapshot remains available, without mutation callbacks.
      return
    }

    try {
      const capabilities = await ctx.rest('/capabilities', { timeoutMs: 5_000 })
      if (generation !== requestGeneration) return
      if (Array.isArray(capabilities?.mutations) && MUTATION_CAPABILITIES.every(item => capabilities.mutations.includes(item))) {
        enableMutations()
      }
    } catch {
      // State from a v0.2 backend remains visible without mutation callbacks.
    }

    if (generation === requestGeneration) publishBackendState(state)
  }

  const reloadAuthority = () => {
    const nextAuthority = `${host.state.connectionId?.get?.() ?? ''}\u0000${host.state.profile?.get?.() ?? ''}`
    if (nextAuthority === authority) return
    authority = nextAuthority
    generation += 1
    disableMutations()
    publishTransientState(normalizeState({ groups: [] }))
    void load(generation, normalizeState({ groups: [] }))
  }

  const reloadGateway = state => {
    generation += 1
    disableMutations()
    if (state === 'open') void load(generation, currentState)
    else publishTransientState(currentState)
  }

  const disposeProfile = host.state.profile?.listen?.(reloadAuthority)
  const disposeConnection = host.state.connectionId?.listen?.(reloadAuthority)
  const disposeGateway = host.state.gateway?.listen?.(reloadGateway)
  ctx.onDispose?.(() => {
    disposeProfile?.()
    disposeConnection?.()
    disposeGateway?.()
  })

  return { provider, start: () => load(generation, cached) }
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
