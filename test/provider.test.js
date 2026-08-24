import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const atom = initial => {
  let value = initial
  const listeners = new Set()
  return {
    get: () => value,
    listen(listener) {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
    set(next) {
      value = next
      for (const listener of [...listeners]) listener(next)
    }
  }
}

const host = {
  state: {
    connectionId: atom('local'),
    gateway: atom('open'),
    profile: atom('A')
  }
}

const pluginSource = await readFile(new URL('../plugin.js', import.meta.url), 'utf8')
const testablePluginSource = `const host = globalThis.__PROJECT_GROUPS_TEST_HOST__\n${pluginSource.replace(
  /^import\s+\{\s*host\s*\}\s+from\s+['"]@hermes\/plugin-sdk['"]\s*$/mu,
  ''
)}`
globalThis.__PROJECT_GROUPS_TEST_HOST__ = host
const { default: plugin } = await import(`data:text/javascript;base64,${Buffer.from(testablePluginSource).toString('base64')}`)

const state = (assignments = {}) => ({
  version: 1,
  groups: [{ id: 'cue', name: 'CUE++', collapsed: false }],
  assignments,
  projectOrder: { cue: ['p1'] }
})

const tick = () => new Promise(resolve => setImmediate(resolve))

test('root and Desktop entrypoints are byte-identical', async () => {
  const [root, desktop] = await Promise.all([
    readFile(new URL('../plugin.js', import.meta.url)),
    readFile(new URL('../desktop/plugin.js', import.meta.url))
  ])
  assert.deepEqual(desktop, root)
})

function context({ backend = state(), cached = state(), mutate } = {}) {
  const registrations = []
  const disposers = []
  const writes = []
  const storage = new Map([['state.v1', cached]])
  const ctx = {
    register(entry) {
      registrations.push(entry)
      return () => {}
    },
    onDispose(disposer) {
      disposers.push(disposer)
    },
    rest: async (path, options = {}) => {
      if (mutate && options.method !== undefined) return mutate(path, options)
      if (path === '/state') return { state: backend, storage: 'backend', version: 1 }
      if (path === '/capabilities') {
        return { mutations: ['createGroup', 'assignProject', 'setGroupCollapsed', 'deleteGroup'], version: 1 }
      }
      if (path === '/state/migrate') return { state: cached, storage: 'backend', version: 1 }
      throw new Error(`Unexpected REST request: ${path}`)
    },
    storage: {
      get(key, fallback) {
        return storage.has(key) ? storage.get(key) : fallback
      },
      set(key, value) {
        writes.push({ key, value })
        storage.set(key, value)
      }
    }
  }
  return {
    ctx,
    dispose() {
      for (const disposer of disposers.splice(0)) disposer()
    },
    registrations,
    storage,
    writes
  }
}

test('reloads state and mutation authority when the active profile changes A to B', async () => {
  const calls = []
  const backends = {
    A: {
      version: 1,
      groups: [{ id: 'a', name: 'Profile A', collapsed: false }],
      assignments: { projectA: 'a' },
      projectOrder: { a: ['projectA'] }
    },
    B: {
      version: 1,
      groups: [{ id: 'b', name: 'Profile B', collapsed: false }],
      assignments: { projectB: 'b' },
      projectOrder: { b: ['projectB'] }
    }
  }
  host.state.profile.set('A')
  const fixture = context()
  fixture.ctx.rest = async (path, options = {}) => {
    const profile = host.state.profile.get()
    calls.push([profile, path])
    if (path === '/state') return { state: backends[profile], storage: 'backend', version: 1 }
    if (path === '/capabilities') {
      return {
        mutations: profile === 'A' ? [] : ['createGroup', 'assignProject', 'setGroupCollapsed', 'deleteGroup'],
        version: 1
      }
    }
    if (options.method === 'PUT' && path === '/assign') {
      assert.equal(profile, 'B')
      assert.deepEqual(options.body, { project_id: 'projectB', group_id: null })
      return { state: backends.B, storage: 'backend', version: 1 }
    }
    throw new Error(`Unexpected REST request: ${path}`)
  }

  plugin.register(fixture.ctx)
  const provider = fixture.registrations[0].data
  await tick()
  assert.deepEqual(provider.getSnapshot().groups.map(group => group.id), ['a'])
  assert.equal(provider.assignProject, undefined)

  host.state.profile.set('B')
  await tick()
  assert.deepEqual(provider.getSnapshot().groups.map(group => group.id), ['b'])
  assert.deepEqual(provider.getSnapshot().groups[0].projectIds, ['projectB'])
  assert.equal(typeof provider.assignProject, 'function')
  assert.deepEqual(calls.filter(([, path]) => path === '/capabilities'), [
    ['A', '/capabilities'],
    ['B', '/capabilities']
  ])
  await provider.assignProject('projectB', null)
  fixture.dispose()
})

test('publishes capability-only profile changes through the grouping snapshot revision', async () => {
  const backend = state({ p1: 'cue' })
  host.state.gateway.set('open')
  host.state.profile.set('read-only')
  const fixture = context({ backend })
  fixture.ctx.rest = async path => {
    if (path === '/state') return { state: backend, storage: 'backend', version: 1 }
    if (path === '/capabilities') {
      return {
        mutations: host.state.profile.get() === 'mutable' ? ['createGroup', 'assignProject', 'setGroupCollapsed', 'deleteGroup'] : [],
        version: 1
      }
    }
    throw new Error(`Unexpected REST request: ${path}`)
  }

  plugin.register(fixture.ctx)
  const provider = fixture.registrations[0].data
  await tick()
  const readOnlySnapshot = provider.getSnapshot()
  assert.equal(provider.assignProject, undefined)
  assert.equal(Number.isSafeInteger(readOnlySnapshot.revision), true)

  host.state.profile.set('mutable')
  await tick()
  const mutableSnapshot = provider.getSnapshot()
  assert.deepEqual(mutableSnapshot.groups, readOnlySnapshot.groups)
  assert.ok(mutableSnapshot.revision > readOnlySnapshot.revision)
  assert.equal(typeof provider.assignProject, 'function')
  fixture.dispose()
})

test('publishes disconnected to connected capability restoration and the reverse', async () => {
  const backend = state({ p1: 'cue' })
  let connected = false
  host.state.gateway.set('closed')
  const fixture = context({ backend, cached: backend })
  fixture.ctx.rest = async path => {
    if (!connected) throw new Error('offline')
    if (path === '/state') return { state: backend, storage: 'backend', version: 1 }
    if (path === '/capabilities') {
      return { mutations: ['createGroup', 'assignProject', 'setGroupCollapsed', 'deleteGroup'], version: 1 }
    }
    throw new Error(`Unexpected REST request: ${path}`)
  }

  plugin.register(fixture.ctx)
  const provider = fixture.registrations[0].data
  await tick()
  const disconnectedSnapshot = provider.getSnapshot()
  assert.equal(provider.assignProject, undefined)
  assert.equal(Number.isSafeInteger(disconnectedSnapshot.revision), true)

  connected = true
  host.state.gateway.set('open')
  await tick()
  const connectedSnapshot = provider.getSnapshot()
  assert.deepEqual(connectedSnapshot.groups, disconnectedSnapshot.groups)
  assert.ok(connectedSnapshot.revision > disconnectedSnapshot.revision)
  assert.equal(typeof provider.assignProject, 'function')

  host.state.gateway.set('closed')
  const reDisconnectedSnapshot = provider.getSnapshot()
  assert.deepEqual(reDisconnectedSnapshot.groups, connectedSnapshot.groups)
  assert.ok(reDisconnectedSnapshot.revision > connectedSnapshot.revision)
  assert.equal(provider.assignProject, undefined)
  fixture.dispose()
})

test('ignores a delayed Profile A load after switching to Profile B', async () => {
  let resolveProfileA
  const profileA = new Promise(resolve => {
    resolveProfileA = resolve
  })
  const profileB = {
    version: 1,
    groups: [{ id: 'b', name: 'Profile B', collapsed: false }],
    assignments: { projectB: 'b' },
    projectOrder: { b: ['projectB'] }
  }
  const calls = []
  host.state.profile.set('A')
  const fixture = context()
  fixture.ctx.rest = async path => {
    const profile = host.state.profile.get()
    calls.push([profile, path])
    if (path === '/state' && profile === 'A') return profileA
    if (path === '/state' && profile === 'B') return { state: profileB, storage: 'backend', version: 1 }
    if (path === '/capabilities') {
      return { mutations: ['createGroup', 'assignProject', 'setGroupCollapsed', 'deleteGroup'], version: 1 }
    }
    throw new Error(`Unexpected REST request: ${path}`)
  }

  plugin.register(fixture.ctx)
  const provider = fixture.registrations[0].data
  host.state.profile.set('B')
  await tick()
  resolveProfileA({ state: null, storage: 'backend', version: 1 })
  await tick()

  assert.deepEqual(provider.getSnapshot().groups.map(group => group.id), ['b'])
  assert.equal(calls.some(([, path]) => path === '/state/migrate'), false)
  fixture.dispose()
})

test('registers one stable native projects.grouping provider and no page or nav', async () => {
  const fixture = context()
  plugin.register(fixture.ctx)

  assert.equal(fixture.registrations.length, 1)
  assert.equal(fixture.registrations[0].area, 'projects.grouping')
  const provider = fixture.registrations[0].data
  const initial = provider.getSnapshot()
  assert.strictEqual(provider.getSnapshot(), initial)

  await tick()
  assert.strictEqual(fixture.registrations[0].data, provider)
  assert.equal(typeof provider.createGroup, 'function')
  assert.equal(typeof provider.assignProject, 'function')
  assert.equal(typeof provider.setGroupCollapsed, 'function')
  assert.equal(typeof provider.deleteGroup, 'function')
})

test('deleteGroup uses one exact-CAS DELETE mutation for empty and non-empty groups', async () => {
  for (const expectedProjectIds of [[], ['p1', 'p2']]) {
    const calls = []
    const backend = state(Object.fromEntries(expectedProjectIds.map(projectId => [projectId, 'cue'])))
    const deleted = { version: 1, groups: [], assignments: {}, projectOrder: {} }
    const fixture = context({ backend })
    fixture.ctx.rest = async (path, options = {}) => {
      if (path === '/state') return { state: backend, storage: 'backend', version: 1 }
      if (path === '/capabilities') {
        return { mutations: ['createGroup', 'assignProject', 'setGroupCollapsed', 'deleteGroup'], version: 1 }
      }
      if (path === '/groups' && options.method === 'DELETE') {
        calls.push({ path, options })
        return { state: deleted, storage: 'backend', version: 1 }
      }
      throw new Error(`Unexpected REST request: ${path}`)
    }

    plugin.register(fixture.ctx)
    const provider = fixture.registrations[0].data
    await tick()
    await provider.deleteGroup({
      groupId: 'cue',
      expectedProjectIds,
      operationId: `delete-${expectedProjectIds.length}`
    })

    assert.deepEqual(calls, [{
      path: '/groups',
      options: {
        method: 'DELETE',
        body: {
          group_id: 'cue',
          expected_project_ids: expectedProjectIds,
          operation_id: `delete-${expectedProjectIds.length}`
        },
        timeoutMs: 5_000
      }
    }])
    assert.deepEqual(provider.getSnapshot().groups, [])
    fixture.dispose()
  }
})

test('deleteGroup rejects a response from a stale profile generation without publishing it', async () => {
  let resolveDelete
  let markDeleteStarted
  const pendingDelete = new Promise(resolve => {
    resolveDelete = resolve
  })
  const deleteStarted = new Promise(resolve => {
    markDeleteStarted = resolve
  })
  const profileB = {
    version: 1,
    groups: [{ id: 'b', name: 'Profile B', collapsed: false }],
    assignments: {},
    projectOrder: {}
  }
  host.state.profile.set('A')
  const fixture = context({ backend: state() })
  fixture.ctx.rest = async (path, options = {}) => {
    if (path === '/state') {
      return {
        state: host.state.profile.get() === 'A' ? state() : profileB,
        storage: 'backend',
        version: 1
      }
    }
    if (path === '/capabilities') {
      return { mutations: ['createGroup', 'assignProject', 'setGroupCollapsed', 'deleteGroup'], version: 1 }
    }
    if (path === '/groups' && options.method === 'DELETE') {
      markDeleteStarted()
      return pendingDelete
    }
    throw new Error(`Unexpected REST request: ${path}`)
  }

  plugin.register(fixture.ctx)
  const provider = fixture.registrations[0].data
  await tick()
  const deletion = provider.deleteGroup({
    groupId: 'cue',
    expectedProjectIds: [],
    operationId: 'delete-stale-profile'
  })
  await deleteStarted
  host.state.profile.set('B')
  await tick()
  resolveDelete({ state: { version: 1, groups: [], assignments: {}, projectOrder: {} } })

  await assert.rejects(deletion, /backend changed during mutation/)
  assert.deepEqual(provider.getSnapshot().groups.map(group => group.id), ['b'])
  fixture.dispose()
})

test('keeps an offline cached snapshot read-only', async () => {
  const fixture = context()
  fixture.ctx.rest = async () => {
    throw new Error('offline')
  }
  plugin.register(fixture.ctx)
  const provider = fixture.registrations[0].data

  await tick()
  assert.deepEqual(provider.getSnapshot().groups[0].projectIds, [])
  assert.equal(provider.createGroup, undefined)
  assert.equal(provider.assignProject, undefined)
  assert.equal(provider.setGroupCollapsed, undefined)
  assert.equal(provider.deleteGroup, undefined)
  assert.equal(fixture.writes.length, 0)
})

test('keeps an older backend read-only when state exists but mutation capability is absent', async () => {
  const fixture = context({ backend: state({ p1: 'cue' }), cached: state() })
  fixture.ctx.rest = async path => {
    if (path === '/state') return { state: state({ p1: 'cue' }), storage: 'backend', version: 1 }
    throw new Error('not found')
  }
  plugin.register(fixture.ctx)
  const provider = fixture.registrations[0].data

  await tick()
  assert.deepEqual(provider.getSnapshot().groups[0].projectIds, ['p1'])
  assert.equal(provider.createGroup, undefined)
  assert.equal(provider.assignProject, undefined)
  assert.equal(provider.setGroupCollapsed, undefined)
  assert.equal(provider.deleteGroup, undefined)
})

test('keeps existing mutations when an older backend does not advertise deleteGroup', async () => {
  const fixture = context({ backend: state({ p1: 'cue' }) })
  fixture.ctx.rest = async path => {
    if (path === '/state') return { state: state({ p1: 'cue' }), storage: 'backend', version: 1 }
    if (path === '/capabilities') {
      return { mutations: ['createGroup', 'assignProject', 'setGroupCollapsed'], version: 1 }
    }
    throw new Error(`Unexpected REST request: ${path}`)
  }
  plugin.register(fixture.ctx)
  const provider = fixture.registrations[0].data

  await tick()
  assert.equal(typeof provider.createGroup, 'function')
  assert.equal(typeof provider.assignProject, 'function')
  assert.equal(typeof provider.setGroupCollapsed, 'function')
  assert.equal(provider.deleteGroup, undefined)
  fixture.dispose()
})

test('publishes exactly once after backend mutation success and never optimistically', async () => {
  let resolveMutation
  const mutation = new Promise(resolve => {
    resolveMutation = resolve
  })
  const fixture = context({
    mutate: async (path, options) => {
      assert.equal(path, '/assign')
      assert.deepEqual(options.body, { project_id: 'p1', group_id: 'cue' })
      return mutation
    }
  })
  plugin.register(fixture.ctx)
  const provider = fixture.registrations[0].data
  await tick()

  let publications = 0
  provider.subscribe(() => {
    publications += 1
  })
  const before = provider.getSnapshot()
  const writeCount = fixture.writes.length
  const pending = provider.assignProject('p1', 'cue')

  assert.strictEqual(provider.getSnapshot(), before)
  assert.equal(fixture.writes.length, writeCount)
  assert.equal(publications, 0)

  resolveMutation({ state: state({ p1: 'cue' }), storage: 'backend', version: 1 })
  await pending
  assert.notStrictEqual(provider.getSnapshot(), before)
  assert.deepEqual(provider.getSnapshot().groups[0].projectIds, ['p1'])
  assert.equal(fixture.writes.length, writeCount + 1)
  assert.equal(publications, 1)
})

test('backend rejection preserves the stable snapshot and cache', async () => {
  const fixture = context({
    mutate: async () => {
      throw new Error('rejected')
    }
  })
  plugin.register(fixture.ctx)
  const provider = fixture.registrations[0].data
  await tick()

  let publications = 0
  provider.subscribe(() => {
    publications += 1
  })
  const before = provider.getSnapshot()
  const writeCount = fixture.writes.length

  await assert.rejects(provider.createGroup('Other'), /rejected/)
  assert.strictEqual(provider.getSnapshot(), before)
  assert.equal(fixture.writes.length, writeCount)
  assert.equal(publications, 0)
})

test('migrates legacy cache when backend has no state', async () => {
  const fixture = context({ backend: null, cached: state({ p1: 'cue' }) })
  const calls = []
  const originalRest = fixture.ctx.rest
  fixture.ctx.rest = async (path, options = {}) => {
    calls.push({ path, options })
    return originalRest(path, options)
  }
  plugin.register(fixture.ctx)
  const provider = fixture.registrations[0].data

  await tick()
  assert.deepEqual(calls.map(call => call.path), ['/state', '/state/migrate', '/capabilities'])
  assert.deepEqual(calls[1].options.body.state.assignments, { p1: 'cue' })
  assert.deepEqual(provider.getSnapshot().groups[0].projectIds, ['p1'])
  assert.equal(typeof provider.assignProject, 'function')
})

test('repairs v0.2 cache names and duplicate labels without losing groups or assignments', async () => {
  const legacy = {
    version: 1,
    groups: [
      { id: 'long', name: 'L'.repeat(101) },
      { id: 'duplicate-1', name: 'Shared label' },
      { id: 'duplicate-2', name: ' shared   label ' }
    ],
    assignments: {
      projectLong: 'long',
      projectOne: 'duplicate-1',
      projectTwo: 'duplicate-2'
    },
    projectOrder: {
      long: ['projectLong'],
      'duplicate-1': ['projectOne'],
      'duplicate-2': ['projectTwo'],
      __ungrouped__: ['projectTwo', 'projectLong']
    }
  }
  const fixture = context({ backend: null, cached: legacy })
  let migrated
  const originalRest = fixture.ctx.rest
  fixture.ctx.rest = async (path, options = {}) => {
    if (path === '/state/migrate') migrated = options.body.state
    return originalRest(path, options)
  }

  plugin.register(fixture.ctx)
  await tick()

  assert.deepEqual(migrated.groups.map(group => [group.id, group.name]), [
    ['long', 'L'.repeat(100)],
    ['duplicate-1', 'Shared label'],
    ['duplicate-2', 'shared label (2)']
  ])
  assert.deepEqual(migrated.assignments, legacy.assignments)
  assert.deepEqual(migrated.projectOrder, legacy.projectOrder)
})

test('a new Desktop process reloads authoritative backend state over stale cache', async () => {
  const fixture = context({ backend: state({ p1: 'cue' }), cached: state() })
  plugin.register(fixture.ctx)
  const firstProvider = fixture.registrations[0].data
  await tick()

  const reloaded = context({ backend: state({ p1: 'cue' }), cached: state() })
  plugin.register(reloaded.ctx)
  const secondProvider = reloaded.registrations[0].data
  await tick()

  assert.notStrictEqual(secondProvider, firstProvider)
  assert.deepEqual(secondProvider.getSnapshot(), firstProvider.getSnapshot())
  assert.deepEqual(secondProvider.getSnapshot().groups[0].projectIds, ['p1'])
})
