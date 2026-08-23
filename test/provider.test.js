import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

import plugin from '../plugin.js'

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
  const writes = []
  const storage = new Map([['state.v1', cached]])
  const ctx = {
    register(entry) {
      registrations.push(entry)
      return () => {}
    },
    rest: async (path, options = {}) => {
      if (mutate && options.method !== undefined) return mutate(path, options)
      if (path === '/state') return { state: backend, storage: 'backend', version: 1 }
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
  return { ctx, registrations, storage, writes }
}

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
  assert.equal(fixture.writes.length, 0)
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
  assert.deepEqual(calls.map(call => call.path), ['/state', '/state/migrate'])
  assert.deepEqual(calls[1].options.body.state.assignments, { p1: 'cue' })
  assert.deepEqual(provider.getSnapshot().groups[0].projectIds, ['p1'])
  assert.equal(typeof provider.assignProject, 'function')
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
