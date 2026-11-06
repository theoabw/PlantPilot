# How we work in this repo

Four people, 26 hours. The rules here are short because the cost of breaking them is a lost night.

## Everything through a pull request

- `main` is the review surface. Nobody pushes to it directly, including the lead.
- Branch per change: `bootstrap/...`, `feat/...`, `fix/...`, `proof/...`.
- Open the PR when the branch first runs, not when it is finished. A draft PR is the right shape for work in progress; GitHub will not merge a draft.
- A PR is merged only by the lead, after review, and only when its checks are green. No automerge.

## One writer per file

Two agents or two people editing the same file silently overwrite each other. On Thursday that happened three times in one hour. If two workstreams need one file, order them and hand over.

## What a PR must show

- `make test` green.
- `make check` green, or the remaining failure named in the PR body (the submission checker will complain about missing links until Sunday).
- `npm run build` in `app/web` green, if the front end changed.
- The demo path still works: `make demo` then open `http://127.0.0.1:8000`.

## Review in five minutes

1. Does it change the demo path? If yes, does the PR body say what a judge now sees differently?
2. Does it add a dependency, a key or a network call? Those need a reason in the PR body.
3. Does it ship a number without `proof/metrics.json` behind it? Reject.
4. Does it ship data into git? `data/` and `*.onnx` are ignored; `fixtures/` is for small text only, under 256 KB.

## Ownership

| Seat | Owns |
| --- | --- |
| A | capture, gate, OCR, field resolver |
| B | corpus, retrieval, then the proof harness and the numbers |
| C | UI, the five states, the on-screen copy |
| D | merges, demo driver, video, README, submission |

Interfaces freeze at H+2 (the API contract in the build plan). After that, a contract change is a PR that says which side changed and why.
