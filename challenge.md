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
- The task in the company's own words: to be written at the 18:50 briefing. The public summary says: "Explore how AI can connect the physical and digital worlds in complex industrial sites. Build ideas that help people and intelligent systems understand equipment, navigate environments and support field-service decisions."
- Why this one (business value, data available, fit with the stack): a technician photographs a valve nameplate and gets the asset record, the cited manual page and the next service action, offline. Valmet publishes the 170 page Flow control manual and the VMR003 service recommendation, both fetched and parsed, so the document side is real rather than mocked. The result is measurable (plate to page in seconds, against a folder-tree baseline) and the vote story is a physical object in frame.
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

1. Camera view of a printed plate on a real object, network off. Click Scan, the app refuses the frame with the measured character height, the person moves closer.
2. Rescan passes, OCR fills the fields, and the screen shows the asset card, the manual section with a quote and a page anchor, and the VMR003 action row with its interval.
3. One tap opens the line graph: two neighbours, one of them 14 months overdue. Then a plate not in the register returns no match instead of a guess.

The moment that proves it works (output, number, before/after): median seconds from plate in frame to the correct section and action, measured over 20 trials, against 64 s finding the same documents in a folder tree. Target under 15 s; the earlier plan targeted 11 s. The number comes from `make proof` and is never typed by hand.

## What we are not building

- A digital twin, a 3D site model, AR glasses, or indoor positioning.
- A dashboard that lists every asset; the camera is the only entry point.
- Work order creation, CMMS integration, login, roles, cloud deployment.
- A fine-tuned model, a vector database, or an LLM on the answer path.
- Invented spare part numbers: the ePartsbook boundary is shown, not faked.

## Data and privacy

- What data we use: two public Valmet PDFs (the Flow control manual and VMR003), a 48 row synthetic asset register, 16 printed synthetic plates, and photographs of our own objects.
- Where it comes from and where it goes: the PDFs are fetched by script into the gitignored `data/` folder and never committed; neither the PDFs nor the extracted text nor the photographs leave the laptop. The PDFs are all rights reserved, so only section numbers, titles and quotes of 1 to 3 lines ship.
- What is mocked: the asset register, the tag numbers, the place names on the plates, the line graph and the overdue neighbour. Every plate carries SYNTHETIC DEMO ASSET.
- What is real: the two documents, the section and page anchors, the VMR003 interval rows, the OCR, the retrieval, the gate, the timing and the offline run.
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
