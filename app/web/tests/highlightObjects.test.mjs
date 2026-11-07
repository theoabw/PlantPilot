import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'

const source = await readFile(new URL('../src/room/highlightObjects.ts', import.meta.url), 'utf8')
const js = ts.transpile(source, { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 })
const { highlightObjects } = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)

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
