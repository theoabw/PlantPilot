# SinceAI 2026: the schedule and the Valmet challenge in one document

Everything the team has on the event timetable and on the Valmet challenge, merged
from `AGENTS.md`, `docs/event-brief.md`, `challenge.md`, `docs/plans/valmet.md`,
`docs/valmet-build-plan.md`, `docs/plantpilot-plan.md` and `docs/workflow.md`.
Snapshot written Fri 6 Nov 2026, 16:30 EET.

The organiser's platform (`sinceai.app`) and email always win over this document.
Re-run `node scripts/sinceai_check.mjs` for the live clock and phase.

## 1. The event at a glance

| | |
| --- | --- |
| Dates | Fri 6 Nov 15:00 to Sun 8 Nov about 15:30, 2026 |
| Place | Turku Science Park, Kupittaa: EduCity, BioCity and Joki |
| Format | 48 hour AI hackathon, on site, no remote participation |
| Challenges | 15 company challenges, exactly one per team |
| Team | Up to 5 people, solo allowed |
| Entry | Free, event meals free with a Meal RSVP |
| Prize pool | €50,000 across the event, plus optional awards |
| Platform | `sinceai.app`, not Devpost |
| Submission | Sun 8 Nov 10:00 EET, fixed |
| Finalists | 5, one per challenge, picked by the participant vote |
| Finals | Sun 14:00 live at EduCity, 4 min pitch then 6 min jury questions |
| Our challenge | Valmet: €2,000 first, €750 second, €250 third |
| Contact | info@sinceai.fi |

MLH 2027 season member event. Opening and closing at EduCity, Joukahaisenkatu 7,
20520 Turku. Building around the clock at BioCity, Tykistökatu 6, and Joki,
Lemminkäisenkatu 12b (Joki is entered through BioCity).

## 2. The timetable

All times EET. "Our target" marks a team rule, not an organiser deadline.

| When | What | Where |
| --- | --- | --- |
| Thu 5 Nov 15:00 | Public-safe summaries of all 15 challenges open | sinceai.app |
| Thu 5 Nov, evening | Team shortlists challenges it would accept | sinceai.app |
| Fri 15:00 | Registration opens, every member checks in in person | EduCity, floor 1 |
| Fri 15:00-16:45 | Team formation, only if the roster is not already set | EduCity, Aula |
| Fri 15:00-17:30 | Team lead marks the team ready, then selects the challenge | sinceai.app |
| Fri 16:45 | Team formation closes, roster fixed | sinceai.app |
| Fri 16:45-16:55 | MLH introduction and prizes | EduCity, Taidon portaat |
| Fri 17:00-17:30 | Opening ceremony and challenge intros; selection stays open to 17:30 | EduCity, Taidon portaat |
| Fri 17:30-18:30 | Jason Mayes (Google Web AI Lead): keynote and tech talk | EduCity, Taidon portaat |
| Fri 18:30-22:00 | Dinner | Restaurant Mauno, BioCity |
| Fri 18:50-19:30 | Company challenge briefing, hard end 19:30 | our EduCity room |
| Fri 19:30 | Full challenge and materials open for our team; building starts | sinceai.app, BioCity and Joki |
| Sat 07:00 | Breakfast | Mauno |
| Sat 09:00-12:00 | Challenge partner Q&A | Joki, Showroom and floors 2-3 |
| Sat 10:30-13:30 | Lunch | Mauno |
| Sat 14:30-18:00 | Second Q&A window | Joki |
| Sat 17:00-20:00 | Dinner | Mauno |
| Sat 22:00 | Our feature freeze | team rule |
| Sun 07:00 | Breakfast | Mauno |
| Sun 09:00 | Our target: submission entry saved with all required fields | team rule |
| Sun 09:30 | Our target: submission done and attached | team rule |
| Sun 10:00 | Submission deadline | sinceai.app |
| Sun 10:00-12:00 | Participant vote, 20 comparisons per builder | sinceai.app |
| Sun 10:00-13:00 | Lunch | Mauno |
| Sun 12:00 | Five finalists confirmed, one per challenge | sinceai.app |
| Sun 13:00 | If finalist: rehearse at the side of the stage | EduCity |
| Sun 13:15 | Closing ceremony | EduCity, Taidon portaat |
| Sun 13:30 | Top three per challenge announced and awarded | EduCity |
| Sun 14:00 to about 15:10 | Finals, five teams, jury picks the overall winner | EduCity |
| Sun about 15:30 | Event ends | EduCity |

### Deadlines that have already passed

Fixed in October, they cannot be re-opened. Worth checking what was and was not done.

| Deadline | What | If missed |
| --- | --- | --- |
| Fri 30 Oct | Meal RSVP and dietary needs on the dashboard | Email info@sinceai.fi now; unannounced diets cannot be guaranteed |
| Fri 30 Oct | CSC / LUMI AI Factory registration | Closed. Plan the build without LUMI GPUs |
| Fri 30 Oct | Special diet requests | Same as meal RSVP |
| Tue 6 Oct | Original Sokos Hotel Kupittaa code `BSINCEAI` | Book elsewhere; other Turku codes may still work |

## 3. Where we are now

At 16:15 on Fri 6 Nov the checker read **1 day 17 hours 45 minutes to submission,
phase `onboarding` until Fri 6 Nov 19:30 EET**.

The phase doctrine (from `AGENTS.md`):

| Phase | From (EET) | Rule for the phase |
| --- | --- | --- |
| prep | before the event | No challenge chosen; dry-run the deploy path, agree the stack. Do not pre-build a company challenge |
| shortlist | Thu 5 Nov 15:00 | Read all 15 summaries, agree on three the team would accept |
| onboarding | Fri 6 Nov 15:00 | Check in in person, pick the challenge, write down the evaluation criteria the company states, not just the task |
| build | Fri 6 Nov 19:30 | One demo-able path, every other feature cut. Commit something that runs before the night ends |
| freeze | Sat 7 Nov 22:00 | Features frozen. README, demo video and submission text only |
| submit | Sun 8 Nov 07:00 | Artifacts only. Save the entry first, then attach files and links. Be done by 09:30 |
| judging | Sun 8 Nov 10:00 | Vote 10:00 to 12:00. If finalist: 4 minute pitch, then 6 minutes of questions |

When a phase rule and an explicit request conflict, do what the user asks and say
what it costs.

### The repo right now

- `main` carries the PlantPilot bootstrap. `uv run pytest` gives 14 passed.
- Built and tested: FastAPI app, corpus fetch and TOC index, OCR and capture gate,
  register and line graph, synthetic register CSV, plate sheet, proof summary.
- Capture pipeline landed: `scripts/scan.py` and `plantpilot/capture.py` (depth,
  guided filter, ArUco scale, back-projection, RANSAC floor). `make models` fetches
  the 27 MB depth model; `make scan PHOTO=...` turns a photo into a point cloud.
- The web page is a shell around the old nameplate flow: camera, asset, document,
  action and graph cards. No three.js viewer, no semantics, no path solver yet.
- `proof/metrics.json` is `{"n": 0}`, so no claim has been measured yet.
- `README.md` still describes the nameplate-to-manual product, not the spatial
  product in the current plan. It must be rewritten for the spatial demo before
  submission, and it must keep the section headings the submission checker looks
  for ("The problem", "Solution", "Setup", "Demo path", "Technology",
  "What is real and what is mocked").

## 4. Venues and logistics

| Venue | Address | Use |
| --- | --- | --- |
| EduCity | Joukahaisenkatu 7 | Registration, team formation, opening, briefings, Sunday ceremony and finals |
| BioCity | Tykistökatu 6 | Main build hall, meals at Restaurant Mauno, partner stands |
| Joki | Lemminkäisenkatu 12b, entered through BioCity | Build space (Aula and Cave), Saturday Q&A in the tower, Company Lounge |

- EduCity to BioCity is a 3 minute outdoor walk, about 200 m along the raised campus deck.
- Joki is indoors from the far south-east end of BioCity's main lobby, down 10 steps.
  Step-free access has to be arranged in advance by email.
- Kupittaa railway station is next to the campus. Parking: ParkCity
  (Joukahaisenkatu 8, about €15 per 24 h) and P-Station Kupittaa
  (Joukahaisenkatu 2, 24/7, about €15 per 24 h).
- Wi-Fi: EduCity has `TUAS Guest` or eduroam. BioCity and Joki details were still
  unconfirmed when the event brief was written. Plan a phone hotspot as backup.
- Meals at Restaurant Mauno, BioCity: dinner Fri 18:30-22:00, breakfast both
  mornings around 07:00, lunch Sat 10:30-13:30 and Sun 10:00-13:00, dinner Sat
  17:00-20:00.
- No sleeping facilities. Build spaces stay open around the clock, and a short rest
  in suitable areas is fine. Bring a water bottle and snacks for the night.

## 5. The rules that bite

- **One challenge per team, and the choice is final.** Only the team lead of a team
  marked ready can select, Friday 15:00-17:30. No changes, no cancellations.
- **The roster also locks.** After the lead marks the team ready, nobody can be
  added, removed or swapped.
- **Friday check-in is required, in person, by every member.** A member without a
  check-in or an approved Saturday arrival can be removed overnight.
- **On site only.** No remote participation.
- **The submission platform is `sinceai.app`, not Devpost.** An entry on Devpost
  alone is not a submission.
- **The deadline is fixed:** Sun 8 Nov 10:00 EET. Uploads attach to a saved
  submission, so create the entry before adding files.
- **AI tools are allowed and encouraged.** Using AI, even for most of the code,
  does not count against the team. What counts is understanding the system, the
  working product and responsible data handling.
- **Separate pre-existing work from what was built at the event.** Commit often,
  keep the README reproducible.
- **The repository has to open for judges while logged out.** A private repo is
  fine only if evaluators can open it.
- **IP terms vary by challenge.** Some transfer the work to the company, others let
  the team keep ownership and grant a licence. Every member accepts the terms
  personally before the team can submit.
- **No ZIP archives.** Share code through the repository link.

The scheduling fact that shaped the whole weekend: the challenge is selected by
17:30, the company briefing runs 18:50 to 19:30, and the full brief opens at
19:30. So the brief cannot inform the choice. A disappointing brief is a scope
decision at 19:30, not a switch to another company.

## 6. How the work is judged

Each challenge company evaluates its own challenge and picks its top three. The
event brief lists what evaluators weigh:

- Whether it works and actually answers the challenge.
- Real-world relevance and business value.
- Technical quality and feasibility.
- How well the team understands and explains the system.
- Responsible handling of privacy, security and data.

The five finalists are not picked by the companies. They come from the
**participant vote** on Sunday morning, 10:00-12:00, 20 comparisons per builder,
one finalist per different challenge. So the submission text and the demo video
also have to convince the other builders, who are not domain experts. The finals
jury then picks the overall winner from the five live pitches.

## 7. What the submission needs

Required fields in the `sinceai.app` form:

| Field | Notes |
| --- | --- |
| Project name | |
| Submission URL | Where the project can be viewed after the event |
| About the project | Up to 5,000 characters, problem and solution |
| Repository / demo link | Code or a working demo |
| Built with | Technologies, comma-separated |
| Technology feedback | On the tech used over the weekend |
| GenAI tools used | Select all, or "I did not use GenAI" |
| Generative AI in the project | Did we implement a GenAI model or API, how and why, or N/A |
| Challenge IP terms | Every member ticks this personally |
| Challenge | Filled from the Friday selection, organisers only can change it |

Optional: YouTube video URL, pitch deck (PDF, PPT, PPTX), supporting documents
(PDF, PPT, PPTX, DOC, DOCX, TXT, Markdown), demo video (MP4 or WebM), domain name,
MLH prize categories, Red Hat and FIWARE award entries, and a public summary for a
confidential challenge.

What makes a strong entry, in the organiser's words: a working prototype or clear
steps to run it, a repository with a README and setup instructions, a short demo
video of about two minutes, and a concise deck only if it helps. The product is
the pitch.

The README checklist from the event brief: problem and who has it, solution and
what it does, setup from a clean clone, the demo path, a technology inventory,
what is mocked versus real, and the licence.

Our Sunday routine, timeboxed so the entry is saved by 09:30:

1. Run `node scripts/sinceai_check.mjs --public --write` and read the whole report.
2. Fix every failure that is a repository defect, then re-run until only TODO lines remain.
3. Answer every TODO in `SUBMISSION.md` from the real repo and this conversation.
   Never invent a number, a URL or a claim.
4. Open the repo and demo links while logged out and report their status.
5. Write the demo video shot list from the product's real flows: 6 shots, under 2 minutes.
6. Report one go/no-go line: `READY at HH:MM` or `NOT READY: <blocking items>`.

Before 09:30, if the product does not demo, fix the demo path, not the README.
After 09:30, submitting is the only action.

## 8. Our own timeline from here

Hours count from H+0 = Fri 19:30. The plan of record is
`docs/plantpilot-plan.md` (written 16:10 from the real brief). It supersedes the
product shape in `docs/valmet-build-plan.md`; the repo rules, workflow, seats,
agent rules and briefing questions in the old plan still stand.

Gates in the plan of record:

| Gate | Time (EET) | Must be true |
| --- | --- | --- |
| G0 | Fri 19:45 | WebGL runs on the demo laptop, and one venue photo becomes a cloud on screen |
| G1 | Sat 02:00 | Three photos become a cloud, coloured by height and geometry, machines boxed, one plate flies the camera to its asset |
| G2 | Sat 07:45 | Attention layer, path with clearance, cited answer, all in one flow, offline |
| G3 | Sat 12:30 | The 90 seconds runs three times in a row |
| G4 | Sat 16:00 | The numbers are measured and the video script is locked |
| Freeze | Sat 22:00 | No code changes after this |

The earlier build plan adds the working marks the new plan does not restate:

- **pre, now to 18:45:** scaffold, corpus fetch, TOC parser, plates printed, webcam
  tested on the real laptop, phone photo upload over the LAN. Done when `make demo`
  serves `/health` with the real section count and one plate reads in the room light.
- **briefing, 18:50 to 19:30:** write the criteria verbatim, ask the questions,
  decide the contingencies.
- **H+0 to H+1.5, 19:30 to 21:00:** read the brief, freeze scope and contracts,
  assign the four seats.
- **M0, 22:30:** one page served, `/scan` returns a fixture card, phone opens the
  page over LAN, plates printed. Network-off run shows a card.
- **runnable commit, 02:40:** a commit that runs, plus a raw screen capture of the
  loop. `make demo` passes on a clean clone.
- **sleep, 02:45 to 07:45:** all four sleep. Nobody is on call, so the state left
  behind has to stand on its own.
- **M2, 07:45 to 12:30:** graph, failure path, photos, register import. Five states
  walk through with no dead end.
- **proof, 12:30 to 16:00:** timed trials, held-out photos, `make proof`.
- **M3, 16:00 to 19:30:** six shots under two minutes, README with setup and
  numbers, clean-clone test.
- **buffer, 19:30 to 22:00:** fixes, final video render, submission text draft.
  Nothing new starts here.

The 20 minutes at 19:30, in order:

1. Check the brief against the plan and name any scored criterion we are missing.
2. Confirm the demo out loud once.
3. Assign the four seats by name.
4. Freeze contracts: photo upload, cloud buffer, asset with position and label
   source, route request and response.
5. Test WebGL on the demo laptop. Choose the fallback at 19:45, not at midnight.

## 9. The Valmet challenge: what the company says

**Title:** Connecting the physical and digital worlds at industrial sites.
**Prizes:** 1st €2,000, 2nd €750, 3rd €250.
**IP terms:** "Your team owns what you build. Valmet can use it in its business."
No NDA and no restricted data are named for Valmet; FORCIT is the only challenge
the event brief puts a paper NDA on.

The public summary, verbatim:

> Explore how AI can connect the physical and digital worlds in complex industrial
> sites. Build ideas that help people and intelligent systems understand equipment,
> navigate environments and support field-service decisions.

The full brief, verbatim:

> Imagine entering a digital industrial plant where the environment does more than
> look real. It understands where machines are, what they are, how people or robots
> could move between them and which equipment needs attention. Today's 3D captures
> can be visually extraordinary, but they often lack the meaning needed for
> intelligent action. Valmet challenges you to bridge that gap. Explore how spatial
> perception, semantic 3D understanding and AI-grounded equipment information could
> transform a scanned industrial environment into a navigable, useful digital world.

The brief names four capabilities, which the plan uses as the four beats of the
demo: **locate, identify, navigate, explain**. The menu it offers: spatial
perception, semantic 3D understanding, point-cloud intelligence, digital twins,
robotics simulation, and an assistant that can explain the context behind a
maintenance decision.

Still unknown, and only the company can answer it: the **scored criteria**. The
card has three empty lines for them, to be written verbatim at the 18:50 briefing.

### How we got here

Thursday's shortlist ranked Valmet, Traficom and Business Turku. The card's table
puts Valmet first (best visual storytelling), while the paragraph under it leant to
Traficom (the more measurable result), and Business Turku was the safest build. The
decision log records the plan moving to Valmet on Friday afternoon at 15:18.
FORCIT was left off the card: it needs a paper NDA signed on site, and its summary
is deliberately content-free.

The card's Thursday risk line for Valmet said "do not build a digital twin". The
current plan stays a single-room, single-session demo, not a twin platform, so the
risk line still holds even though the full brief now uses the words "digital plant".

### What changed on Friday

The Thursday plan (`docs/plans/valmet.md`) was built from the public summary and
read Valmet as a nameplate and document problem: photograph a valve nameplate, get
the CMMS row, the manual page and the VMR003 service action. That demo had a paper
trail and real documents.

The full brief turned out to be about a scanned plant: spatial perception,
semantic point clouds, navigation and a digital twin. The decision log in
`challenge.md` records the pivot at 15:18, and `docs/plantpilot-plan.md` at 16:10
replaces the product with photos in, meaning out. The old build plan's sections 1
to 6 (product, demo, data, design, proof, schedule) are superseded; section 0 (the
probes), the repo rules, workflow, seats, agent rules and briefing questions still
stand.

No switch of challenge is possible now. Whatever the briefing says at 18:50, the
reaction is which of our planned demos still answers a defensible reading of the
brief.

### What we infer, and what is unconfirmed

- The user is a mill maintenance technician or a Valmet service engineer. The
  register may belong to the customer, not to Valmet.
- "Navigate environments" could mean wayfinding or knowing where an asset sits in a
  process line. The plan does the second (a route through the room, line
  neighbours), not indoor positioning.
- Nothing tells us which artefact scores highest: a working flow, a measured time
  study, or an integration sketch.
- We do not know whether a fully offline prototype is acceptable, or whether
  Valmet expects a deployed service.
- No tag numbering or marking standard is known. The synthetic tags mimic a CMMS
  extract until someone says otherwise.

## 10. The product: PlantPilot

One line: take four photos of a room with a phone, and in about ten seconds you
have a metric point cloud you can walk through. Every machine placed and named,
the ones that need service lit up, a route to one that goes around the equipment,
and a cited reason behind its maintenance decision.

Photo in, meaning out. No scanner, no LiDAR, no GPU.

Three properties the demo has to make visible, because they make it Valmet's
problem and not a generic 3D toy:

1. **Local.** Every stage runs on one laptop, with the network off. A judge can
   check by pulling the cable.
2. **Cited.** The maintenance answer names a document, a section and a page, with a
   quote, and VMR003 supplies the interval.
3. **Honest.** Tags are certain, geometry is probable, appearance labels are a
   hypothesis, and the UI says which. The room is the venue room; the plant is a
   stand-in.

The honesty sentence for the README and the closing card: **the room is real, the
plant is a stand-in; every stage of the pipeline is the one that would run on a
real site.**

Working name: **PlantPilot** (the plate is the interface, the record is the
payload). Alternates if the room hates it: Tagline, or Page 47. The name goes into
the repo, the video and the submission, so decide it at 20:00.

What it is not: LiDAR or photogrammetry capture, a real facility scan, physics
simulation, robot control, a multi-room twin platform, VR or AR, a login, a cloud
service, or an LLM on the answer path. The card's "What we are not building"
section still lists the nameplate-era cuts (a dashboard, work orders, CMMS
integration, a fine-tuned model, invented spare part numbers); most still apply,
but it needs a pass to match the spatial product.

## 11. The 90 second demo

One laptop projecting, its own webcam or four uploaded phone photos. Printed plates
with ArUco markers on real objects in the room.

| # | Time | What the judge sees |
| --- | --- | --- |
| 1 | 0:00 | Four photos of the room on the table, taken with a laptop or phone. Click **Scan**. A point cloud builds, grey, colours off |
| 2 | 0:15 | The cloud rotates. Points take colour: floor, wall, pipe, machine. Labels appear on the machines. Count and time on screen |
| 3 | 0:28 | Click **Needs attention**. Machines light red, each with its service interval and due date from the register. The rest stay grey |
| 4 | 0:40 | Hold a printed plate to the camera. OCR reads it, the twin finds the same asset, the camera flies to it and pulses. The plate and the machine in the model are the same object |
| 5 | 0:55 | Ask for a route from the door to that machine. The straight line is drawn first and visibly cuts through a bench; the real route threads around it, with clearance in centimetres and 0 collisions against 2 |
| 6 | 1:12 | Ask why it needs attention. The answer cites the manual section, the page, the quote and the VMR003 interval, and highlights the neighbour that shares the spare |
| 7 | 1:25 | The numbers, then one line: "four photos, one laptop, no scanner" |

The moment that proves it is step 5. A path that visibly avoids an object is the
brief's own "how people or robots could move between them", and nothing can fake it.

## 12. The technology

**Capture.** `scripts/scan.py` and `plantpilot/capture.py`, already in the repo:
monocular depth, guided-filter refinement, ArUco scale, back-projection,
RANSAC floor plane, voxel downsample. Multi-photo alignment by marker pose when the
card is visible in more than one frame; if alignment is flaky, each photo is its
own fragment and the viewer shows fragments side by side. Start with one photo, add
the second only if time is left.

**Semantics.** Three layers, weakest to strongest:

1. **Geometry:** floor from RANSAC, walls from vertical planes, pipes from cylinder
   runs, machines as boxes above the floor. Cheap, deterministic, explainable.
2. **Appearance:** CLIP (ONNX, open weights) over object proposals to label each box
   as valve, pump, tank, cabinet, bench or pipe. This is the "AI-grounded" layer.
3. **Tags:** the printed plate is read by OCR and matched to the register. Tags beat
   guesses: a tagged machine is certain, an untagged one is a hypothesis, and the UI
   shows the difference.

If CLIP is too slow or too vague on the venue photos, layer 2 is cut and the demo
runs on geometry plus tags. Say which is running on screen.

**Navigation.** Occupancy grid at 5 cm from points between 0.2 and 1.5 m above the
floor, machine boxes as obstacles, A* from the door to the asset, clearance reported
in centimetres, and the naive straight line drawn for contrast.

**Answer.** The existing corpus and register: question plus asset, top three sections
with page anchors, a quote, and the VMR003 interval. No LLM on the answer path.

**Rendering.** three.js, one buffer of points, render on demand. Fallbacks: canvas
2D projection of the same buffer, then an isometric SVG plan. WebGL is tested at
19:45 on the demo laptop.

Probed on this machine on Friday afternoon, on a real photograph:

| Step | Tool | Cost | Result |
| --- | --- | --- | --- |
| Monocular depth | Depth Anything V2 Small, int8 ONNX, Apache-2.0 | 1.7 s at 518 px, CPU | clear near and far separation, object edges preserved |
| Depth refinement | OpenCV `ximgproc.guidedFilter` | 0.1 s | depth edges snap to image edges |
| Metric scale | OpenCV ArUco, 4x4 dictionary, scale card | instant | a 150 mm card printed at 100 percent measures 590 px against 591 expected |
| Back-projection | numpy pinhole, 60 degree FOV | 0.2 s | 241k coloured points at 2 cm voxels, bounded 0.1 to 20 m |
| Floor | RANSAC plane | 0.3 s | normal and offset, 9 to 54 percent inliers depending on the scene |

Whole path, photo to cloud: **3.2 s**. Model size: 27 MB, fetched once by
`make models`, cached in `data/`, gitignored. Everything is local and open source:
OpenCV 5.0, ONNX Runtime, Depth Anything V2, numpy and scipy, three.js. No API key,
no service, nothing on the network at demo time.

The earlier probes still hold for the document half: the Flow control manual is
170 pages with extractable text, the printed page number equals the physical page
(page 46 carries "46 Liquid flow"), the table of contents on pages 4 to 6 gives a
section map, and VMR003 is a real 9 row action table at 1 and 4 year intervals.

## 13. Data, licences, privacy

| | |
| --- | --- |
| Real | the photographs, the depth model, the guided filter, the camera scale from the ArUco card, the point cloud, the floor plane, the semantic rules, the instance extraction, the path solver, the printed plates and OCR, the corpus and its page anchors, the timing, the offline run |
| Synthetic | the asset register, the tag numbers, the service intervals, the plate text, the door and the "plant" framing. The room is the venue room, not a mill |
| Not attempted | LiDAR, photogrammetry bundle adjustment, a real facility, physics simulation, robot control, a production digital twin platform |

- **Documents:** the Valmet Flow control manual (6th edition, dated 4/2022, ISBN
  952-9773-12-9, 170 pages, 6.7 MB) and VMR003 (one page, NelesAce basis weight
  control valve, 1 and 4 year actions). Both are public PDFs, copyright Valmet, all
  rights reserved. `make corpus` fetches them into the gitignored `data/` folder.
  They are never committed and never shipped. What ships is document codes, titles,
  section numbers and quotes of 1 to 3 lines, with the citation.
- **Register:** 48 rows, 4 lines, schema shaped like a CMMS extract (tag, functional
  location, line, type, family, size, class, body material, serial, install date,
  last service, criticality, spare group), 8 rows deliberately overdue. A
  documented CSV import lets one real row replace a synthetic row in one command.
- **Plates:** 16 synthetic labels, 60 by 40 mm matte stock, three character heights
  (28, 20, 14 px cap height at camera distance), 12 percent with one damaged
  character, and `SYNTHETIC DEMO ASSET` in 6 pt on every plate. Stuck on real
  objects in the room.
- **Privacy:** no customer data, no site photos, no people in frame, no real serial
  numbers. Nothing leaves the laptop. The optional Gemini rewrite of one quoted
  section is cached, backend only, key in `.env`, cut at H+18 if it causes trouble.
- **IP:** the team owns the code and the synthetic data; Valmet can use it in its
  business. Confirm at the briefing. Every member must accept the IP terms
  personally before submission.

## 14. The numbers that prove it

Primary claims in the plan of record:

- **Four photos to a labelled, navigable cloud in under 12 seconds**, measured on
  screen.
- **From a plate in frame to that machine highlighted, median under 10 seconds**,
  against 95 seconds finding the same asset by scrolling a 40 row CMMS table.

Supporting, printed on screen and in the README: depth time per frame (1.7 s
measured), point count, scale error against a tape measure (target under 5 percent),
semantic recall on a hand-labelled set of 20 objects in the room (target 15 of 20),
and path clearance plus collision count against the straight line.

`proof/trials.csv` holds one row per trial and `make proof` summarises it into
`proof/metrics.json`. The README and the video read that file. Nobody types a
number by hand. If a number misses, the claim is rewritten to what was measured.

The floor rules from the nameplate plan (18 of 20 correct, 0 silent wrong assets,
95 percent OCR) belong to the old claim and do not transfer to the spatial demo. New
floors are still to be set at G4.

The one number to protect: **a measured, demonstrable number with its baseline
written next to it**. If the UI is beautiful and the number is missing, the company
gate is lost. If the number is there and the page is ugly, the story survives.

## 15. Who does what

Four people. Two seats carry a second job, and it is written down here rather than
discovered at breakfast.

| Seat | Owns | First handover |
| --- | --- | --- |
| A Capture | depth, refinement, ArUco scale, multi-photo, cloud format | venue photo to cloud by 22:30 |
| B Semantics | geometry classes, instance boxes, CLIP labels, plate matching | boxes by 02:00, labels by 07:45 |
| C View and navigation | three.js scene, attention layer, route and marker, the six states | cloud on screen by 22:30, path by 07:45 |
| D Lead | integration, assistant wiring, proof harness, the demo run and video, README, submission | photo plumbed to screen by 22:30 |

Two rules: one writer per file, and the lead is the only person who merges to main.
With four people there is no slack, so a missed handover is the arbitration point:
the lead cuts from the cut order rather than extending the night.

Agents do most of the typing and none of the deciding. Delegate with a file scope and
a verification command. Never delegate the demo path, the numbers, the reply to a
partner question, or a cut. Verify with the command, do not trust the report.
`make demo` and `make proof` are the two commands everything is validated against.

## 16. Cuts, risks, never-cut

Cut order, decided now so nobody argues at 03:00:

- Multi-photo alignment at 02:00 if it fights back.
- CLIP labels at 07:45, keeping geometry plus tags.
- The straight-line comparison at 10:00.
- The fly-to animation at 12:00, keeping a cut.
- Point density down to 50k at any stutter.

Never cut: the photos-to-cloud moment, the plate anchor, the path, the number. The
earlier plan's never-cut list still holds too: the offline run, `make demo`, the
timed baseline, the video.

Risks in the plan of record:

1. **Depth on flat, low-texture surfaces** (white walls, glass) comes out blobby.
   Mitigation: texture in frame, keep the guided filter, lean on the tag where a
   machine matters.
2. **Scale error.** A misprinted card makes every metre wrong. Mitigation: measure
   the printed card with a ruler and pass the real length to `scan.py`.
3. **Semantics look confident and are wrong.** Mitigation: tags certain, geometry
   probable, CLIP a hypothesis, and the UI says which. Never merge them into one
   unlabelled number.
4. **WebGL on the venue laptop.** Tested at 19:45, with two fallbacks.
5. **Too much for one night.** G1 is a complete demo without the path, so a bad
   night still ships on-brief.

## 17. What is still open

| Item | State | Due |
| --- | --- | --- |
| Valmet selected in `sinceai.app` | The plan assumes Valmet; the card still says TODO for time and by whom | Before Fri 17:30 |
| Roster marked ready, every member checked in in person | Must be done by the lead and by each member | Before Fri 17:30 |
| Team names on the card ("accepted by the whole team") | TODO | At check-in |
| The three scored criteria | Blank lines in `challenge.md` | Written verbatim 18:50-19:30 |
| Briefing questions asked | The 8 questions below | 18:50-19:30 |
| Four seats assigned by name | Seats A to D exist, names do not | 19:30 |
| WebGL on the demo laptop | Untested | 19:45 (G0) |
| Product name | PlantPilot, Tagline, Page 47 | 20:00, default PlantPilot |
| Register size | 48 versus 12 | 20:00, default 48 |
| Plate count | The card records 16 printed plates; the old plan lists 24 versus 12 with 24 as default | 20:00 |
| Sleep block | All four sleep 02:45 to 07:45, nobody on call | 20:00 |
| README rewritten for the spatial product | Still describes the nameplate flow | Before the video, ideally by G4 |
| Proof numbers measured | `metrics.json` is empty | G4, 16:00 Sat |
| IP terms accepted by every member | Personal step in the form | Before Sunday submission |
| Submission entry saved and READY | Checker currently passes on the old README | Sun 09:30 |

## 18. Questions for Valmet

At the 18:50 briefing, ask what they will score, not what they think we should
build. In this order:

1. Whose technician is the user, Valmet's own service engineer or the mill's
   maintenance team?
2. Which artefact scores highest: a working phone flow, a measured time study, or
   an integration sketch with your systems?
3. Can you share one redacted asset row and one real nameplate photo tonight? The
   register is our fiction until you do.
4. For a valve with a cavitation complaint, which document comes first: the IMO, a
   technical bulletin, the maintenance recommendation, or the spare part list?
5. Which equipment families are in scope: flow control, automation, or also pulp
   and paper machines?
6. Is a fully offline prototype acceptable, or do you expect a deployed service?
7. What counts as responsible data handling in your scoring: no cloud, no customer
   data, an audit trail, or all three?
8. Is there a tag numbering or marking standard we should mimic, and what is the one
   thing your engineers would call wrong in this demo?

The card's four partner questions (`challenge.md`) repeat questions 1, 2, 4 and 8
above. Keep them in that wording for the Saturday Q&A: whose technician, which
artefact scores highest, which document comes first for a cavitation complaint, and
what their engineers would call wrong or missing.

Saturday Q&A runs 09:00-12:00 and 14:30-18:00 in Joki. Best use: show the measured
number if it exists, and ask which of the two gates (company score, participant
vote) they think the demo is weaker at.

## 19. Where everything lives

| Path | What |
| --- | --- |
| `README.md` | The submission README, currently the nameplate product. Must be rewritten |
| `challenge.md` | The challenge card: shortlist, choice, criteria, demo path, data, questions, decision log |
| `docs/event-brief.md` | The event brief, checked against the site on 1 November |
| `docs/challenge-summaries.md` | The 15 public summaries, verbatim |
| `docs/challenge-plans.md` | The eight planning packs and the ranked call |
| `docs/plans/valmet.md` | The Thursday Valmet plan and reasoning |
| `docs/valmet-build-plan.md` | The Friday 15:40 build plan, product shape superseded, rules and questions stand |
| `docs/plantpilot-plan.md` | The plan of record after the real brief |
| `docs/workflow.md` | PR rules, one writer per file, review in five minutes |
| `AGENTS.md` | The phase doctrine, the numbers that matter, the Sunday routine |
| `scripts/sinceai_check.mjs` | The submission check, offline by default |
| `.agents/skills/` | `sinceai-judge` (the three scoring passes) and `sinceai-pitch` (the 4 minute finals pitch) |
| `proof/` | `trials.csv` and the `metrics.json` the README and video quote |
| `fixtures/` | Small, committed, synthetic: register CSV, section sample, action sample |

The checker: `node scripts/sinceai_check.mjs` prints the live line and the verdict.
`--public` fetches the repo and demo links and verifies they open while logged out,
`--write` writes `SUBMISSION.md` from the current facts, `--json` prints the result
object, `--repo <path>` checks another directory. Exit 0 ready, 1 failures remain,
2 the check itself failed. The check cannot fill the form, record the video, or
verify that every member accepted the IP terms. Those are human steps.

## 20. Sources

- Event site: <https://sinceai.ai/hackathon>
- Field Guide: <https://sinceai.ai/hackathon-2026/guide>
- Builder Guide (rules, submission, FAQ): <https://sinceai.ai/hackathon-2026/guide/builders>
- Builder Resources (tools, awards): <https://sinceai.ai/hackathon-2026/guide/resources>
- Venue and maps: <https://sinceai.ai/hackathon-2026/guide/venue>
- FAQ: <https://sinceai.ai/faq>
- Participant platform: <https://sinceai.app>
- Discord: <https://discord.gg/vMWdrVUPws>
- Contact: info@sinceai.fi
- Valmet flow control manual: <https://www.valmet.com/globalassets/sharepoint/imported/flowcontrol_manual.pdf>
- Valmet VMR003: <https://www.valmet.com/globalassets/sharepoint/imported/vmr003en.pdf>
- Valmet flow control catalogue: <https://www.valmet.com/flowcontrol/valves/>
