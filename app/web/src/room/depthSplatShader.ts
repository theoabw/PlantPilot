/**
 * The depth pass draws every second splat, because it is fill bound like the
 * colour pass. The choice has to follow the splat, not its place in the draw:
 * gl_InstanceID is the sort rank, so one rank shift flips the parity of every
 * splat after it, and the depth surface would change whenever the camera moved
 * enough to re-sort. splatIndex is the splat's own id. gl_Position already holds
 * an off-screen value at this point in Spark's shader, so returning discards it.
 */
const SPLAT_LOOKUP = 'ivec3 texCoord = splatTexCoord(int(splatIndex));'

export function stableHalfDepthShader(vertexShader: string): string | null {
  if (!vertexShader.includes(SPLAT_LOOKUP)) {
    return null
  }
  return vertexShader.replace(
    SPLAT_LOOKUP,
    `if ((splatIndex & 1u) == 1u) {\n        return;\n    }\n\n    ${SPLAT_LOOKUP}`,
  )
}
