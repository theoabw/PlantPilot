import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'

const source = await readFile(new URL('../src/room/renderScale.ts', import.meta.url), 'utf8')
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 } }).outputText
const { nextRenderScale, RENDER_SCALE_MIN } = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)

test('slow frames lower the scale, but never below the floor', () => {
  assert.ok(nextRenderScale(1, 200) < 1)
  let scale = 1
  for (let step = 0; step < 20; step += 1) scale = nextRenderScale(scale, 200)
  assert.equal(scale, RENDER_SCALE_MIN)
})

test('fast frames raise the scale, but never above full resolution', () => {
  assert.ok(nextRenderScale(0.5, 16) > 0.5)
  assert.equal(nextRenderScale(1, 16), 1)
})

test('frames between the thresholds hold the scale, so it does not oscillate', () => {
  assert.equal(nextRenderScale(0.6, 25), 0.6)
})
