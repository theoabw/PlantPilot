# Demo video: script and shot list

The submitted film: 2 minutes 48 seconds, 2560x1440, English narration with burned-in captions. Every shot is a screen recording of the running app on the supplied capture; the only graphics are the title and end cards. The target is P-005.

## How it was recorded

- The app was built from `main` and served locally (`make demo`), then driven by a scripted browser at 1920x1080 so every take is reproducible. The diagnosis close-up was recorded at 2x pixel density so the card stays legible when zoomed.
- `?sharp=1` keeps full resolution while the camera moves (see the README). Without it the viewer lowers the moving resolution on slow frames.
- The robot moves at its real speed. Cuts happen between beats, never inside the P-005 drive.
- The cursor is a drawn overlay, because the screen capture does not include the system pointer.

## Script

| # | Narration | On screen |
| --- | --- | --- |
| Title | (metal pipe clang) | The PlantPilot mark draws on and its arrow drops in on the clang. "From scan to service." |
| 1 | Hear that? Somewhere in this plant, something just failed. The work order names the machine, but not where it is. We built PlantPilot to find it. | The room capture, orbiting. |
| 2 | This is a real 3D scan. But a scan is blind: it can't tell a pump from a pipe, or a wall from the floor. So PlantPilot works it out. Floors and walls peel away, read from each splat's own surface direction, and what's left becomes 150 separate objects, each in its own 3D frame. | Objects tinted; Objects isolated with Explode; the occupancy grid on the floor. |
| 3 | Eight key pieces of equipment are confirmed with SAM 3, across camera views. Click one, and it lights up inside the scan. Or strip the room away, and keep only the equipment. | The washing machine is selected and its card opens with the SAM 3 check; Only splats in equipment boxes. |
| 4 | Valmet's synthetic maintenance pack gave us thirty assets, and not a single position. So PlantPilot places every one on a matching object itself, and flags the faulty one: P-005, a process pump showing fouling. | Synthetic pack frames; the P-005 card with "procedural, not verified". |
| 5 | From above, this is what the robot plans on. Four obstacle layers: equipment, walls, overhead pipes, and floor the scan never saw. A* finds a collision-free path, sized to each robot's body. | Top down with Occupancy; the Compact AMR drives across the room. |
| 6 | A humanoid is taller, so low pipes count as obstacles, and it plans a route of its own. Every piece of equipment it passes lights up. | The Humanoid walks to the blue vertical vessel; nearby equipment highlights. |
| 7 | Swap in the compact AMR. Switch the view mid-drive: height, normals, photo, and it keeps going. Then hand it the work order. It replans from wherever it stands. | Character swap; Height, Normals and Photo while driving; Send robot to P-005 from the far side of the room. |
| 8 | But in a plant, a black-box answer isn't good enough. On arrival: fouling. Flow dropped 14% while speed and pressure held steady, so a sensor fault, or a blocked suction line, is less likely. Next safe step: inspect the hydraulic path, after lockout. | Arrival; the diagnosis card, with a slow zoom over the reasoning, the alternative causes and the next check. |
| 9 | Every claim is cited. It's not guessing: every sentence traces back to a record. | The citation chips and "5 claims, 5 cited, 0 unsupported". |
| 10 | And if you'd rather drive yourself, you can. Crouch, and step into first person. | Manual control as the Humanoid; crouch; First person. |
| 11 | Under the hood, it's a modular Python pipeline. The whole room rebuilds from the raw scan in under a minute, and runs fully offline. | The room capture. |
| 12 | Something in this room broke. Now we know which machine, where it is, and why. PlantPilot. From scan to service. | Top down; the logo resolves. End card disclosures. |

## Why the mission has two legs

The room's start position is about 0.2 m from P-005, so a direct send is a very short drive. The film sends the AMR to the far equipment cluster first and then to P-005, using the app's own behaviour of planning from wherever the robot stands.

## What the film states as simulated

On screen and in the narration: the maintenance pack is synthetic, the placement of pack records is proposed, the diagnosis is computed from the supplied pack rather than measured, and the robot is a viewer character. The end card repeats these and adds that scene units are treated as metres.

## Audio and credits

- Narration: synthesised voice (ElevenLabs), disclosed on the end card.
- Music: "Rising Arpeggio", generated with Suno.
- Sound effect: a metal pipe clang on the title card, mixed to speaking level.
