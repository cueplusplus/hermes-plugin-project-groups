import test from 'node:test'
import assert from 'node:assert/strict'

import {
  DEFAULT_GROUPS,
  assignProject,
  autoGroupProjects,
  createGroup,
  deleteGroup,
  moveGroup,
  moveProject,
  normalizeState,
  renameGroup,
  unassignProject
} from '../src/groups.js'

const projects = [
  { id: 'p_cue', name: 'CUE++ · Quotamate', primary_path: '/Users/demo/work/cue++/quotamate' },
  { id: 'p_labs', name: 'RGC-LABS · Knowledgebase', primary_path: '/Users/demo/work/rgc-labs/knowledgebase' },
  { id: 'p_legacy', name: 'RGC Legacy · BTS v3', primary_path: '/Users/demo/work/rgc/bts-v3' },
  { id: 'p_misc', name: 'Personal Demo', primary_path: '/Users/demo/Desktop/demo' }
]

test('autoGroupProjects assigns organization roots and leaves unrelated projects ungrouped', () => {
  const state = autoGroupProjects(projects, { groups: DEFAULT_GROUPS, assignments: {} })

  assert.equal(state.assignments.p_cue, 'cue')
  assert.equal(state.assignments.p_labs, 'rgc-labs')
  assert.equal(state.assignments.p_legacy, 'rgc-legacy')
  assert.equal(state.assignments.p_misc, undefined)
})

test('autoGroupProjects respects an intentionally empty group list', () => {
  const state = autoGroupProjects(projects, { groups: [], assignments: {}, projectOrder: {} })
  assert.deepEqual(state.groups, [])
  assert.deepEqual(state.assignments, {})
})

test('manual assignments survive automatic grouping', () => {
  const state = autoGroupProjects(projects, {
    groups: DEFAULT_GROUPS,
    assignments: { p_cue: 'rgc-labs' }
  })

  assert.equal(state.assignments.p_cue, 'rgc-labs')
})

test('create, rename, reorder, assign and unassign preserve stable ids', () => {
  let state = normalizeState({ groups: [], assignments: {} })
  state = createGroup(state, { id: 'studio', name: 'Studio' })
  state = createGroup(state, { id: 'archive', name: 'Archive' })
  state = renameGroup(state, 'studio', 'Studio Projects')
  state = moveGroup(state, 'archive', -1)
  state = assignProject(state, 'p_misc', 'studio')

  assert.deepEqual(state.groups.map(group => [group.id, group.name]), [
    ['archive', 'Archive'],
    ['studio', 'Studio Projects']
  ])
  assert.equal(state.assignments.p_misc, 'studio')

  state = unassignProject(state, 'p_misc')
  assert.equal(state.assignments.p_misc, undefined)
})

test('project order is explicit, stable, and moves within a group', () => {
  let state = normalizeState({
    groups: [{ id: 'cue', name: 'CUE++' }],
    assignments: { a: 'cue', b: 'cue', c: 'cue' },
    projectOrder: { cue: ['a', 'b', 'c'] }
  })

  state = moveProject(state, 'cue', 'c', -1)
  assert.deepEqual(state.projectOrder.cue, ['a', 'c', 'b'])

  state = moveProject(state, 'cue', 'a', -1)
  assert.deepEqual(state.projectOrder.cue, ['a', 'c', 'b'])
})

test('deleting a group removes its project assignments without affecting other groups', () => {
  const state = deleteGroup(
    {
      groups: [
        { id: 'one', name: 'One' },
        { id: 'two', name: 'Two' }
      ],
      assignments: { a: 'one', b: 'two' },
      projectOrder: { one: ['a'], two: ['b'], __ungrouped__: ['c'] }
    },
    'one'
  )

  assert.deepEqual(state.groups, [{ id: 'two', name: 'Two', collapsed: false }])
  assert.deepEqual(state.assignments, { b: 'two' })
  assert.deepEqual(state.projectOrder, { two: ['b'], __ungrouped__: ['c'] })
})

test('normalizeState repairs malformed and dangling persisted data', () => {
  const state = normalizeState({
    groups: [
      { id: 'cue', name: ' CUE++ ' },
      { id: 'cue', name: 'Duplicate' },
      { id: '', name: 'Invalid' }
    ],
    assignments: { a: 'cue', b: 'missing', c: 4 }
  })

  assert.deepEqual(state.groups, [{ id: 'cue', name: 'CUE++', collapsed: false }])
  assert.deepEqual(state.assignments, { a: 'cue' })
})

test('createGroup enforces authoritative name normalization rules', () => {
  const state = normalizeState({ groups: [{ id: 'one', name: 'Alpha' }] })

  assert.throws(
    () => createGroup(state, { id: 'two', name: '  alpha  ' }),
    /already exists/i
  )
  assert.throws(
    () => createGroup(state, { id: 'emoji', name: '😀'.repeat(51) }),
    /1-100 UTF-16/
  )
})
