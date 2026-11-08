import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'
import { renderToStaticMarkup } from 'react-dom/server'
import { createElement } from 'react'

const compile = async (path) => {
  const source = await readFile(new URL(path, import.meta.url), 'utf8')
  return ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX },
  }).outputText
}
const wordmark = await compile('../src/room/brandWordmark.ts')
const wordmarkUrl = `data:text/javascript;base64,${Buffer.from(wordmark).toString('base64')}`
const js = (await compile('../src/room/StartScreen.tsx'))
  .replace(/["']react\/jsx-runtime["']/, JSON.stringify(import.meta.resolve('react/jsx-runtime')))
  .replace(/["']react["']/, JSON.stringify(import.meta.resolve('react')))
  .replace(/["']\.\/brandWordmark["']/, JSON.stringify(wordmarkUrl))
const { default: StartScreen, shouldShowIntro } = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)

const text = (html) => html.replace(/<svg[\s\S]*?<\/svg>/g, '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()

test('a fresh visit shows the intro; direct links and capture flags skip it', () => {
  assert.equal(shouldShowIntro(''), true)
  assert.equal(shouldShowIntro('?occlusion=off'), true)
  for (const search of ['?demo', '?skipintro=1', '?sharp=1', '?perf=1', '?eye=1,2,3&target=0,0,0']) {
    assert.equal(shouldShowIntro(search), false, search)
  }
})

test('the start screen keeps to the essentials with one clear action', () => {
  const html = renderToStaticMarkup(createElement(StartScreen, { progress: 42, loaded: false, onStart() {} }))
  assert.match(html, /aria-label="PlantPilot"/)
  assert.match(html, /From scan to service\./)
  assert.equal((html.match(/<button/g) ?? []).length, 1)
  assert.match(html, />Start demo</)
  assert.match(html, /Loading the scan 42%/)
  assert.ok(text(html).split(' ').length < 40, 'copy stays short')
})

test('once the capture is drawn the button stands alone', () => {
  const html = renderToStaticMarkup(createElement(StartScreen, { progress: 100, loaded: true, onStart() {} }))
  assert.match(html, />Start demo</)
  assert.doesNotMatch(html, /Loading the scan/)
  assert.doesNotMatch(html, /ready/i)
})

test('the room view mounts the intro and keeps loading behind it', async () => {
  const room = await readFile(new URL('../src/room/RoomLab.tsx', import.meta.url), 'utf8')
  assert.match(room, /useState\(\(\) => shouldShowIntro\(window\.location\.search\)\)/)
  assert.match(room, /quietLoading=\{introOpen\}/)
  assert.match(room, /\{introOpen \? <StartScreen /)
})
