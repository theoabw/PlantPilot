import * as THREE from 'three'

/** Follow exactly the straight segments checked by the route planner. */
export function routeCurve(points: THREE.Vector3[]): THREE.CurvePath<THREE.Vector3> {
  const curve = new THREE.CurvePath<THREE.Vector3>()
  for (let index = 1; index < points.length; index += 1) {
    curve.add(new THREE.LineCurve3(points[index - 1], points[index]))
  }
  return curve
}
