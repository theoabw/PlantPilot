# Demo frontend changelog

Changes to the scene lab demo frontend, tracked against
[`Feedback.md`](Feedback.md).

## 2026-11-06 - The real capture

Branch: `feat/spark-room`

### Features

- **The room is the supplied capture.** The default view now renders the actual
  gaussian splat with Spark inside the existing three.js scene, so the room and
  the 130 extracted boxes share one camera and depth order. Clicking a box opens
  its class proposal, confidence and size; the scene lab stays available from
  the info tab as the provisional room.
- The camera opens at standing height inside the room, from a stand position
  chosen for clearance, and the capture's own up axis decides which way is up.
- The up axis detection now signs the axis from the two slabs of a room: the
  floor is the brighter one, so the pipes end up overhead instead of under the
  floor. Both supplied captures are y-down 3DGS frames.

### Robot on the capture

- The robot now drives the real room: `GET /api/scene/route` serves the route
  from `make route`, the room view draws it on the floor, and Send robot runs the
  robot along it with a follow camera and a live distance and clearance readout.
  While it drives, unmapped object frames drop back so the route and the mapped
  asset stay readable.
- The camera opens at the hero view the extraction records, so the browser and
  the rendered stills share one viewpoint.

### Verification

- `pnpm typecheck`, `pnpm build`, `uv run pytest` and `node scripts/sinceai_check.mjs`.
- Loaded in Chromium against `GET /api/splat` and `GET /api/scene/objects`;
  screenshot in the pull request.

## 2026-11-06 - Feedback round 1

Branch: `feat/web-demo-ui`

### Fixes

- **View controls are now scene controls.** Overview, Follow, Reset and the
  Mission panel toggle moved out of the side panel and onto a labelled toolbar
  attached to the 3D scene. The active Follow and panel states are visible, and
  the toolbar shifts left on desktop when the drawer opens so it stays usable.
- **The scene is full width by default.** The task, target and machine list are
  collapsed into a drawer that opens from the toolbar or by clicking a machine
  in the scene. The drawer uses a dark, scene-matched style with Mission and
  Machines tabs.
- **Narrow screens get a bottom sheet.** The same drawer becomes a rounded
  bottom sheet below the `lg` breakpoint, with a close button and Escape to
  dismiss.
- **Sending the robot clears the scene.** Send robot and Fault demo close the
  drawer and turn on the follow camera, so the route is visible while the robot
  moves.
- **Narrow screens get more room.** The header subtitle collapses, the compact
  view toolbar uses icons only, and the camera widens its field of view below the
  `lg` breakpoint so the room is not cropped as tightly.

### Robot on the capture

- The robot now drives the real room: `GET /api/scene/route` serves the route
  from `make route`, the room view draws it on the floor, and Send robot runs the
  robot along it with a follow camera and a live distance and clearance readout.
  While it drives, unmapped object frames drop back so the route and the mapped
  asset stay readable.
- The camera opens at the hero view the extraction records, so the browser and
  the rendered stills share one viewpoint.

### Verification

- `pnpm typecheck`
- `pnpm build`
- Exercised in headless Chromium at 1440x900: open panel, select an asset, run
  the fault demo, confirm the robot arrives at P-005 with the drawer closed.

## 2026-11-06 - Feedback round 2

Branch: `feat/web-demo-ui`

### Fixes

- **Raleway is now the UI font.** The normal and italic variable fonts are
  bundled under `app/web/public/fonts` with the SIL OFL licence, so the demo
  keeps the typeface offline. The Tailwind sans stack falls back to system
  fonts if the files are unavailable.
- **The main header and demo switcher are gone from the scene.** The scene view
  fills the viewport with no top chrome. Brand, offline state and workspace
  links live in the new Info tab of the mission panel.
- **Legacy views keep a compact bar.** Plant mission and plate scan use a slim
  workspace bar with a back link to the scene lab, instead of the old PlantPilot
  header and tab row.
- **The Makefile uses pnpm.** `make web` and `make web-build` now call `pnpm run`
  instead of `npm run`.

### Robot on the capture

- The robot now drives the real room: `GET /api/scene/route` serves the route
  from `make route`, the room view draws it on the floor, and Send robot runs the
  robot along it with a follow camera and a live distance and clearance readout.
  While it drives, unmapped object frames drop back so the route and the mapped
  asset stay readable.
- The camera opens at the hero view the extraction records, so the browser and
  the rendered stills share one viewpoint.

### Verification

- `pnpm typecheck`
- `make web-build`
- Headless Chromium at 1440x900 and 390x844: no header or tab row in the scene,
  Raleway reported by the computed body font, Info tab exposes Plant mission and
  Plate scan, navigation and the back link both work.
