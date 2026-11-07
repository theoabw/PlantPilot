import { SplatEdit, SplatEditSdf, SplatEditSdfType } from '@sparkjsdev/spark'
import type { RoomObject } from './api'
import { boxQuaternion } from './boxGeometry'

/** Hide splats outside the union of the reviewed oriented equipment boxes. */
export function boxSplatFilter(objects: RoomObject[]): SplatEdit {
  const edit = new SplatEdit({ invert: true })
  for (const object of objects) {
    const box = new SplatEditSdf({ type: SplatEditSdfType.BOX, opacity: 0 })
    box.position.set(...object.centre)
    box.quaternion.copy(boxQuaternion(object.axes))
    box.scale.set(...object.extents).multiplyScalar(0.5)
    edit.add(box)
  }
  return edit
}
