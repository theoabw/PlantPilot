import { SplatEdit, SplatEditRgbaBlendMode, SplatEditSdf, SplatEditSdfType } from '@sparkjsdev/spark'
import * as THREE from 'three'
import type { RoomObject } from './api'

/**
 * Tint the splats inside one reviewed box so a selection shows the surface the
 * box is masking rather than only the box.
 *
 * The edit lives in the splat mesh's local space, which is the capture's scene
 * frame, so the box is placed with the same centre, axis basis and extents the
 * frames are drawn with. The colour is added, so the object keeps its own
 * shading and gains a cyan glow instead of turning into a flat silhouette.
 *
 * ADD_RGBA adds the edit's opacity to each splat's alpha as well, and a summed
 * alpha over 1 grows the splat and makes it opaque. The opacity stays 0 so that
 * faint fog keeps its alpha and does not turn into solid blobs that also start
 * writing to the depth pass.
 */
export function selectionSplatEdit(object: RoomObject): SplatEdit {
  const edit = new SplatEdit({ rgbaBlendMode: SplatEditRgbaBlendMode.ADD_RGBA })
  const box = new SplatEditSdf({
    type: SplatEditSdfType.BOX,
    opacity: 0,
    color: new THREE.Color(0.10, 0.55, 0.80),
  })
  box.position.set(...object.centre)
  const axes = object.axes.map((axis) => new THREE.Vector3(...axis).normalize())
  box.quaternion.setFromRotationMatrix(
    new THREE.Matrix4().makeBasis(axes[0], axes[1], axes[2]),
  )
  box.scale.set(...object.extents).multiplyScalar(0.5)
  edit.add(box)
  return edit
}
