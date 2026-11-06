# Demo frontend changelog

Changes to the scene lab demo frontend, tracked against
[`Feedback.md`](Feedback.md).

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

### Verification

- `pnpm typecheck`
- `pnpm build`
- Exercised in headless Chromium at 1440x900: open panel, select an asset, run
  the fault demo, confirm the robot arrives at P-005 with the drawer closed.
