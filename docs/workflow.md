# How we work in this repo

Up to five people, from Friday evening to the Sunday 10:00 deadline. `main` is the release branch.

## Branches and pull requests

- Short-lived branches, one concern each, merged into `main` through a PR. The plan direction arrived as `plan-scene-agnostic`.
- The PR description says what a judge sees differently and what the change does not include.
- No force pushes and no amends to pushed commits. A fix after review is a new commit.

## Commits

- Small steps, meaningful messages. Every commit is event work and the judges read the log.
- `make test` green before a push. `make check` green, or the remaining failure named in the message.
- One writer per file. Two agents on one file silently overwrite each other; it happened three times in one hour on Thursday.

## Before a push, five minutes

1. Does it change the demo path? Say what a judge now sees differently.
2. Does it add a dependency, a key or a network call? Say why in the message.
3. Does it ship a number without a command behind it? Do not.
4. Does it add a constant from this room (bounds, floor height, point count, asset position) to a scene-agnostic stage? Do not.
5. Does it put data in git? `fixtures/` is small text only, under 256 KB; `data/` is ignored.

## Ownership

| Seat | Owns |
| --- | --- |
| A | ingest, segmentation, objects, the scene-agnostic CLI |
| B | floor, occupancy grid, A*, waypoints, proximity queries |
| C | viewer, selection, highlights, avatar, camera, panels |
| D | pack, mapping, diagnosis, evidence, integration, evaluation harness, video, submission |

The contracts (scene frame, artifact names, module boundaries) are frozen at 21:00 Friday. After that a contract change is a commit that says which side changed and why. Features freeze Saturday 22:00.
