import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'
import * as THREE from 'three'

const roomSource = await readFile(new URL('../src/room/SplatRoom.tsx', import.meta.url), 'utf8')
const room = ts.createSourceFile('SplatRoom.tsx', roomSource, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
const distance = room.statements.find((statement) => ts.isFunctionDeclaration(statement) && statement.name?.text === 'distanceToBox')
const radius = room.statements
  .filter(ts.isVariableStatement)
  .flatMap((statement) => [...statement.declarationList.declarations])
  .find((declaration) => declaration.name.getText(room) === 'NEARBY_RADIUS_M')
assert.ok(distance && radius?.initializer)
const boxSource = await readFile(new URL('../src/room/boxGeometry.ts', import.meta.url), 'utf8')
const boxJs = ts.transpile(boxSource, { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 })
  .replace("'three'", JSON.stringify(import.meta.resolve('three')))
const boxUrl = `data:text/javascript;base64,${Buffer.from(boxJs).toString('base64')}`
const js = ts.transpile(
  `import * as THREE from 'three'; import { boxQuaternion } from './boxGeometry'; ${distance.getText(room)}; export { distanceToBox }; export const radius = ${radius.initializer.getText(room)};`,
  { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 },
).replace("'three'", JSON.stringify(import.meta.resolve('three')))
  .replace("'./boxGeometry'", JSON.stringify(boxUrl))
const { distanceToBox, radius: nearbyRadius } = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)

test('synthetic boxes enter and leave proximity at the existing box-distance radius', () => {
  const box = {
    centre: [0, 0, 0],
    axes: [[0, 1, 0], [-1, 0, 0], [0, 0, 1]],
    extents: [4, 2, 2],
  }
  assert.equal(nearbyRadius, 2.5)
  assert.ok(distanceToBox(new THREE.Vector3(0, 4.5, 0), box) <= nearbyRadius)
  assert.ok(distanceToBox(new THREE.Vector3(0, 4.51, 0), box) > nearbyRadius)
  assert.match(roomSource, /for \(const object of candidates\)[\s\S]*?distanceToBox\(sceneRobot, object\) <= NEARBY_RADIUS_M/)
  assert.match(roomSource, /syntheticFrameOpacity\(child\.userData\.objectId, nearby, showNearbyHighlights\)/)
})

test('steady synthetic tint is gated by Objects tinted and the synthetic layer', async () => {
  const labSource = await readFile(new URL('../src/room/RoomLab.tsx', import.meta.url), 'utf8')
  assert.match(labSource, /showMappedFrames \? syntheticObjects : \[\]/)
  assert.match(labSource, /syntheticObjects=\{enabledSyntheticObjects\}/)
  assert.match(labSource, /objectOverlayUrl=\{view === 'semantics' \? '\/api\/filter\/anchors_overlay' : null\}/)
  assert.match(roomSource, /if \(!mesh \|\| !objectOverlayUrl \|\| syntheticObjects\.length === 0\)/)
  assert.match(roomSource, /syntheticTintSplatEdit\(syntheticObjects\)/)
  assert.match(roomSource, /\[objectOverlayUrl, syntheticObjects, splatUrl, filterUrl\]/)
})
