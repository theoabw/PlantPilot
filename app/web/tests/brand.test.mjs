import assert from 'node:assert/strict'
import { existsSync } from 'node:fs'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const web = new URL('../', import.meta.url)
const publicFile = (path) => new URL(`public${path}`, web)
const read = (path) => readFile(new URL(path, web), 'utf8')
const brandPaths = (text) => [...text.matchAll(/\/brand\/[\w.-]+/g)].map((match) => match[0])

test('every brand file the page head names is served', async () => {
  const paths = brandPaths(await read('index.html'))
  assert.ok(paths.length >= 5)
  for (const path of paths) assert.ok(existsSync(publicFile(path)), path)
})

test('every brand file the viewer draws is served', async () => {
  const paths = [
    ...brandPaths(await read('src/room/RoomLab.tsx')),
    ...brandPaths(await read('src/room/SplatRoom.tsx')),
  ]
  assert.ok(paths.length >= 3)
  for (const path of paths) assert.ok(existsSync(publicFile(path)), path)
})

test('every icon in the web manifest is served', async () => {
  const manifest = JSON.parse(await read('public/brand/site.webmanifest'))
  assert.ok(manifest.icons.length > 0)
  for (const icon of manifest.icons) assert.ok(existsSync(publicFile(`/brand/${icon.src}`)), icon.src)
})

test('the homepage is self-contained and every file it names exists', async () => {
  const site = new URL('../../site/', web)
  const page = await readFile(new URL('index.html', site), 'utf8')
  const assets = [...page.matchAll(/assets\/[\w.-]+/g)].map((match) => match[0])
  assert.ok(assets.length >= 5)
  for (const path of assets) assert.ok(existsSync(new URL(path, site)), path)
  const loaded = [...page.matchAll(/<(?:script|img|link)\b[^>]*\b(?:src|href)="(https?:[^"]+)"/g)]
  assert.deepEqual(loaded.map((match) => match[1]), [])
})

test('the container image keeps the PNGs the page serves', async () => {
  const lines = (await readFile(new URL('../../.dockerignore', web), 'utf8')).split(/\r?\n/)
  const excluded = lines.indexOf('*.png')
  const kept = lines.indexOf('!app/web/public/brand/*.png')
  assert.ok(excluded >= 0 && kept > excluded, 'the exception has to follow the exclusion')
})
