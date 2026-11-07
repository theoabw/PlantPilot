import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'
import * as THREE from 'three'

const brandSource = await readFile(new URL('../src/room/robotBrand.ts', import.meta.url), 'utf8')
const brandJs = ts.transpile(brandSource, { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 })
  .replace("'three'", JSON.stringify(import.meta.resolve('three')))
const brandUrl = `data:text/javascript;base64,${Buffer.from(brandJs).toString('base64')}`
const { ROBOT_PALETTE } = await import(brandUrl)

const source = await readFile(new URL('../src/room/SplatRoom.tsx', import.meta.url), 'utf8')
const parsed = ts.createSourceFile('SplatRoom.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
const body = parsed.statements.find((node) => ts.isFunctionDeclaration(node) && node.name?.text === 'buildRobotBody')
assert.ok(body, 'robot model builder exists')
const moduleSource = `
import * as THREE from ${JSON.stringify(import.meta.resolve('three'))}
import { ROBOT_PALETTE, robotLogo } from ${JSON.stringify(brandUrl)}
const ROBOT_TRIM_COLOUR = ROBOT_PALETTE.green
let robotCrouchSpans: [number, number][] = []
let robotManualCrouch: boolean | null = null
${body.getText(parsed)}
export { buildRobotBody }
`
const js = ts.transpile(moduleSource, { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 })
const { buildRobotBody } = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)

test('local logo has the actual PNG format and expected dimensions', async () => {
  const image = await readFile(new URL('../public/brand/valmet-logo.png', import.meta.url))
  assert.equal(image.subarray(0, 8).toString('hex'), '89504e470d0a1a0a')
  assert.equal(image.readUInt32BE(16), 2149)
  assert.equal(image.readUInt32BE(20), 768)
})

for (const profile of ['humanoid', 'amr']) {
  test(`${profile} has logo badges and retains safety equipment colors`, () => {
    const texture = new THREE.Texture()
    const robot = buildRobotBody(profile, texture)
    const meshes = []
    robot.traverse((child) => { if (child instanceof THREE.Mesh) meshes.push(child) })
    const badges = meshes.filter((mesh) => mesh.material.map === texture)
    assert.equal(badges.length, profile === 'humanoid' ? 2 : 3)
    for (const badge of badges) {
      assert.equal(badge.userData.noGhost, true)
      assert.equal(badge.material.transparent, true)
      assert.equal(badge.material.depthTest, true)
      assert.equal(badge.renderOrder, 4)
      assert.ok(Math.abs(badge.geometry.parameters.width / badge.geometry.parameters.height - 2149 / 768) < 1e-8)
    }
    const colors = meshes.map((mesh) => mesh.material.color.getHex())
    if (profile === 'humanoid') {
      assert.ok(colors.includes(ROBOT_PALETTE.hiVis))
      assert.ok(colors.includes(ROBOT_PALETTE.hardHat))
      assert.ok(colors.includes(ROBOT_PALETTE.darkGrey))
    } else {
      assert.ok(colors.includes(ROBOT_PALETTE.white))
      assert.ok(colors.includes(ROBOT_PALETTE.green))
      assert.equal(colors.filter((color) => color === ROBOT_PALETTE.tyre).length, 4)
      assert.ok(colors.includes(0xdc2626))
    }
    robot.userData.animate(1, 0.3, true)
  })
}
