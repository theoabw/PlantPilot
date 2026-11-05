# Valmet: Connecting the physical and digital worlds at industrial sites
**Tier:** bid candidate. **Verdict:** bid. The two things we cannot get (their machinery, their asset data) are replaced by printed plates on real objects and by Valmet's own public valve manuals, so both halves of the loop are real. Written Thu 5 Nov 2026 from the public summary only.

## 1. The 20 second story

A field technician stands at a valve with a dirty nameplate and 170 pages of manual. He photographs the plate. Two seconds later the phone shows what the asset is, the manual page that matters, and the next service action with its interval and its source. One tap shows what else sits on that line, which neighbour shares the same spare, and which neighbour is overdue. One sentence: point a phone at a machine and get its record, the right manual page and the next service step, with the network off.

## 2. What the company said, and what we infer

> "Explore how AI can connect the physical and digital worlds in complex industrial sites. Build ideas that help people and intelligent systems understand equipment, navigate environments and support field-service decisions."

- Inference: the user is a mill maintenance technician or a Valmet service engineer working on Valmet and third-party equipment. The summary says field-service decisions, not failure prediction. Tagged equipment means a nameplate plus a record in a customer CMMS, and Valmet's own spare parts catalog and ePartsbook sit behind the Valmet Customer Portal with an access request, so the register is the customer's, not public.
- Inference: navigate environments can mean wayfinding or knowing where an asset sits in a process line. We do the second (line neighbours), not indoor positioning.
- Inference: understand equipment is a document problem before it is a model problem. Valmet's public flow control document library lists IMO (installation, maintenance and operating instructions), technical bulletins, safety manuals and valve maintenance recommendations.
- Inference: a valve nameplate carries brand, type code, size (DN), pressure class (PN), body material, serial and maximum temperature. The real layout and marking standard are theirs.

Confirm at the Friday briefing, because each answer changes the plan:

1. Whose technician is the user, Valmet's own or the mill's maintenance team? It changes who owns the asset register and the access story.
2. Which artefact scores highest for you: a working phone flow, a measured time study, or an integration sketch with your systems?
3. Can you share one redacted asset row (tag, type, location, criticality) and one real nameplate photo tonight? The register's credibility depends on it.
4. For a valve complaint, which document comes first: the IMO, a technical bulletin, the maintenance recommendation, or the spare part list?
5. Which equipment families are in scope: flow control valves, automation, or also pulp and paper machines?
6. Is a fully offline prototype on one laptop acceptable, or do you expect a deployed service?
7. What counts as responsible handling of privacy and data in your scoring: no cloud, no customer data, an audit trail, or all three?
8. Is there a tag numbering or marking standard (functional location, KKS, QR labels) we should mimic?

## 3. The 90 second demo

Setting: one laptop projects the app, and a phone runs the same page over the venue LAN. Three printed plates are stuck on three objects on the table: a radiator valve, a water tap, a laptop lid. Each plate carries the words SYNTHETIC DEMO ASSET in 6 pt.

1. Live. The webcam shows the radiator valve with the plate in frame, and a badge reads network off, because wifi is disabled before the run. The screen shows the camera only.
2. Live. Click Scan. The frame freezes and a quadrilateral snaps onto the plate corners. The judge sees a real object, not a render.
3. Live. The app refuses the frame: characters 9 px, need 20, move closer. He moves in, scans again, the gate passes. The visible engineering is a quality gate, not a spinner.
4. Live OCR, local (tesseract 5.5.0). Fields appear with confidence: type code, DN 150, PN 40, body material, serial.
5. Live lookup. Asset card: tag K-102, line 2 board machine, last service 2025-11-14, criticality high. Rows are synthetic, the schema is a CMMS extract.
6. Live retrieval over the real PDFs. Card one: Flow control manual, section 3.3 Cavitation and flashing, page 47, two quoted lines and a page anchor. Card two, for the NelesAce plate: VMR003, 1 year interval, Check function, limit switches.
7. Live action card: next is check function of limit switches at the 1 year interval. Part numbers sit in the spare parts catalog behind Valmet Customer Portal (ePartsbook) access, which is their real boundary, so we show it instead of inventing a part number.
8. Live graph. One tap: asset, valve, document, action, plus two line neighbours. One neighbour is 14 months overdue and turns red. Capped at 25 nodes, never a full-screen canvas.
9. Live failure path. Scan a plate that is not in the register: no asset match, three closest types, a create-asset button. No invented record and no invented document.

Live: camera, gate, OCR, lookup, retrieval, action, graph, failure path, and no step is scripted output. Replay: only the submitted video, which is this same run recorded Saturday 21:00, so a dead laptop or dead wifi on Sunday cannot cost the entry.

## 4. The proof number

Claim: median 11 s from plate in frame to the correct manual section and action row, against 64 s on a file tree holding the same documents, over 20 timed trials, 4 assets, 2 people who had not used the app. Baseline: a mock CMMS folder tree on the same laptop (4 line folders, 12 assets each, PDFs named by document code only), same two people, same 4 assets, same task wording, stopwatch, 20 trials per side. Measured on: /proof/trials.csv, one row per trial (asset, start, end, target section, correct yes or no, wrong-asset warning shown), median and interquartile range in the README, never asserted in a slide. Data is 4 register assets, real text from the two public PDFs, 3 physical objects with printed plates and 60 held-out photos for the OCR rate.

Floors: 18 of 20 trials reach the correct section (90%), and 0 of 20 show a wrong asset record without a warning. OCR needs 95 percent field-level exact match on held-out photos with character height at or above 20 px. A local probe with tesseract 5.5.0 on a clean rendered plate read 4 of 4 fields at 20 px, 3 of 4 at 14 px and 2 of 4 at 10 px. Real plates, glare and curvature stay unmeasured until Saturday, which is why the gate is a demo step and not a footnote. That becomes a win rather than a toy at 4x faster, 90 percent correct first section, zero silent wrong assets and the whole run offline; 2x with wrong sections is a demo.

## 5. System design

```
 webcam or phone -> [quality gate: blur, character height >= 20 px] --reject--> "move closer"
 |
 v
 [OCR tesseract 5.5.0] -> type, DN, PN, material, serial, confidence
 |
 v
 [field resolver] -> type id, family, confidence
 |
 v
 [asset register] -> asset card      [corpus of real PDF sections, by family]
 |                                   |
 |                                   v
 |                                   [BM25 + family filter] -> 3 sections + citation
 |                                   [action table, VMR shape] -> next action
 +------------------+----------------+
                    v
                    [line graph, 25 nodes max, plain SVG] -> FastAPI :8000 -> React page
                    v
                    [optional Gemini rewrite of one quoted section, cached]
```

- Camera and gate: input camera frames, no model, Laplacian variance plus estimated text height, output accept or move closer. Real.
- OCR: input the plate crop, tesseract 5.5.0 with deskew and threshold, output field strings with confidence. Real.
- Field resolver: input raw strings, regex grammar for DN and PN plus fuzzy match on the public family list, output a type id and a confidence. Real.
- Asset register: input type id or tag, SQLite rows, output the asset card. Schema real, rows synthetic.
- Corpus: input the fetched PDFs split by chapter and page, output sections with page anchors in SQLite FTS. Real text for the two documents opened, synthetic sections for the rest.
- Retriever: input type id plus symptom words, BM25 with a family filter and a minimum score, output the top 3 sections or no match. Real, deterministic.
- Action row: input the product family, lookup in a VMR-shaped table of part, action and interval, output the next action with its source. Real for VMR003, synthetic elsewhere.
- Graph: input the asset, its line neighbours and document links, output a plain SVG. Real rendering of synthetic links.
- Language step, optional: input one quoted section and the asset, one Gemini call, output two imperative lines, cached to JSON and replayed offline. Real call, recorded fallback.

Real: camera, gate, OCR, resolver, retrieval, action lookup, timing. Mocked: the asset register rows, the line neighbours, and document coverage beyond the two PDFs.

## 6. Data strategy

(a) Public data verified in this session. Every row returned HTTP 200 and its text was read. Not verified: whether IMO documents download without a login, whether public documents cover pulp and paper machinery, and what the catalogue at https://valmet.my.site.com/solutionfinder/ contains (it renders in JavaScript). To verify.

| URL | Contents |
| --- | --- |
| https://www.valmet.com/company/ | Valmet describes itself as a global technology leader serving process industries, with 19,400 people and net sales of EUR 5.2 billion in 2025. Context only. |
| https://www.valmet.com/flowcontrol/valves/ | Public product catalogue: Neles, Jamesbury, Neles Easyflow and Flowrox valves; control, on-off and emergency shutdown valves; ball, butterfly, segment, globe, Finetrol eccentric rotary plug and pinch types; actuators and valve controllers. This is our asset type list. |
| https://www.valmet.com/flowcontrol/valves/flow-control-manual/ | Public manual page with the full table of contents. |
| https://www.valmet.com/globalassets/sharepoint/imported/flowcontrol_manual.pdf | The 170-page Flow control manual, 6.7 MB, ISBN 952-9773-12-9, 6th edition dated 4/2022, chapters 1 to 6 and appendices A to M. Copyright 2022 by Valmet and the authors, all rights reserved. Real headings and page numbers to cite. |
| https://www.valmet.com/flowcontrol/documents/ | Public flow control document library. Its document types are application reports, brochures, IMO (installation, maintenance and operating instructions), safety manuals, technical bulletins and valve maintenance recommendations. |
| https://www.valmet.com/globalassets/sharepoint/imported/vmr003en.pdf | VMR003, Application based service recommendation for NelesAce basis weight control valve, 1 page. A real parts by interval table (check function, check condition, calibration, change) at 1 and 4 years, with DN ranges and a grease specification. This is our real action row. |
| https://www.valmet.com/service/spare-parts/ | Spare parts ordering, and the fact that the spare parts catalog and ePartsbook sit behind the Valmet Customer Portal with an access request. Not public, so we show that boundary. |

(b) The synthetic generator we write Friday night.

- 24 plates, 60 by 40 mm matte stock, 3 character heights, tag and serial prefixes, types drawn from the verified families, DN 25 to DN 600, PN 16, 25 and 40, 5 body material codes, and 12 percent with one damaged character so the failure path is physical. Stuck on 12 real objects: radiator valve, tap, fan, laptop lid, kettle, extinguisher bracket. Surfaces, curvature and dirt are then real even though the asset is not.
- Asset register: 48 rows, 4 lines, tag with line prefix, functional location, type, serial, install date, last service, criticality, 8 deliberately overdue. Documented CSV import shaped like a CMMS extract, so one real row can replace a synthetic one in one command.
- Corpus: real PDFs fetched by make corpus into a gitignored folder, plus 40 committed synthetic sections in `fixtures/corpus/`, written in the manual's register so a clean clone runs offline with less coverage.
- Why it is credible: families, sizes and classes come from the public catalogue and manual, action rows and intervals mirror the VMR003 structure, and the document text is theirs with page anchors. The plate field set is an inference until someone photographs a real one.

(c) Ask the company for, with deadlines.

- By Fri 21:30: one redacted asset row, one nameplate photo set (5 photos at 3 distances), the tag convention, and the document type a technician opens first. After 21:30 we build on public documents only. By Sat 09:00 Q&A: whether the register belongs to the customer or to Valmet. At no point: customer data, site photos, or a nameplate carrying a real serial number.

## 7. Build plan to freeze

Hour marks count from Friday 19:30. Night hours assume 4 of 5 asleep from 02:00 to 07:30 and one on call.

| Milestone | Hour mark | Done when | Hard stop |
| --- | --- | --- | --- |
| M0 scaffold | H+0 to H+1.5, Fri 21:00 | make demo serves one page, /scan returns a fixture card, the phone opens it over LAN, 3 plates printed | 21:00 |
| M1 demo loop | H+1.5 to H+6.5, Fri 21:00 to Sat 02:00 | 10 of 12 scans resolve the right asset and the right section end to end, network off, committed, plus a 60 s raw screen capture | 02:00 |
| Sleep | H+6.5 to H+12 | 4 sleep, 1 on call, nothing merges to main overnight | 07:30 |
| M2 the proof | H+12 to H+21, Sat 07:30 to 16:30 | graph and failure path done, 120 photos with 60 held out, 20 timed trials per side, /proof/trials.csv and the median in the README | 16:30 |
| M3 video and README | H+21 to H+24.5, Sat 16:30 to 20:00 | 6 shots under 2 minutes, clean-clone run, README with setup and the numbers | 20:00 |
| Freeze | H+24.5 to H+26.5, Sat 22:00 | features frozen, only README, video and submission text afterwards | 22:00 |

- Cut 1 at H+6.5 (Sat 02:00, before sleep) if the loop is not end to end: the graph goes, replaced by a related-assets list.
- Cut 2 at H+14 (Sat 09:30) if photos score below 95 percent: the claim drops to document-finding time, and the plate is read closer at 25 px.
- Cut 3 at H+18 (Sat 13:30): the Gemini rewrite goes, and the action card becomes a quoted line.
- Cut 4 at H+21 (Sat 16:30): 4 assets become 2, valves only, then record the video.
- Never cut: the offline run, make demo, the timed baseline, the video. Sunday 08:00 to 09:30 is README, MP4 upload, and the entry saved before files are attached.

## 8. Default stack and what we cut

- Python 3.12 provisioned by uv (this host runs 3.14, so pin 3.12 in .python-version), FastAPI on 127.0.0.1:8000 serving JSON, one React + Vite + Tailwind page, all traffic on localhost, CPU only with no GPU (LUMI registration closed).
- OCR: tesseract 5.5.0 through pytesseract, verified installed on this workstation. PaddleOCR only if tesseract fails the photo set; its install size is to verify.
- Language or vision fallback: Gemini API, key in .env, backend only, one call per scan, response written to cache/ and replayed with the network off.
- Storage: SQLite for the register and the corpus index, 200 KB of committed synthetic sections in `fixtures/corpus/` (under the checker's 256 KB warning line, split into files if needed), real PDFs fetched into a gitignored folder by make corpus.
- scikit-learn, chart libraries, Leaflet and OSM tiles: cut. The resolver is a grammar plus fuzzy match, the graph is plain SVG, and there is no site map or indoor positioning.
- One make demo starts uvicorn, serves the built page, prints the LAN URL and a QR code, and the submitted artefact is a recorded MP4 under 2 minutes plus the repo README.

We do not build: digital twin, 3D site model, AR glasses, indoor positioning, sensor telemetry, failure prediction, work order creation, login and roles, multi-user sync, cloud deployment, vector database, fine-tuned model, app store build, ePartsbook integration.

## 9. Risks and kill criteria

1. No Valmet machinery, so a judge reads the demo as a sticker on a radiator valve. Mitigation: keep the object and the page number in the same shot, print plates for the real product families, and say in the first 10 seconds that the register is an extract.
2. OCR fails on a real plate in venue light. Mitigation: matte print, the 20 px gate, a closer-is-better prompt, three plate sizes chosen under the real light Saturday morning.
3. The asset register is our fiction, and the brief also says navigate environments. Mitigation: say both out loud, show a line strip of neighbours, keep the documented CSV import, and ask for one redacted row tonight.
4. The document shown does not match the type, or retrieval picks the wrong chapter of a 170-page manual. Mitigation: family filter plus a minimum score, chapter routing, three candidates with page anchors, and no action card below the threshold.
5. Venue wifi, one shared laptop, five people and scope creep. Mitigation: wifi off for the run, one laptop, one make demo, one owner per component, and no screen lists all assets.
6. The manual is all rights reserved. Mitigation: PDFs and full extracted text stay out of git, only codes, titles, section numbers and 1 to 3 line quotes ship.

Kill criteria, meaning switch direction rather than push on.

- At the briefing, if the task is defined as monitoring live sensor data from Valmet automation, with no document or asset search, switch tonight to a telemetry anomaly path. Our corpus advantage disappears.
- At the briefing, if registers and documents are only available under NDA or a customer contract, switch to a type-level assistant with no asset record, keeping the document and action path.
- H+4 (Fri 23:30): if one scan cannot reach a section end to end, drop OCR to type-the-tag plus pick-the-type. The demo survives and the claim narrows.
- H+12.5 (Sat 08:00): if the plates cannot be read in the real venue light, move the demo object to a large, flat, matte plate on the laptop lid. Do not keep pushing on the radiator valve.
- H+14 (Sat 09:30): if the baseline shows less than 2x, change the claim to correctness (zero wrong sections) and say so in the README.

## 10. Questions for the partner Q&A

1. When you score it works and answers the brief, what does a passing entry contain that a failing one lacks? Name one artefact.
2. Rank these for a field technician: finding the right document, ordering the right part, leaving a cleaner asset record. What is the order?
3. What does the technician carry today, and what do they open first on site: phone, tablet, printed IMO sheet, or the CMMS?
4. For a valve with a cavitation complaint, which document should appear first: IMO, technical bulletin, maintenance recommendation, or application report?
5. What is your tag numbering and asset hierarchy convention, who owns that register, and is there a marking standard (functional location, KKS, QR labels) we should mimic?
6. Which failure is worse, no result or a plausible but wrong section, and what error rate would you accept in a pilot?
7. What non-confidential artefact can you give us today: one redacted asset row, one nameplate photo, a product type list?
8. If this ran in production, where would it live: the customer CMMS, Valmet's service platform, or the technician's phone offline?

## 11. How it scores: company vs participant vote

Company gate. Strong on whether it works and answers the brief, because the run starts at a physical object and ends at a document section and an interval, and strong on privacy because nothing leaves the laptop. The specific weakness against the other shortlisted entries: our asset register is invented, and the brief also says navigate environments. Traficom can show a measured result on physics it simulates. Business Turku needs no physical props at all. Our counter is that the documents are Valmet's own, the action row is a real VMR003 row with a real DN range, and the proof is a timed study with a stated baseline. If this judge weighs integration with their systems, we lose that criterion. If it weighs a working physical-to-digital loop, we win it.

Participant gate. Strong: a real object, an instant card, a visible refusal (move closer), a page number from a real manual, and one red overdue neighbour in the graph. The 20 second read is phone, machine, answer. Weakness: OCR demos are familiar, a graph can look like a dashboard, and a louder team may show a robot or a live machine. Counter: the first frame is a physical object with a printed plate, the second is page 47 of a real manual, and both are inside the first 5 seconds of the video.

## 12. IP, NDA and data handling

- The summary's terms are: "Your team owns what you build. Valmet can use it in its business." No NDA and no restricted data are mentioned for Valmet; the event brief puts the paper NDA on FORCIT. Confirm at the briefing.
- The public manual says "Copyright 2022 by Valmet and the authors. All rights reserved." So the PDFs and the full extracted text do not go into the repo. What ships is document codes, titles, section numbers and quotes of 1 to 3 lines with the citation, make corpus rebuilds the rest into a gitignored folder, and the README carries a public-safe summary that names no customer, no mill and no real asset.
- Every demo plate carries the words SYNTHETIC DEMO ASSET, so the video cannot be read as a real mill or a real serial number. No customer data, no site photos, no people in frame. The Gemini key lives in .env, backend only, never in the browser bundle, revoked after the event. The team owns the code and the synthetic data, and the fetch script is ours to hand over for Valmet to run under its own access.
