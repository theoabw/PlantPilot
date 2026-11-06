# Roadmap, Friday 16:40 to Sunday 10:00

The plan is in [plantpilot-plan.md](plantpilot-plan.md). This page is the execution order: what exists, what gets built when, and what has to be true at each gate before the next thing starts.

## Where we are

| Piece | State | Verified by |
| --- | --- | --- |
| Corpus from the real manual | 57 numbered sections, FTS5 index, page anchors | `make corpus`, 14 tests |
| OCR and field resolver | plate to type, DN, PN, body, serial | `uv run pytest` |
| Asset register | 48 rows, CMMS shaped | `make register` |
| Photo capture | depth, guided filter, ArUco scale, cloud | `make scan PHOTO=...`, 3.2 s per photo |
| Reference plant | 10 assets, 141k points, ground truth, preview | `make plant` |
| Plates and scale card | 16 tags with ArUco, true scale card | `make plates` |
| Viewer shell | five states, camera and upload, sample path | `npm run build`, screenshot |
| Repository | one branch, one commit history, CI green | `make check` |

Not built yet: the mission layer. No asset store with positions, no route, no blockage, no evidence panel wired to the viewer.

## The weekend at a glance

| Phase | Window | Goal | Hard output |
| --- | --- | --- | --- |
| Prep | now to 18:45 | print tags and scale card, measure the card, test the laptop camera, settle the data question | a photographed area or the reference plant loaded |
| Brief | 18:50 to 19:30 | the company's criteria, in their words, plus the dataset answer | criteria and data branch written down |
| M0 | 19:50 to 22:30 | cloud, assets and viewer in one page | the scan on screen from the real API |
| M1 | 22:30 to 02:00 | five confirmed assets, a route to each, fly-to | gate G1 |
| Night | 02:00 to 02:40 | commit, clean clone, capture a raw run | a state the morning can trust |
| Sleep | 02:45 to 07:45 | nobody on call, no half-merges | clean clone still runs |
| M2 | 08:30 to 12:30 | blockage, reroute, evidence panel, follow the route | gates G2 and G3 |
| M3 | 12:30 to 16:00 | numbers, evaluation, three clean runs, script locked | gate G4 |
| Video | 16:00 to 19:30 | screen recording, voice, render, upload to YouTube unlisted, README, submission text | the video is live on YouTube and the link works |
| Buffer | 19:30 to 22:00 | fix what the demo exposes, final runs | features frozen |
| Submit | Sunday 07:00 to 09:30 | entry saved, links checked logged out, YouTube link pasted, IP terms accepted by every member | submitted before 10:00 |

## Gates

| Gate | Time | Must be true | If it fails |
| --- | --- | --- | --- |
| G0 | 19:50 | data branch chosen, one area loads, WebGL confirmed on the demo laptop | choose the fallback renderer now, not at midnight |
| G1 | 02:00 | five assets confirmed with waypoints, a route to each from the door, the camera flies to the selected asset | ship the mission without fly-to, keep the route list |
| G2 | 12:30 | a blocked aisle reroutes or reports unreachable, with the reason; the evidence panel cites the manual | drop the follow camera and the judge-chosen destination, keep the blockade |
| G3 | 12:30 | the 120 second sequence runs three times in a row offline | rehearse only the five beats that work, cut the sixth |
| G4 | 16:00 | the numbers in the claims table are measured and on screen | print the two strongest and label the rest as future work |
| Freeze | 22:00 | no code changes after this | only README, video, submission text |

## Lanes

| Seat | Until 22:30 | Until 02:00 | Saturday morning |
| --- | --- | --- | --- |
| A | serve the cloud and the asset spec over the API | plate to asset identity, five assets confirmed | semantic proposals against the reference truth, recall number |
| B | floor polygon and occupancy grid from the cloud or spec | A* to five waypoints, response times | blocker insertion, reroute, clearance, unreachable case |
| C | viewer loads the cloud, orbit, select | highlight, asset card, fly-to camera | blockage interaction, evidence panel, six states |
| D | asset store schema, coordinates frozen, integration | plumb order to asset end to end | evaluation harness, numbers, video script |

The asset record and the coordinate convention are frozen at 19:50. After that a contract change is a commit that says which side changed and why.

## The demo, as a checklist

| Beat | Must show | Owner |
| --- | --- | --- |
| 1 | scan on screen, unlabelled, rotating | C |
| 2 | equipment highlights, select P-204, evidence visible | A, C |
| 3 | pick the inspection request, route appears with distance and clearance | B, D |
| 4 | click a blocker, route recomputes, longer or unreachable with a reason | B |
| 5 | follow to the waypoint, reason panel cites section, page and interval | D |
| 6 | a judge picks one of three prepared destinations | C, D |

## Numbers we must be able to print

- Capture: points, seconds per photo, scale error against a ruler on the card.
- Semantics: class and instance recall against the reference plant truth.
- Mission: assets with waypoints, routes found, response time in ms, clearance in cm.
- Blockage: reroutes succeeded, added distance, unreachable verdicts with reason.
- Preparation: objects confirmed by hand, metres of floor drawn by hand, documents attached by hand.

Every one of these comes from a command or from the app, not from a slide.

## Risks and triggers

| Risk | Trigger | Response |
| --- | --- | --- |
| No industrial environment | venue rooms are halls and chairs | load the reference plant, label it synthetic, keep the photo path as the second mode |
| Depth quality | walls and glass are blobby | use the reference plant for the mission, photos for the capture proof |
| WebGL on the laptop | G0 fails | canvas 2D projection, then isometric SVG |
| Semantics too vague | CLIP labels contradict geometry | cut CLIP, ship geometry plus tags, say so |
| Time | G1 slips past 01:00 | cut the fly-to and the follow camera, keep route and blockage |
| Half-merged state overnight | last commit does not run | fix before sleeping or revert; nothing is left for the morning |

## Saturday night, in order

1. Freeze features at 22:00. The repository is the deliverable from here.
2. Write the 90 second script with two number placeholders, then fill them from the app.
3. Record the screen at real speed, no mockups: the scan, the selection, the route, the blockage, the citation.
4. Synthesise the voice and attach it as an audio track in the video project.
5. Re-cut the video after any late fix rather than after midnight.
6. README numbers, limitations, and the submission text before the video render finishes.
7. Upload the cut to YouTube as unlisted and paste that link into the submission. There are no video file uploads; YouTube is the only accepted format.

## Sunday

| Time | Action |
| --- | --- |
| 07:00 | wake, clean clone, `make test`, `make check`, `make demo` |
| 07:30 | submission entry saved: name, tagline, About under 5,000 characters, Built with (first five become chips), repo link, YouTube link |
| 08:00 | repo and YouTube link open logged out, deck uploaded only if it earns its place |
| 09:00 | every member has accepted the IP terms |
| 09:30 | done, with 30 minutes of slack |
| 10:00 | deadline, vote window opens |
| 12:00 | if finalist, rehearse the four minute pitch |

## What we are not doing

Robot simulation, predictive maintenance, pipe connectivity, whole plant understanding, multi-room twins, VR, LiDAR capture, a login, a cloud service, an LLM on the answer path.

## Open decisions at 19:30

1. Data branch: supplied scan, venue photos, or the reference plant.
2. Which machines are the five confirmed assets, and which one is P-204 for the demo.
3. Who sits in each of the four seats, by name.
4. The blocker location, chosen so the reroute is visibly longer rather than barely different.
