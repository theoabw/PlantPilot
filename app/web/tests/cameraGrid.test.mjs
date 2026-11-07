import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'

const source = await readFile(new URL('../src/room/cameraGrid.ts', import.meta.url), 'utf8')
const js = ts.transpile(source, { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 })
const { cameraGridClearance, cameraGridIsFree } = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)

const mask = (blockedCells = []) => {
  const bits = new Uint8Array(2)
  for (const index of blockedCells) {
    bits[index >> 3] |= 0x80 >> (index & 7)
  }
  return { x0: 0, z0: 0, cell_m: 1, rows: 4, cols: 4, bits }
}

test('diagonal blocked cells outside the clearance radius do not reduce clearance', () => {
  assert.equal(cameraGridClearance(mask([10]), 1.5, 1.5, 0.2), 0.2)
})

test('clearance measures the distance to a nearby blocked cell', () => {
  assert.equal(cameraGridClearance(mask([6]), 1.5, 1.5, 1), 0.5)
})

test('positions outside the grid are blocked', () => {
  assert.equal(cameraGridClearance(mask(), -0.1, 1.5, 0.5), 0)
})

test('camera candidates must be farther than their clearance margin from blocked cells', () => {
  const grid = mask([6])
  for (const margin of [0.1, 0.12]) {
    assert.equal(cameraGridIsFree(grid, 1.5, 1.5, margin), true, `open position at margin ${margin}`)
    assert.equal(cameraGridIsFree(grid, 2 - margin / 2, 1.5, margin), false, `too close at margin ${margin}`)
    assert.equal(cameraGridIsFree(grid, 2.5, 1.5, margin), false, `blocked at margin ${margin}`)
    assert.equal(cameraGridIsFree(grid, -0.1, 1.5, margin), false, `outside at margin ${margin}`)
  }
  assert.equal(cameraGridIsFree(grid, 1.875, 1.5, 0.125), false, 'exactly at the clearance boundary')
})
