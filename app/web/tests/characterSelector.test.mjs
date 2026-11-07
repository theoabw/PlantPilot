import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'
import { renderToStaticMarkup } from 'react-dom/server'
import { createElement } from 'react'

const source = await readFile(new URL('../src/components/CharacterSelector.tsx', import.meta.url), 'utf8')
const js = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX },
}).outputText.replace('"react/jsx-runtime"', JSON.stringify(import.meta.resolve('react/jsx-runtime')))
const { default: CharacterSelector } = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)

const options = [
  { id: 'humanoid', label: 'Humanoid', radius: 0.18, height: 1.35 },
  { id: 'amr', label: 'Compact AMR', radius: 0.2, height: 0.55 },
  { id: 'cargo', label: 'Cargo AMR', radius: 0.45, height: 0.9 },
]

function buttons(element) {
  if (!element || typeof element !== 'object') return []
  const children = Array.isArray(element.props.children) ? element.props.children : [element.props.children]
  return [...(element.type === 'button' ? [element] : []), ...children.flat(Infinity).flatMap(buttons)]
}

test('header selector shows one selected character and calls the shared selection handler', () => {
  const chosen = []
  const props = { options, selected: 'amr', open: true, ready: true, onToggle() {}, onSelect: (id) => chosen.push(id) }
  const html = renderToStaticMarkup(createElement(CharacterSelector, props))
  assert.match(html, /Character <span[^>]*>Compact AMR/)
  assert.equal((html.match(/aria-pressed="true"/g) ?? []).length, 1)
  const choices = buttons(CharacterSelector(props))
  assert.equal(choices.length, 4)
  assert.equal(choices[2].props['aria-pressed'], true)
  choices[1].props.onClick()
  choices[3].props.onClick()
  assert.deepEqual(chosen, ['humanoid', 'cargo'])
})

test('selector remains available without equipment while the start loads', () => {
  const props = { options, selected: 'amr', open: true, ready: false, onToggle() {}, onSelect() {} }
  const choices = buttons(CharacterSelector(props))
  assert.equal(choices[0].props.disabled, undefined)
  assert.ok(choices.slice(1).every((button) => button.props.disabled))
  assert.match(renderToStaticMarkup(createElement(CharacterSelector, props)), /Waiting for the starting route/)
})
