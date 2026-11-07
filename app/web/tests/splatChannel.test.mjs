import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'

const helper = await readFile(new URL('../src/room/splatChannel.ts', import.meta.url), 'utf8')
const js = ts.transpile(helper, { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 })
const { channelLabel } = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)
const room = await readFile(new URL('../src/room/SplatRoom.tsx', import.meta.url), 'utf8')

test('channel labels name the baked view', () => {
  assert.equal(channelLabel('/api/filter/height'), 'height')
  assert.equal(channelLabel('/api/filter/normals'), 'normals')
  assert.equal(channelLabel('/api/filter/edges_base'), 'edges')
  assert.equal(channelLabel('/api/splat'), 'photo')
  assert.equal(channelLabel(null), 'photo')
})

test('a channel swap keeps the old splats on screen and caches the photo capture', () => {
  // the swap no longer drops back to the full-screen first-load splash
  const swap = room.slice(room.indexOf('Swapping the baked information channel'))
  const effect = swap.slice(0, swap.indexOf('}, [filterUrl, splatUrl])'))
  assert.doesNotMatch(effect, /setLoaded\(false\)/)
  // the new mesh only replaces the old one once it is initialized
  assert.match(effect, /state\.pendingSplat = mesh/)
  assert.match(effect, /\.initialized[\s\S]*show\(mesh, wanted\)/)
  // the photo capture is reused instead of downloaded again
  assert.match(effect, /state\.baseSplat/)
})

test('splat edits follow the mesh that is actually drawn', () => {
  for (const marker of ['boxSplatFilter(filterBoxes)', 'heightSplatFilter(', 'selectionSplatEdit(highlighted)']) {
    const at = room.indexOf(marker)
    assert.ok(at > 0, marker)
    const deps = room.slice(at, room.indexOf('])', at))
    assert.match(deps, /meshVersion/, marker)
  }
})
