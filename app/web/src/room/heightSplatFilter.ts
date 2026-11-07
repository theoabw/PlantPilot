import { SplatEdit, SplatEditSdf, SplatEditSdfType } from '@sparkjsdev/spark'
import * as THREE from 'three'

/** Hide splat centres above a height measured along the capture's up axis. */
export function heightSplatFilter(upAxis: [number, number, number], floorHeight: number, height: number): SplatEdit {
  const up = new THREE.Vector3(...upAxis).normalize()
  const edit = new SplatEdit({ invert: true })
  edit.ordering = Number.MAX_SAFE_INTEGER
  const plane = new SplatEditSdf({ type: SplatEditSdfType.PLANE, opacity: 0 })
  plane.position.copy(up).multiplyScalar(floorHeight + height)
  plane.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), up)
  edit.add(plane)
  return edit
}
