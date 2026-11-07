import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import test from 'node:test'
import ts from 'typescript'

const source = await readFile(new URL('../src/room/depthSplatShader.ts', import.meta.url), 'utf8')
const js = ts.transpile(source, { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 })
const { stableHalfDepthShader } = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)

// Spark does not export its shader, so read the embedded GLSL from the package.
const sparkPath = fileURLToPath(import.meta.resolve('@sparkjsdev/spark'))
const sparkSource = await readFile(sparkPath, 'utf8')
const embedded = sparkSource.match(/var splatVertex_default = ("(?:[^"\\]|\\.)*")/)
assert.ok(embedded, 'the Spark vertex shader moved')
const vertexShader = JSON.parse(embedded[1])

test('the depth subset is chosen by splat id, after the id is read', () => {
  const edited = stableHalfDepthShader(vertexShader)
  assert.ok(edited, 'the Spark shader no longer has the splat lookup')
  assert.ok(!edited.includes('mod(float(gl_InstanceID)'))
  const lookup = edited.indexOf('uint splatIndex = texelFetch(ordering')
  const skip = edited.indexOf('if ((splatIndex & 1u) == 1u)')
  const read = edited.indexOf('ivec3 texCoord = splatTexCoord(int(splatIndex));')
  assert.ok(lookup >= 0 && lookup < skip && skip < read)
  // Spark sets the off-screen position first, so the early return discards it.
  assert.ok(edited.indexOf('gl_Position = vec4(0.0, 0.0, 2.0, 1.0);') < skip)
})

test('a shader without the lookup is reported instead of drawn wrongly', () => {
  assert.equal(stableHalfDepthShader('void main() {}'), null)
})
