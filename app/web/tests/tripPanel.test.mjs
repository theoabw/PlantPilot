import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'
import { renderToStaticMarkup } from 'react-dom/server'
import { createElement } from 'react'

const source = await readFile(new URL('../src/room/RoomLab.tsx', import.meta.url), 'utf8')
const room = ts.createSourceFile('RoomLab.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
let panel
function findPanel(node) {
  if (ts.isConditionalExpression(node) && node.condition.getText(room) === 'driving') {
    const body = node.whenTrue
    if (ts.isParenthesizedExpression(body) && ts.isJsxElement(body.expression)
      && body.expression.openingElement.tagName.getText(room) === 'section') {
      panel = body.expression.getText(room)
    }
  }
  ts.forEachChild(node, findPanel)
}
findPanel(room)
assert.ok(panel, 'driving panel exists')
const js = ts.transpileModule(
  `export function TripPanel({ destinationTag, destinationLabel, mission, remaining, progress, nearbyEquipment }) { return (${panel}) }`,
  { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX } },
).outputText.replace('"react/jsx-runtime"', JSON.stringify(import.meta.resolve('react/jsx-runtime')))
const { TripPanel } = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)

test('trip panel shows progress without listing nearby equipment', () => {
  const html = renderToStaticMarkup(createElement(TripPanel, {
    destinationTag: 'P-005',
    remaining: 3.2,
    progress: 0.5,
    nearbyEquipment: [{ id: 'nearby', name: 'Nearby pump', state: 'watch' }],
  }))
  assert.match(html, /Driving to P-005/)
  assert.match(html, /3\.2 m/)
  assert.match(html, /width:50%/)
  assert.doesNotMatch(html, /Nearby pump|Synthetic pack status/)
  assert.match(source, /nearbyHighlightIds=\{nearbyHighlightIds\}/)
  assert.match(source, /showNearbyHighlights=\{driving\}/)
  assert.match(source, /onNearby=\{setNearby\}/)
})
