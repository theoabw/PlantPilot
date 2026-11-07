import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'

const source = await readFile(new URL('../src/room/walkGrid.ts', import.meta.url), 'utf8')
const js = ts.transpile(source, { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 })
const { escapeDistances, canEscapeCell } = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)

test('blocked starts can move toward free space but not deeper through obstacles', () => {
  const distances = escapeDistances({ rows: 1, cols: 5, bits: Uint8Array.of(0b01110000) })
  assert.deepEqual([...distances], [0, 1, 2, 1, 0])
  assert.equal(canEscapeCell(1, 2, distances), false)
  assert.equal(canEscapeCell(2, 1, distances), true)
  assert.equal(canEscapeCell(1, 1, distances), true)
  assert.equal(canEscapeCell(1, -1, distances), false)
})

test('a grid with no free cells has no escape', () => {
  const distances = escapeDistances({ rows: 1, cols: 2, bits: Uint8Array.of(0b11000000) })
  assert.equal(canEscapeCell(0, 1, distances), false)
})
