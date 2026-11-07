import { SplatEdit, SplatEditSdf, SplatEditSdfType } from '@sparkjsdev/spark'
import * as THREE from 'three'
import type { RoomObject } from './api'

/** Hide splats outside the union of the reviewed oriented equipment boxes. */
export function boxSplatFilter(objects: RoomObject[]): SplatEdit {
  const edit = new SplatEdit({ invert: true })
  for (const object of objects) {
    const box = new SplatEditSdf({ type: SplatEditSdfType.BOX, opacity: 0 })
    box.position.set(...object.centre)
    const axes = object.axes.map((axis) => new THREE.Vector3(...axis).normalize())
    box.quaternion.setFromRotationMatrix(new THREE.Matrix4().makeBasis(axes[0], axes[1], axes[2]))
    box.scale.set(...object.extents).multiplyScalar(0.5)
    edit.add(box)
  }
  return edit
}
