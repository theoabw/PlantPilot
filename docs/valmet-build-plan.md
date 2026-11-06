# Valmet build plan, Friday 6 November

Assumed selected Friday afternoon. The company materials open at 19:30 and only for the team that picked Valmet, so this plan is written from the public summary plus tonight's probes, and section 10 says exactly what changes if the real brief differs. Hours are counted from H+0 = Friday 19:30. Submission is Sunday 10:00. Four team members and one shared sleep block, no night watch: section 6 is built around that, and the scope in sections 3 and 5 is sized for it.

Read [plans/valmet.md](plans/valmet.md) first for the reasoning. This file is the execution plan: what we build, in what order, by whom, and how we prove it.

## 0. What is already verified, tonight

These came from probes run on this machine on Friday afternoon, not from the plan's assumptions. Two of them correct the earlier plan.

| Claim | Result |
| --- | --- |
| The manual is real and text-extractable | 170 pages, 595x792 pt, produced in FrameMaker 2022, 306 KB of extracted text, every page extractable |
| Printed page number equals physical page | page 46 carries the header "46 Liquid flow", so a page anchor is `#page=46` and a human can find it in the PDF |
| The table of contents gives a section map | pages 4 to 6 list numbered sections with dotted leaders and printed page numbers, e.g. "3.4 Cavitation and hydrodynamic noise abatement 55" |
| The earlier plan's example anchor was wrong | it said "section 3.3 Cavitation, page 47". Actually 3.3.3 Flashing of liquids is page 53 and 3.4 Cavitation is page 55. Never hardcode a section number; derive it from the TOC. |
| VMR003 is a real action table | 9 part rows with 1 year and 4 year actions: potentiometer and R/I modulator, display card, limit switches, flexible coupling, coupling set, belt, step motor, gear and lubrication set, valve |
| Nameplate OCR is not the risk | a synthetic plate rendered at 1400x950 read back exactly with tesseract 5.5.0 (psm 4 and psm 6): every field, no substitutions. The risk is camera resolution and venue light, not the OCR engine |

Two consequences. First, the corpus is a solved problem if we parse the TOC instead of regexing headings. Second, the equations extract as garbage, so the parser must drop equation blocks and running headers before indexing, or a query about cavitation will match a wall of symbols.

## 1. The product, in one page

A field technician stands at a valve with a dirty nameplate. They photograph it. The phone shows what the asset is, the manual page that matters with a short quote, and the next service action with its interval and its source. One tap shows what else sits on the line and which neighbour shares the same spare.

Three properties that the demo has to make visible, because they are what makes it Valmet's problem and not a generic OCR toy:

1. **Offline.** The network is off for the whole run. Industrial sites do not have reliable connectivity, and a judge can check this by pulling the cable.
2. **Cited.** Every card names a document, a section and a page, with a quote. No answer without a source.
3. **Honest boundary.** The spare part number needs the Valmet Customer Portal, so we show that boundary instead of inventing a number.

Working name: **Fieldplate** (the plate is the interface, the record is the payload). Two alternates if the room hates it: Tagline, or Page 47. Decide at 20:00, not at 23:00, because the name goes into the repo, the video and the submission.

## 2. The demo path, step by step

One laptop projecting, one phone on the venue network running the same page. Three printed plates on three real objects on the table.

| # | Time | What the judge sees | Live or replay |
| --- | --- | --- | --- |
| 1 | 0:00 | Camera view only, plate in frame, an "offline" badge. No dashboard. | live |
| 2 | 0:08 | Click Scan. Frame freezes, a quadrilateral snaps to the plate. | live |
| 3 | 0:12 | Scan refused: "characters 9 px, need 20, move closer". Judge watches the person move in. | live |
| 4 | 0:20 | Rescan passes. OCR fields appear with confidence: type, DN 150, PN 40, body material, serial. | live |
| 5 | 0:28 | Asset card: tag K-102, line 2 board machine, last service 2025-11-14, criticality high. | live |
| 6 | 0:38 | Manual card: Flow control manual, section 3.4, page 55, two quoted lines, page anchor. | live |
| 7 | 0:48 | Action card: VMR003, check function of limit switches, 1 year interval, source link. | live |
| 8 | 0:58 | Graph tap: asset, valve, document, action, two line neighbours. One neighbour is 14 months overdue and turns red. | live |
| 9 | 1:10 | Failure path: scan a plate not in the register. "No match", three closest types, create-asset button. Nothing invented. | live |
| 10 | 1:20 | One line: median 11 s to the right section, against 64 s on the same documents as a folder tree. | live number |

The moment that proves it works is step 3 followed by step 6: the app refuses a bad frame rather than guessing, then produces a page number from a real manual. The contrast with a chatbot that always answers is the whole pitch.

If OCR fails on the day, the fallback is not a different demo: it is the same demo with the type typed in by hand, and the person says "the camera path is what we showed you twice already". The claim in step 10 drops to document-finding time, and the README says so.

## 3. Data

### 3.1 The corpus

- Source: two public Valmet PDFs, fetched by `make corpus` into `data/valmet/`, which is gitignored. The PDFs are all rights reserved, so they are never committed and never shipped inside the repo.
- Parse: read the TOC pages (4 to 6), build `sections.json` mapping section id, title, level, printed start page and end page. Split the 170 pages by that map, not by heading regex.
- Clean: drop the running header line (the one containing the page number), drop equation blocks (lines with `=`, fraction rules, or symbol runs), drop page furniture. Keep paragraph text, table rows and figure captions.
- Index: SQLite FTS5 over section text with fields `doc`, `section`, `title`, `page`, `text`. VMR003 goes in as a separate table, not as prose.
- Ship: the fetch script, the parser, `fixtures/corpus/` with 40 synthetic sections written in the manual's register (under 256 KB), and a 20 row sample of `sections.json`. The full text stays local.

### 3.2 The asset register

- 48 rows, 4 lines, schema shaped like a CMMS extract: tag, functional location, line, type, family, size, class, body material, serial, install date, last service, criticality, spare group.
- Tags follow a line prefix: `K-102` (board machine, line 2), `P-011` (pump line), etc. 8 rows deliberately overdue.
- The CSV import is documented in the README so a real row can replace a synthetic one in one command. That is the answer to "is this your fiction".
- The three demo assets are chosen so the graph has something to show: one overdue neighbour, one shared spare, one unknown plate.

### 3.3 The plates

- 16 labels, 60 by 40 mm matte stock, printed tonight. Fields: brand, family, type code, size (DN), class (PN), body material, serial, max temperature.
- Three character heights (28, 20, 14 px cap height at camera distance) so the quality gate is a real interaction, not a staged one.
- 12 percent carry one damaged character, so the failure path is physical. One label carries the words SYNTHETIC DEMO ASSET in 6 pt on every plate, so no video frame can be mistaken for a real mill.
- Stuck on 8 real objects in the room: radiator valve, tap, fan, laptop lid, kettle, extinguisher bracket.

### 3.4 Pre-existing versus built at the event

Fetched or written before 19:30: the two PDFs, the TOC parser, the scaffold, the plate artwork. All of it is declared as pre-existing in the README and in the submission's technology field. The app, the index, the register, the proof and the video are built at the event.

## 4. System design

### 4.1 Repo layout

```
app/
  server/          FastAPI, python 3.12 via uv
    main.py        /scan, /assets/{tag}, /section/{id}, /health
    ocr.py         capture gate, tesseract wrapper, field resolver
    corpus.py      TOC parser, FTS index build, retrieval
    register.py    SQLite asset register
  web/             React + Vite + Tailwind, one page, five states
  data/            local only: PDFs, manual.txt, index.db, photos (gitignored)
  fixtures/        committed: 40 synthetic sections, 20 sections, plates.svg
  scripts/         make_corpus.py, make_plates.py, make_register.py, proof.py
  proof/           trials.csv, ocr_trials.csv, metrics.json
Makefile           demo, corpus, data, proof, plates
```

### 4.2 API contract, frozen at H+2

| Endpoint | In | Out |
| --- | --- | --- |
| `POST /scan` | JPEG frame | `{gate: "ok"\|"refused", reason, plate: {fields, confidence}, asset: {...}\|null, sections: [...], action: {...}\|null}` |
| `GET /assets/{tag}` | tag | asset row plus neighbours and shared spares |
| `GET /section/{id}` | section id | title, page, quote, doc path, anchor |
| `GET /health` | | `{ok: true, corpus_sections: n, assets: n}` |

The gate returns a machine reason and a human sentence, because the sentence is on screen during the demo.

### 4.3 Capture and OCR

1. `getUserMedia` at 1280x720, one frame on click, JPEG quality 0.9.
2. Quality gate: Laplacian variance for blur, plus an estimated character height from the plate's detected bounding box. Refuse under 20 px or under the blur floor, with the number on screen.
3. Deskew and threshold the plate crop, then tesseract 5.5.0 `--psm 6`, whitelist per field.
4. Field resolver: regex grammar for `DN` and `PN`, a fuzzy match of the type code against the public family list, and a confidence per field.
5. No match in the register returns null, never a guess. That is a demo step.

### 4.4 Retrieval

- Query = family + size + class + symptom words taken from the asset's criticality and the action table.
- BM25 over section text with a family filter, minimum score, top 3 sections. Below the threshold, return nothing.
- The quote is extracted from the winning section: the sentence containing the query terms, cut to 2 lines.
- Section routing is deterministic and inspectable. No LLM on the answer path; the optional Gemini rewrite of one quote is cached and cut at H+18.

### 4.5 UI

Five states, one page: camera, asset, document, action, graph. Plain SVG for the graph, capped at 25 nodes. No chart library, no map, no dashboard list of all assets. The camera is the first screen and there is no way to see a list of everything, which is what keeps this from becoming an inventory browser.

### 4.6 Offline guarantees

- The bundle, fonts, icons and the whole corpus index are local.
- `make demo` starts both processes, opens the browser, prints the LAN URL and a QR code for the phone.
- The demo runs with the network cable out, tested at M0 and again at freeze.

## 5. The proof

**Claim.** Median 11 s from plate in frame to the correct manual section and action row, against 64 s finding the same documents in a folder tree, over 20 timed trials per arm. The operators are the two team members who did not build the capture path. Nobody on a four person team is a naive user, so the README says so and the sample size is stated on screen.

**Floor.** 16 of 20 trials reach the correct section (80 percent), and 0 of 20 show a wrong asset record without a warning. OCR: 95 percent field-level exact match on 40 held-out photos at 20 px or more. Twenty per arm is kept because the trials cost about 25 minutes of wall clock; it is the photo set that gets cut, not the timing.

**Protocol.**

- Baseline: a folder tree of the same PDFs on the same laptop, 4 line folders, 12 assets each, PDFs named by document code only.
- Task worded identically both arms: "find the section that explains cavitation damage on this valve, and the service action due at one year".
- One person holds the stopwatch and reads the task; one operates. Start on the last word of the task, stop when the target section title is on screen.
- 20 trials per arm, the same 3 assets, alternated arms to spread fatigue.
- If someone from a neighbouring team will sit for ten minutes, their two trials are reported separately as n=2 and are the only genuinely naive run in the set.
- Target set fixed in advance and kept in `proof/targets.csv`, so the operator cannot pick an easy section.

**Output.** `make proof` prints median, IQR, percent correct, wrong-asset count, and OCR field accuracy, and writes `proof/metrics.json`. The video and the README read that file. Nobody types a number by hand.

**If the number misses the floor.** The claim is rewritten to what was measured, and the README says which floor missed. The plan's own history is the reason: the earlier draft said page 47 and the TOC says page 55.

## 6. Schedule

| Mark | Clock | Work | Done when | Owner |
| --- | --- | --- | --- | --- |
| pre | now to 18:45 | Scaffold, corpus fetch, TOC parser probe, plates printed, camera test on the real laptop and both phones | `make demo` serves `/health` with the real section count, and one plate reads in the room's light | lead |
| briefing | 18:50 to 19:30 | Write the criteria verbatim, ask the 8 questions, decide the three contingencies in section 10 | `challenge.md` Choice and criteria filled | whoever is not driving |
| H+0 to H+1.5 | 19:30 to 21:00 | Read the brief, freeze scope and the API contract, assign the four seats | one page of scope, no open interface questions | lead |
| M0 | 22:30 | One page served, `/scan` returns a fixture card, phone opens the page over LAN, 8 plates printed | network-off run shows a card | A capture |
| M1 | 02:00 | 10 of 12 scans resolve the right asset and the right section end to end, offline | the loop works three times in a row | A + B |
| runnable commit | 02:40 | A commit that runs, plus a 60 s raw screen capture of the loop | `make demo` passes on a clean clone at 02:40 | lead |
| sleep | 02:45 to 07:45 | All four sleep. Nobody is on call, so the state we leave has to stand on its own. | a clean clone runs after breakfast with no repair | all four |
| M2 | 07:45 to 12:30 | Graph, failure path, 80 photos, register import | 5 states walk through with no dead end | C UI |
| proof | 12:30 to 16:00 | 20 trials per arm, 40 held-out photos, `make proof` | `metrics.json` has the median and the floors | B proof |
| M3 | 16:00 to 19:30 | 6 shots under 2 minutes, README with setup and numbers, clean-clone test | video plays on a phone, clean clone runs `make demo` | lead |
| buffer | 19:30 to 22:00 | Fixes, final video render, submission text draft | nothing new starts here | lead |
| freeze | 22:00 | Features frozen; only README, video, submission text afterwards | no code change after this | lead |

Cut order, decided now so it is not argued at 03:00 and nobody has to make a scope call at 04:00 while the others sleep: if the loop is not end to end at breakfast, the graph dies that morning; the photo claim drops to document-finding time at 12:30 if photos score under 95 percent; the Gemini rewrite dies at 13:30; the demo drops to 2 assets at 16:00. Never cut: the offline run, `make demo`, the timed baseline, the video.

## 7. The four seats

Four people, so two seats carry a second job. It is written down here rather than discovered at breakfast.

| Seat | Owns | Must hand over by |
| --- | --- | --- |
| A Capture and OCR | camera page, gate math, tesseract, field resolver | API contract at H+0.5, working loop at 02:00 |
| B Corpus, then proof | TOC parser, index, retrieval, quotes, anchors; then the trial harness, the photos and the numbers | index at 21:30, routing at 02:00, harness at 08:00, numbers at 16:00 |
| C UI | five states, graph, the exact on-screen copy | three states at 22:30, all five at 12:30 |
| D Lead | merges, demo driver, video, README, submission, agent dispatch | a runnable commit every 4 hours, and `make demo` green at 02:40 |

Two rules: one writer per file, and the lead is the only person who merges to main. With five people a clobbered file costs an hour; with four it costs the night, and Thursday showed the mechanism: three parallel writers silently overwrote each other's fixes inside one hour.

With four people and no night watch there is no slack, so the handovers above are the arbitration point. If a seat misses its time, the lead cuts from the order in section 6 rather than extending the night.

## 8. Working with agents

Agents should do most of the typing and none of the deciding. Concretely:

- **Delegate with a file scope and a verification command.** Every brief names the files, the interface it must match, the done-when command, and the report shape. Nothing else.
- **Never delegate:** the demo path, the numbers in the claim, the reply to a partner question, the decision to cut a feature.
- **Verify, do not trust.** The owner runs the command that proves the work. A report is not evidence. Tonight's probes are the model: two corrected plan claims came from running `pdfinfo` and `pdftotext`, not from reading a summary.
- **One writer per file.** Give each agent one file or one directory. Where two agents need the same file, order them and hand over, do not run them together.
- **Four people is where agents earn their keep.** They hold the typing; the four of us hold the demo, the number and the Q&A. That is the trade the roster forces, and it works as long as the verification rule above is not skipped.
- **Keep the checks cheap.** `make proof` and `make demo` are the two commands everything else is validated against.

The briefs we will need, in order: corpus parser and index, synthetic register and plates, the capture page and resolver, the UI scaffold, the proof harness. Each is a self-contained spec with a command, which is why they can run in parallel while the humans do the demo and the Q&A.

## 9. What the company hears at 18:50

Write the criteria in their words, not a paraphrase. Ask these, in this order:

1. Whose technician is the user, Valmet's own service engineer or the mill's maintenance team?
2. Which artefact scores highest: a working phone flow, a measured time study, or an integration sketch with your systems?
3. Can you share one redacted asset row and one real nameplate photo tonight? The register is our fiction until you do.
4. For a valve with a cavitation complaint, which document comes first: the IMO, a technical bulletin, the maintenance recommendation, or the spare part list?
5. Which equipment families are in scope: flow control, automation, or also pulp and paper machines?
6. Is a fully offline prototype acceptable, or do you expect a deployed service?
7. What counts as responsible data handling in your scoring: no cloud, no customer data, an audit trail, or all three?
8. Is there a tag numbering standard we should mimic, and what is the one thing your engineers would call wrong in this demo?

The answers change the plan in exactly three ways, covered next.

## 10. If the brief is not what we assumed

No switch is possible: selection closed at 17:30. So these are scope decisions at 19:30.

- **If the task is live sensor telemetry, not documents:** keep the app shell, the camera and the plate, and replace the document card with a telemetry card fed by synthetic vibration data for the same asset. Cost: 3 hours, and the corpus becomes context instead of the answer. Do this only if the brief is unambiguous about it.
- **If asset registers are NDA or customer-confidential:** drop the register card and the graph, keep the type-level assistant: plate, type, manual section, action. The demo survives and the claim becomes "type to manual" instead of "tag to record". Cost: 1 hour.
- **If navigation is the emphasised half:** add the line strip (asset neighbours, a simple SVG of the process line) as the second tap. Do not build indoor positioning.

Anything else the brief says, our two cards and the citation story still answer it. That is the reason this challenge was ranked second: the work survives a disappointing brief better than most.

## 11. Saturday questions and Sunday submission

Saturday Q&A is 09:00 to 12:00 and 14:30 to 18:00 in Joki. Ask what they will score, not what they would build. Best use: show the median from `make proof` if it exists by then, and ask which of the two gates (company score, participant vote) they think the demo is weaker at.

Submission checklist, all before 09:30 Sunday: project name, about text under 5,000 characters, repo link that opens logged out, `make demo` from a clean clone, the MP4 from the video pipeline, built-with list, GenAI tools disclosure, every member's IP acceptance, and a limitations section that names the invented register and the synthetic plates.

The video is six segments, about 100 seconds: flat refusal of a bad scan, the real page number, the action row, the graph with the overdue neighbour, the proof chart, the end card. Screen capture is the spine, the Remotion pipeline wraps it, the voice is an audio track. Rendered after the 22:00 freeze.

## 12. The one number to protect

Every decision tonight is subordinate to this: **a median under 15 seconds from plate to page, measured, with the baseline written next to it.** If the UI is beautiful and the number is 40 seconds, we lose the company gate. If the number is 9 seconds and the page is ugly, we still have the story.

## 13. Open decisions for 20:00

| Decision | Options | Default if nobody objects |
| --- | --- | --- |
| Name | Fieldplate, Tagline, Page 47 | Fieldplate |
| Register size | 48 assets versus 12 | 48 rows, 4 in the demo path |
| Plate count | 24 versus 12 | 24, because damaged tags need spares |
| Photo claim | 80 photos with 40 held out, versus document-only | 80, cut at 12:30 if under 95 percent |
| Sleep block | all four sleep 02:45 to 07:45, versus staggered pairs | all four sleep together; nobody is on call |
