# Acceptance

What has to be true, not what we hope is true. Two parts: the rules we do not negotiate, and one checkable criterion per beat of the demo.

## The constitution

1. **The demo is offline.** No request leaves the machine on the demo path. If a feature needs the network, it is not in the demo.
2. **No number without a command.** Every figure on screen or in the README comes from the app or from `make proof`, never typed by hand.
3. **Say what is simulated.** The geometry source is on screen, the plates are marked SYNTHETIC DEMO ASSET, and the README names what is mocked in its first paragraph.
4. **The waypoint is beside the machine.** Never a machine centre, and it must resolve to a walkable cell or the answer is "blocked", not a nearby guess.
5. **P0 never gets cut.** If a P0 is late, the demo changes shape around it. A P1 that misses its gate becomes P2 automatically.
6. **One demo path.** A second screen, a second idea or a second dataset waits until the first path runs three times clean.
7. **The repo runs from a clean clone at all times.** `make test` and `make demo` green before a push.
8. **No secrets, no restricted data, no media in git.** `data/` is local, `fixtures/` is small text, keys live in `.env`.
9. **The product is not the pitch.** The interface shows what an operator needs and nothing that exists to impress a judge. Point counts, response times, "offline" stamps, judge buttons and demo scripts belong in the pitch, the video and the README. The one exception is provenance: which dataset is loaded is a fact an operator needs, so it appears once, quietly.

## The six beats

Each criterion is written so a person who did not build the feature can check it.

### 1. The scan is on screen and unlabelled

**Given** the app is open with the reference plant loaded,
**when** the cloud finishes loading,
**then** the view reports the point count and the geometry source, and shows no labels until a selection happens.

**Pass:** point count above 100,000, source label visible, first frame under 5 seconds on the demo laptop.
**Check:** open the app with the API running; the panel shows the count and the source.

### 2. An asset is identified, with evidence

**Given** a printed tag in front of the camera,
**when** it is scanned,
**then** the field resolver returns type, DN, PN, body and serial, the asset match returns the tag on the plate, and the card states whether the identity is a proposal or confirmed.

**Given** a frame whose characters are under 20 px,
**when** it is scanned,
**then** the gate refuses it, reports the measured pixel height, and returns no asset.

**Pass:** the tag on the plate and the matched asset id are the same; the refusal message contains the measured height.
**Check:** `uv run pytest app/server/tests/test_ocr.py app/server/tests/test_api.py`.

### 3. An inspection request becomes a route

**Given** an inspection request derived from last service plus the service interval,
**when** the asset is selected,
**then** a route to that asset's waypoint is returned with a distance in metres and a clearance in metres, and the waypoint is a walkable cell.

**Pass:** reachable true, distance greater than 0.5 m, clearance greater than 0.3 m, response under 300 ms on the demo laptop.
**Check:** `POST /api/route {"to":"P-204"}`.

### 4. Blocking an aisle changes the answer

**Given** the clear route to V-203 is known,
**when** the west aisle is closed,
**then** a route still exists, it is at least 4 m longer than the clear route, and the panel shows the new distance.

**Given** a blocker that seals the hall,
**when** the route is requested,
**then** no route is returned, and the answer carries a reason, not a crash and not a partial path.

**Pass:** the detour is visibly longer, and the sealed case returns `reachable: false` with a reason.
**Check:** `POST /api/route {"to":"V-203"}` and the same with `blockers: [[0,4.8,4.6,7.2]]`, then with `[[0,1.5,16,2.2]]`.

### 5. The reason is cited

**Given** a selected asset,
**when** the evidence panel opens,
**then** it shows a manual section id, the page number for that section, a quote, and the service interval and source from the register and VMR003.

**Pass:** the section id and page returned by the app match the corpus index; no card appears without a citation.
**Check:** `GET /api/section/{id}` and `uv run pytest app/server/tests/test_corpus.py`.

### 6. It generalises when a judge picks

**Given** the demo is running and three destinations are prepared,
**when** a judge names one of them,
**then** the route is computed for that asset, with the same distance, clearance and timing guarantees as beat 3.

**Pass:** every prepared destination reaches the same three numbers within 300 ms, and none of them needs a code change or a re-run of the app.
**Check:** `POST /api/route` for each prepared asset id.

## Release checks

| Check | Command | Pass |
| --- | --- | --- |
| Tests | `make test` | all pass |
| Web build | `cd app/web && npm run build` | exit 0 |
| Offline demo | disable the network, open the app, run beats 1 to 5 | no error, no spinner that never ends |
| Clean clone | fresh clone, `uv sync`, `make plant`, `make demo` | the app opens |
| Submission hygiene | `make check` | ready, or the remaining failure named |
| Honesty | read the README and the video script | every simulated element is called simulated |

## What would fail the demo

- A number on screen that no command produced.
- A route that ends inside a machine.
- A refused frame that returns an asset anyway.
- A citation that does not match the corpus.
- Any request to the network during a live run.
- A geometry source that is not named on screen.

## Current measurements

Values change as the data changes, so they live here and not in the criteria.

| Measure | Value | Where it came from |
| --- | --- | --- |
| Reference plant points | 141,575 | `GET /api/cloud/meta` |
| P-204 route | 11.11 m, 0.85 m clearance | `POST /api/route` |
| V-203 clear route | 14.65 m | `POST /api/route` |
| V-203 with the west aisle closed | 21.25 m, +6.6 m | `POST /api/route` with the blocker |
| Route response | 46 ms | app panel, after the cloud loads |
| Tests | 23 | `make test` |
