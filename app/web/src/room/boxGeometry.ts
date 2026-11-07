import * as THREE from 'three'

/** A box is unchanged when one of its axes is reversed. */
export function boxQuaternion(axes: number[][]): THREE.Quaternion {
  const x = new THREE.Vector3(axes[0][0], axes[0][1], axes[0][2]).normalize()
  const y = new THREE.Vector3(axes[1][0], axes[1][1], axes[1][2]).normalize()
  const z = new THREE.Vector3(axes[2][0], axes[2][1], axes[2][2]).normalize()
  if (new THREE.Vector3().crossVectors(x, y).dot(z) < 0) {
    z.negate()
  }
  return new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().makeBasis(x, y, z)).normalize()
}
