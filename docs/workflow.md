# How we work in this repo

Four people, 26 hours. `main` is the only branch.

## Commits

- Small steps, meaningful messages. Every commit is event work and the judges read the log.
- `make test` green before a push. `make check` green, or the remaining failure named in the message.
- One writer per file. Two agents on one file silently overwrite each other; it happened three times in one hour on Thursday.

## Before a push, five minutes

1. Does it change the demo path? Say what a judge now sees differently.
2. Does it add a dependency, a key or a network call? Say why in the message.
3. Does it ship a number without `proof/metrics.json` behind it? Do not.
4. Does it put data in git? `fixtures/` is small text only, under 256 KB; `data/` is ignored.

## Ownership

| Seat | Owns |
| --- | --- |
| A | ingest, depth or import, segmentation proposals, plate identity |
| B | floor, occupancy grid, A*, obstruction and reroute, waypoints |
| C | viewer, selection, highlights, camera, the mission UI |
| D | integration, asset store, evidence panel, evaluation, video, submission |

The asset format and the coordinate convention are frozen at 19:30. After that, a contract change is a commit that says which side changed and why.
