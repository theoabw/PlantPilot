# Challenge card

Fill this card when the summaries open on Thursday 5 November at 15:00, finalize it at the Friday briefing, and keep it current. It is the shared source of truth for what we build, what the company says it will score, and what we will not build.

## Shortlist (Thursday 5 Nov)

Revised Thursday evening. Three the team would accept, in the ranking we take into Friday's first-come selection.

Decision rule: the Friday brief supports the direction, a working demo is possible in one night, the result is measurable rather than asserted, and the story is clear in 20 seconds to a non-expert voter.

| # | Company | Challenge | Why we would accept | Risk |
| --- | --- | --- | --- | --- |
| 1 | Valmet | Connecting the physical and digital worlds at industrial sites | Best visual storytelling: physical-world AI, interactive machinery, troubleshooting a real site. | Needs a machinery model or real asset, or the demo collapses into a dashboard. Do not build a digital twin. |
| 2 | Traficom | Radio-frequency interference and spectrum planning | Signal processing and simulation: inject interference, show it in a spectrogram, train a model to detect or mitigate it. Measurable result, striking visual, a real model. | The brief may centre on planning and regulation rather than detection. If it does, pivot to interference-risk scoring for a proposed link. Needs a 20 second voter story. |
| 3 | Business Turku | Adding intelligence to existing industrial machinery | Synthetic sensor data, anomaly detection, live machinery dashboard. Fastest route to a working demo. | Generic predictive maintenance, the least differentiated of the three for the vote. |

Lean: Traficom first, because it can satisfy both gates: a measurable technical result for the company, and a visible "jammer against detector" story for the vote. Valmet is the safer visual story, Business Turku the safest build. The order is a preference, not a lock; the final call is the lead's at selection.

If all three briefs disappoint, the vote-friendly fallbacks are DNA and Fonecta, recorded with the rest in [docs/challenge-summaries.md](docs/challenge-summaries.md).

FORCIT Group is the only challenge that needs a paper NDA signed on site at its Friday briefing (Drill and Blast Cycle Intelligence, €3,000 first prize). Its summary is deliberately content-free, so choosing it is choosing blind. Only put it on the shortlist if someone on the team owns industrial operations, geology or blasting experience.

Timing correction, Thursday evening: the brief cannot inform the choice. Selection closes Friday at 17:30, the company intros run 17:00 to 17:30, and the company briefing is 18:50 to 19:30, after the commitment. Anything in this card that reads like a kill criterion is therefore a scope decision taken at 19:30, not a switch to another company. Plans for all eight candidates named in chat, with a ranked call and a pre-build list, are in [docs/challenge-plans.md](docs/challenge-plans.md).

## Choice

Assumed selected on Friday afternoon. Fill the briefing lines at 18:50 and keep them verbatim.

- Company: Valmet
- Challenge title: Connecting the physical and digital worlds at industrial sites
- The task in the company's own words: "Imagine entering a digital industrial plant where the environment does more than look real. It understands where machines are, what they are, how people or robots could move between them and which equipment needs attention. Today's 3D captures can be visually extraordinary, but they often lack the meaning needed for intelligent action. Valmet challenges you to bridge that gap. Explore how spatial perception, semantic 3D understanding and AI-grounded equipment information could transform a scanned industrial environment into a navigable, useful digital world." The scored criteria are still to be written at the 18:50 briefing.
- Why this one (business value, data available, fit with the stack): a work order becomes a guided mission. The plant identifies the machine, explains why it needs attention, computes a route to its inspection position, and reroutes when an aisle is blocked. The scan can be supplied or captured with our depth pipeline; the asset register, the OCR tags and the manual corpus supply identity and evidence. The result is measurable (correct asset selection, routes found, blocked handling, response time, manual preparation) and the vote story is a blocked aisle that visibly changes the answer.
- Accepted by the whole team (names): TODO at check-in
- Selected in sinceai.app (time, by whom): TODO, before 17:30
- IP terms (who owns the work, any NDA): "Your team owns what you build. Valmet can use it in its business." No NDA in the public summary. Confirm at the briefing; FORCIT is the only challenge the event brief names an NDA for.
- Restricted data (what may not leave the room, where it lives): none known. If the briefing introduces any, it goes to the gitignored `restricted/` folder on one laptop and never into the repo, the video or the deck.

## What the company said they will score

Write the criteria in their words at the briefing, not a paraphrase.

1.
2.
3.

## The one demo path

What a judge sees in 90 seconds, step by step:

1. A scan of the area rotates, unlabelled. Click Understand: equipment highlights, and selecting P-204 shows its evidence, the tag and the operator confirmation.
2. Pick the inspection request: the machine lights up and a route appears from the start to the inspection position beside it, with distance and clearance.
3. Block an aisle with a click: the route vanishes and a new one appears around the obstruction, or the app says the destination is unreachable and why. Follow the route to the waypoint, then open the reason: the answer cites the manual section, page and VMR003 interval.

The moment that proves it works (output, number, before/after): the blocked aisle rerouting the mission, plus correct asset selection on 5 to 8 destinations, route response time, and how much was prepared by hand. Numbers come from `make proof` and are never typed by hand. Whether the scan is supplied or captured is printed on screen.

## What we are not building

- Photogrammetry, LiDAR capture, or a real facility scan; the scan is synthetic and labelled as synthetic.
- Physics simulation, robot control, VR or mobile AR. A marker walks the path and is not sold as a robot.
- A multi-room digital twin platform, a login, or any cloud service on the demo path.
- A dashboard that lists every asset; the camera is the only entry point.
- Work order creation, CMMS integration, login, roles, cloud deployment.
- A fine-tuned model, a vector database, or an LLM on the answer path.
- Invented spare part numbers: the ePartsbook boundary is shown, not faked.

## Data and privacy

- What data we use: photographs of the venue room, turned into a point cloud with monocular depth; a 48 row synthetic asset register with positions; two public Valmet PDFs (the Flow control manual and VMR003); 16 printed plates with ArUco markers; and a printed scale card.
- Where it comes from and where it goes: the PDFs are fetched by script into the gitignored `data/` folder and never committed; neither the PDFs nor the extracted text nor the photographs leave the laptop. The PDFs are all rights reserved, so only section numbers, titles and quotes of 1 to 3 lines ship.
- What is mocked: the asset register, the tag numbers, the service intervals, the plate text and the plant framing. The room and the photographs are real; the plant is a stand-in. Every plate carries SYNTHETIC DEMO ASSET.
- What is real: the photographs, the depth model (Depth Anything V2, Apache-2.0, 27 MB, 1.7 s per frame on CPU), the OpenCV guided filter, the ArUco scale card, the point cloud, the geometric classes, the occupancy grid and the path solver, the two documents and their page anchors, the VMR003 intervals, the OCR, the retrieval, the timing and the offline run.
- Third-party services and keys (names only, never values): Gemini API (optional, one cached call, cut at H+18), everything else local. No Elisa, no Valmet API, no cloud on the demo path.

## Questions for the partner Q&A

Saturday 09:00 to 12:00 and 14:30 to 18:00 in Joki. Ask what they will score, not what they think we should build.

- Whose technician is the user, Valmet's own service engineer or the mill's maintenance team?
- Which artefact scores highest: a working phone flow, a measured time study, or an integration sketch with your systems?
- Which document does a technician open first for a cavitation complaint: the IMO, a technical bulletin, the maintenance recommendation, or the spare part list?
- What would your engineers call wrong in this demo, and what would they call missing?

## Decision log

| Time | Decision | Why |
| --- | --- | --- |
| Thu 5 Nov 18:26 | Shortlist Valmet, Traficom, Business Turku; lean Traficom | Two gates: measurable company result and a visible vote story |
| Thu 5 Nov 19:00 | Ranked call in docs/challenge-plans.md puts Traficom first | No data dependency, real licence data, broad brief |
| Fri 6 Nov 15:18 | Plan on the assumption that Valmet was selected | Selection happens before the briefing, so the detailed plan starts now |
| Fri 6 Nov 15:20 | Video method: Remotion pipeline, screen capture as footage | Frame-level sync with the voice; PowerPoint stays the fallback |
