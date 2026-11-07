import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'

const source = await readFile(new URL('../src/room/highlightObjects.ts', import.meta.url), 'utf8')
const js = ts.transpile(source, { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 })
const { highlightObjects, nearbyHighlightIds, syntheticFrameOpacity, syntheticMappedObjects, proximityCandidates } = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)

test('moving highlights exactly the displayed nearby objects and keeps selection', () => {
  const objects = [{ id: 'a' }, { id: 'b' }, { id: 'c' }]
  const selected = { id: 'selected' }
  assert.deepEqual(highlightObjects(objects, [selected], 'selected', ['a', 'c'], true), [selected, objects[0], objects[2]])
  assert.deepEqual(highlightObjects(objects, [selected], 'selected', ['b'], true), [selected, objects[1]])
})

test('selection remains when nearby highlighting is off and duplicates are avoided', () => {
  const objects = [{ id: 'a' }, { id: 'b' }]
  assert.deepEqual(highlightObjects(objects, [], 'a', ['a', 'b'], true), objects)
  assert.deepEqual(highlightObjects(objects, [], 'a', ['a', 'b'], false), [objects[0]])
  assert.deepEqual(highlightObjects(objects, [], null, ['missing'], true), [])
  assert.deepEqual(highlightObjects([], [], null, ['a'], false), [])
})

test('only mapped synthetic detections join the nearby scan when the layer is enabled', () => {
  const reviewed = { id: 'anchor' }
  const raw = [{ id: 'mapped' }, { id: 'unmapped' }]
  const synthetic = syntheticMappedObjects(raw, [{ object_id: 'mapped' }, { object_id: null }, { object_id: 'missing' }])
  assert.deepEqual(synthetic, [raw[0]])
  assert.deepEqual(proximityCandidates([reviewed], synthetic, false), [reviewed])
  assert.deepEqual(proximityCandidates([reviewed], synthetic, true), [reviewed, raw[0]])
  assert.deepEqual(proximityCandidates([raw[0]], synthetic, true), [raw[0]])
  assert.deepEqual(proximityCandidates([], synthetic, true), [raw[0]])
})

test('synthetic highlights follow nearby IDs, the layer and trip state without duplicating selection', () => {
  const anchor = { id: 'anchor' }
  const synthetic = [{ id: 'mapped-1' }, { id: 'mapped-2' }]
  const objects = [anchor]
  assert.deepEqual(highlightObjects(objects, synthetic, 'mapped-1', ['anchor', 'mapped-1'], true, synthetic), [synthetic[0], anchor])
  assert.deepEqual(highlightObjects(objects, synthetic, null, ['mapped-2'], true, synthetic), [synthetic[1]])
  assert.deepEqual(highlightObjects(objects, synthetic, null, ['mapped-2'], true, []), [])
  assert.deepEqual(highlightObjects(objects, synthetic, 'anchor', ['mapped-2'], false, synthetic), [anchor])
})

test('mapped proposals do not displace reviewed highlights and frame brightness follows trip state', () => {
  const synthetic = [{ id: 'mapped-1' }, { id: 'mapped-2' }]
  const ids = nearbyHighlightIds(['anchor'], ['mapped-1', 'unmapped'], synthetic)
  assert.deepEqual(ids, ['anchor', 'mapped-1'])
  assert.deepEqual(nearbyHighlightIds(['anchor'], ['mapped-1'], []), ['anchor'])
  const nearby = new Set(ids)
  assert.equal(syntheticFrameOpacity('mapped-1', nearby, true), 1)
  assert.equal(syntheticFrameOpacity('mapped-2', nearby, true), 0.55)
  assert.equal(syntheticFrameOpacity('mapped-1', nearby, false), 0.55)
})
