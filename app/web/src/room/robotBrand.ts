import * as THREE from 'three'

export const ROBOT_PALETTE = {
  green: 0x008f3c,
  white: 0xf2f4f1,
  lightGrey: 0xc6ceca,
  darkGrey: 0x343b39,
  hiVis: 0xd4f22a,
  hardHat: 0xf5c518,
  tyre: 0x171b1a,
} as const

/** The supplied logo has a white background and a 2149:768 aspect ratio. */
export function robotLogo(texture: THREE.Texture, width: number): THREE.Mesh {
  const badge = new THREE.Mesh(
    new THREE.PlaneGeometry(width, width * 768 / 2149),
    new THREE.MeshBasicMaterial({ map: texture, color: 0xffffff, transparent: true }),
  )
  badge.renderOrder = 4
  badge.userData.noGhost = true
  return badge
}
