import * as THREE from 'three'
import type { RoomObject } from './api'

/** Frame the central equipment bounds from above in the viewer's upright space. */
export function topDownPose(objects: RoomObject[], upright: THREE.Quaternion, fov: number, aspect: number) {
  if (objects.length === 0) {
    throw new Error('Top-down view needs object bounds')
  }
  const mins: THREE.Vector3[] = []
  const maxs: THREE.Vector3[] = []
  for (const object of objects) {
    const centre = new THREE.Vector3(...object.centre).applyQuaternion(upright)
    const half = new THREE.Vector3()
    object.axes.forEach((axis, index) => {
      const direction = new THREE.Vector3(...axis).normalize().applyQuaternion(upright)
      half.x += Math.abs(direction.x) * object.extents[index] / 2
      half.y += Math.abs(direction.y) * object.extents[index] / 2
      half.z += Math.abs(direction.z) * object.extents[index] / 2
    })
    mins.push(centre.clone().sub(half))
    maxs.push(centre.clone().add(half))
  }
  const percentile = (values: number[], fraction: number) => {
    values.sort((a, b) => a - b)
    return values[Math.round((values.length - 1) * fraction)]
  }
  const lows = [0, 1, 2].map((axis) => percentile(mins.map((v) => v.getComponent(axis)), 0.05))
  const highs = [0, 1, 2].map((axis) => percentile(maxs.map((v) => v.getComponent(axis)), 0.95))
  const low = new THREE.Vector3(lows[0], lows[1], lows[2])
  const high = new THREE.Vector3(highs[0], highs[1], highs[2])
  const target = low.clone().add(high).multiplyScalar(0.5)
  const halfHeight = Math.max((high.z - low.z) / 2, (high.x - low.x) / (2 * Math.max(aspect, 0.01)))
  const distance = Math.max(1, halfHeight / Math.tan(THREE.MathUtils.degToRad(fov) / 2) * 1.15)
  return { target, eye: new THREE.Vector3(target.x, high.y + distance, target.z + 0.001) }
}
