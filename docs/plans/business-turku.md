# Business Turku: Adding intelligence to existing industrial machinery
**Tier:** bid candidate. **Verdict:** bid, on the condition that the fault is physically real at the table, the cause is named, and the euro figure comes from the company. Written Thu 5 Nov 2026 from the public summary only.

## 1. The 20 second story
We tape a phone to an old machine until it learns how that machine normally sounds. Then we break the machine on the table in front of you. The screen names what broke, how sure it is, and what a stop costs, 15 seconds before the person standing next to it notices. Nothing to install, no cloud, the sound never leaves the shop.

## 2. What the company said, and what we infer
Business Turku Ltd is a non-profit joint development company for the Turku region, owned by Turun Seudun Kehitys Oy, serving companies in 11 municipalities with free expert services, at Tykistökatu 4 B, 20520 Turku (https://businessturku.fi/en/business-turku-ltd/, read 5 Nov 2026). Its listed key industries are Clean Transition, Blue Economy and Maritime, Security and Dual Use, Health and Life Science, Food and Nutrition (https://businessturku.fi/en/page/4/). BioCity, where we build, is Tykistökatu 6, so a partner visit to our table is a short walk.

Task sentence, verbatim from the public summary: "Explore how AI could add intelligence to established equipment and help people recognise maintenance and performance opportunities." Context sentence: "Existing industrial machinery holds untapped potential for smarter operations."

- Inference: Business Turku does not build machines, so the asset in the brief comes from a member or client company in the region, and the judge may not be its owner.
- Inference: the buyer is an SME with machines from 1990 to 2010, no PLC historian, no condition monitoring budget, and a fitter who listens.
- Inference: "performance opportunities" is scored as hard as failures, meaning energy, throughput and quality yield, not only breakdowns.
- Inference: their live theme is clean transition (they ran a clean transition seminar on 5 Nov), so energy wasted by an unbalanced or misaligned machine is a welcome second number.
- Inference: the main risk is a brief that asks for a regional service concept, in which case a working device is only half of what is scored.

Confirm at the Friday briefing:
1. Which asset classes are in scope, and which one is on their mind: rotating (fan, pump, motor, gearbox) or process (compressed air, hydraulics)?
2. Is there a named end customer or pilot site, and may we name it in the demo and in the video?
3. Do they have real machine data, maintenance logs or a failure history we may use, under what terms, and by when?
4. Is the intended buyer the machine owner, or a service company that maintains many sites?
5. Which unit do they report success in: avoided downtime hours, maintenance cost, energy, or OEE?
6. Is a phone-class sensor acceptable, or do they expect a fixed sensor and a gateway?
7. What would make them call the result not feasible in production: false alarm tolerance, certification, cyber security?
8. Does the deliverable have to include the service model and pricing, or only the working system?

## 3. The 90 second demo
On the table: a desk fan clamped to a plywood board, a phone gaffer-taped to the fan housing, a laptop, and a closed box with four numbered fault cards.

1. 0:00 to 0:15. The fan runs clean. The screen shows a live vibration trace, a health bar at 100, and "baseline learned on this machine, 10 min, today 02:14".
2. 0:15 to 0:30. The judge opens one sealed card and reads it out. It says "2: looseness". A team member with gloves stops the fan, loosens one base screw two turns, restarts it.
3. 0:30 to 0:45. The trace changes, the health bar drops to 61, a red card appears: "Looseness. 2x harmonic up 9 dB, three harmonics. Fix: base screws. One unplanned stop on this machine class: EUR X". This is the moment, 12 to 20 seconds after restart, with the clock visible on screen.
4. 0:45 to 1:05. The screw is retightened, the bar returns to 94 and the alert clears, which is the second proof. Then the judge takes a card, "1: imbalance", and a coin is taped to one blade. A different card appears: "Imbalance. 1x order up 11 dB, weak harmonics. Balance the blade this month". Two cards, two different names: that is the diagnosis, not a threshold.
5. 1:05 to 1:25. One click on "log as real fault" writes a work order JSON and adds the event to the day's false alarm counter, which stays at 0.
6. 1:25 to 1:30. The one number: "18 s median alert, 0 false alarms in 96 min of clean running, EUR X per machine per year".

Live: the sensor capture, the inference, the diagnosis, the clock, the counter, and the hand that applies the fault. Replay: never in the primary path. Two fallbacks, each with a visible REPLAY badge: a recording made 30 minutes earlier on the same machine, and a NASA IMS bearing run for the degradation curve.

## 4. The proof number
The claim: on a machine it has never seen, the system names the applied fault and alerts within 30 seconds of the fault starting, with at most 0.5 false alarms per hour of clean running.

Baseline, two of them. Status quo: no instrumentation, so the fault is found when the machine fails or when someone happens to walk past. We time that with a blind trial, where the person at the table is not told when the card was applied. Second baseline: a single RMS limit, which we also score, because the first judge question will be whether a fixed threshold would do the same.

How it is measured. Every intervention is timestamped on paper by a second person who never touches the laptop. `make eval` joins those timestamps with the model event log and prints three numbers: seconds from injection to first alert, cause label against the card, and alerts per hour on the clean blocks.

Data. Our staged run, at least 12 interventions (8 on the fan, 4 on a second machine or a second mounting position), plus 96 minutes of clean running, and a 4 hour clean block if the table tolerates the fan. Offline, the same code is scored on NASA PCoE Milling, where tool wear VB is measured per cut, and on a FEMTO bearing accelerated life test, where the test runs to the end.

Win line: median under 30 s, no miss, at most one wrong cause in 12, at most 0.5 false alarms per hour. Under that this is an ear with a screen. Over it, an SME can act, and one avoided stop pays for the hour of setup.

## 5. System design
```
phone mic + accelerometer          paper fault log (typed at 12:30)
      | 1 s frames over WebSocket            |
      v                                      v
 [1] capture page --WAV--> [2] ingest + SQLite (runs, labels, events)
                                      |
                                      v
                     [3] features, 1 s window, 0.5 s hop
                                      |
                 +--------------------+--------------------+
                 v                                         v
      [4] per-machine anomaly model              [6] trend and time to threshold
                 |                                         |
                 v                                         v
      [5] diagnosis rules --------------> [8] one page UI <-- [7] business model
                 |
                 v
      [9] make eval: latency, cause, false alarms per hour
```

- [1] Capture page: input phone mic at 16 kHz and the phone accelerometer; logic getUserMedia plus DeviceMotion, 1 s frames to localhost; output WAV frames.
- [2] Ingest: input frames plus card timestamps; logic write to SQLite, clock align to the laptop; output window rows and a ring buffer.
- [3] Features: input 1 s windows; logic RMS, peak, crest, kurtosis, four band energies (0 to 250, 250 to 1000, 1000 to 4000, 4000 to 8000 Hz), spectral flatness, and the 1x, 2x, 3x order track from the strongest low-frequency peak; output 14 numbers.
- [4] Anomaly: input the 14 features; logic per-machine median and MAD from 10 minutes of clean running, capped z distance, alarm on 3 of 5 windows; output a health score and the three largest changes.
- [5] Diagnosis: input the changed features and their shape; logic a physics table (1x only, 1x plus low harmonics, many harmonics plus high-band kurtosis, sidebands); output a named cause, a fix, and the evidence numbers.
- [6] Trend: input the score series; logic exponential smoothing and a linear fit on the last 60 windows; output minutes to threshold with a band, labelled as a trend, not a validated RUL.
- [7] Business: input three editable numbers (stops per year, hours per stop, euro per hour); logic multiplications shown on screen; output euro per machine per year and a ranked fix list.
- [8] UI: input JSON from the three above; logic one page, three zones, Recharts for two charts, one SVG gauge; output the screen the judge reads.
- [9] Make eval: input labels, events and the model log; logic join and aggregate; output the results table that also appears in the README.

Real: the machine, the phone, the audio, the features, the baseline, the score, the rules, the latency, the false alarm count, and the offline NASA results. Mocked: the three euro inputs (sliders tagged "assumption"), a three row fleet list of invented machines, the work order sink (a JSON file, not a CMMS), the machine itself (a desk fan, not a 1990s pump), and the staged degradation (five mass steps, not a run to failure).

## 6. Data strategy
**(a) Public data, opened and checked on 5 Nov 2026.**
- NASA Prognostics Data Set Repository (PCoE): the index page for the numbered sets below, each with a direct download link. https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/
- From that page, Milling: tool wear of the milling insert (VB) across speeds, feeds and depths of cut, 14.0 MB, https://phm-datasets.s3.amazonaws.com/NASA/3.+Milling.zip
- From that page, IMS Bearings: bearing experiments with a degradation record from the Center for Intelligent Maintenance Systems, University of Cincinnati, archived as the data.gov record "IMS Bearings" (https://catalog.data.gov/dataset/ims-bearings), archive 1025.8 MB, https://phm-datasets.s3.amazonaws.com/NASA/4.+Bearings.zip
- From that page, FEMTO bearing accelerated life tests, 1103.4 MB, https://phm-datasets.s3.amazonaws.com/NASA/10.+FEMTO+Bearing.zip
- Case Western Reserve Bearing Data Center, seeded EDM faults from 0.007 to 0.040 in on inner race, ball and outer race, 2 hp motor, 0 to 3 hp load, 1797 to 1720 RPM: https://engineering.case.edu/bearingdatacenter . Labelled fault classes, no run-to-failure, so it supports the diagnosis rules and not the RUL claim.
- MetroPT-3, a real compressor air production unit on a metro train, 1,516,948 rows, 15 features, February to August 2020, unlabelled but shipped with a failure report table (start, end, severity): https://archive.ics.uci.edu/dataset/791/metropt+3+dataset . Good for a false alarm study across months of normal operation.
- Pump wear data and the MFPT fault data sets: to verify. The MFPT page reached on 5 Nov redirected to a society site without the download list, so nothing is planned on it.
- Download rule: 14.0 MB is the only set we can count on from venue wifi, so Milling and one IMS run are pulled on Thursday evening, before check-in. Nothing 1 GB is fetched on site.

**(b) The staged machine and the synthetic failure run.**
- Machine: a 30 cm desk fan on three speeds, clamped to a 60 x 40 cm plywood board. The board is the repeatable mount, which matters more than the machine, because sensor position moves the spectrum more than a fault does. Spare: a second identical fan, and the venue 3D printer if one exists (to verify).
- Sensor: one phone in a case, gaffer tape, mic port 20 cm from the motor, position marked on the housing with a pencil line, same spot every run.
- Fault kit, four numbered cards plus the object: 1 a EUR 0.50 coin (imbalance), 2 a 4 mm hex key (looseness), 3 card and clothes peg against the guard (rub), 4 a spare motor with a dry bushing (bearing).
- Credibility structure: the person who applies the fault never touches the laptop; a third person writes card number and time on paper; the sheet is typed once at 12:30 Saturday and committed as labels.csv. The label is independent of the model by construction.
- Synthetic failure run: five steps of added blade mass, one every 5 minutes for 25 minutes, giving a monotone health trend. Used for the trend and the alert only. It is not a real run to failure and is never described as one.

**(c) What to ask the company for, and the hour it must arrive.**
- By Friday 21:00: the asset class they care about, chosen from four we read out.
- By Friday 23:00: any real signal, log or maintenance export, with terms, or a clear no.
- By Saturday 09:00: three numbers for the euro model (stops per year, hours per stop, euro per hour), or permission to keep ours labelled as assumptions.
- By Saturday 12:00: one sentence on whether a phone-class sensor is acceptable in principle.
- By Saturday 18:00: a written yes or no on naming a pilot site and Business Turku in the video. Each item is dropped at its hour; the build plan does not move for it.

## 7. Build plan to freeze
H0 is Friday 19:30 and the last hour is H26.5, Saturday 22:00.

- M0 scaffold, H0 to H4 (19:30 to 23:30). Repo, `make demo`, FastAPI on 127.0.0.1:8000, one page, replay of a Thursday test recording, feature readout. Done when a clean clone on the demo laptop runs `make demo` with the network off and a trace scrolls. Cut at H4: React, keep plain HTML.
- M1 demo loop, H4 to H9 (23:30 to 04:30). Phone capture over a phone hotspot, baseline learning, score, two diagnosis rules, alert card, event log, card protocol. Done when three consecutive card cycles give the right cause inside 30 s with the phone physically on the fan.
- Sleep, H9 to H13 (04:30 to 08:30): three people sleep, two keep the labelled run going. H13 to H17 (08:30 to 12:30): those two sleep, three analyse. The run never stops; the analysis happens in whichever shift is awake.
- M2 the proof, H9 to H18 (04:30 to 13:30 Saturday, inside the sleep shifts). Labelled run of 12 interventions, 96 minutes of clean running, `make eval`, the euro model, the NASA offline RUL table, README numbers. Done when `make eval` prints a median under 30 s and the UI shows exactly those numbers.
- M2b physical stage, H18 to H21 (13:30 to 16:30). Board, clamps, card box, gloves, printed labels. Done when the 90 seconds runs three times in a row with no hand on the laptop except to click.
- M3 video and README, H21 to H25 (16:30 to 20:30). A 2 minute MP4 recorded one segment at a time, README with setup and limitations, submission text. Done when the MP4 plays offline on a phone and a clean clone still runs `make demo`.
- H25 to H26.5 (20:30 to 22:00): buffer and freeze. After 22:00 only the README, the video and typos.

Cut first, in this order: React at H4; the phone at H9, replaced by the replay with an on-screen badge; the second machine at H13, keeping the second mounting position; the RUL curve on the staged machine at H18, keeping the NASA number; the diagnosis down to two causes at H21, which are the two cards. Never cut: the physical machine, the card interaction, the alert clock, the false alarm counter, `make demo`.

## 8. Default stack and what we cut
Adjusted house stack: Python 3.12 with uv, numpy, scipy, scikit-learn (IsolationForest as a second opinion only); FastAPI and uvicorn on 127.0.0.1:8000; one React, Vite and Tailwind page with Recharts; SQLite for runs, labels and events; the Milling slice and one IMS run kept in `data/` (gitignored) by a committed fetch script, with a few hundred rows of features committed as `fixtures/milling_sample.csv` so a clean clone still runs the offline path; a 60 line HTML page for the phone sensor; `make demo`, `make train`, `make eval`; ffmpeg for the MP4. No Docker, no Postgres, no broker. Note that `data/` and `*.onnx` are gitignored in this repo, and the submission checker enforces the size rules, so no extract, model file or recording is ever committed.

Cut from the house stack: ONNX and any open model (no GPU, no need, another 200 MB over bad wifi), every hosted LLM (network, nondeterminism, and the company gate rewards explaining the system, so a rule table we can defend beats a prompt we cannot), and Aiven or Red Hat OpenShift, which are sponsor routes listed in the event brief but do not remove the one laptop requirement.

Not built: cloud deploy, login, multi-tenancy, a real CMMS connector, a digital twin or 3D plant view, a fleet map, a mobile app, sensor hardware or a PCB, MQTT, Grafana, a CNN on raw audio (unless H18 arrives with the proof already done), and any validated RUL claim on the staged machine.

## 9. Risks and kill criteria
1. The demo laptop's browser cannot capture the phone mic or motion at a usable rate. Mitigation: test both on Thursday on the actual laptop and both phones; fallback is a recorder app writing WAV over USB.
2. Venue wifi. Mitigation: one phone hotspot, laptop and sensor phone on it, nothing at demo time leaves 127.0.0.1, all dependencies installed Thursday.
3. Hall noise faking alarms: other teams, music, announcements. Mitigation: the accelerometer is the alert channel (structure-borne, deaf to air noise), the mic only above 1 kHz, 3 of 5 persistence, a foam mat, a quiet corner.
4. The staged fault does not separate from noise. Mitigation: all four faults pre-tested Thursday; a bigger dose is allowed because the label is the physics, not the dose; second machine ready.
5. The euro number is called invented. Mitigation: three inputs, each tagged assumption, sliders, the formula printed under the number, and the company's own three numbers if they arrive by 09:00.
6. The capture path eats the night. Mitigation: hard cut at H9 to replay.
7. Data download or licence surprise. Mitigation: 14.0 MB set downloaded Thursday, data.gov record read, the extract kept in `data/` and cited in the README, only the small fixture committed.
8. Five people in one API. Mitigation: contract frozen at H4, one branch each, one merger.
9. The fan dies from repeated fault injection. Mitigation: two fans, one spare motor, 15 minutes cool-down between cycles.
10. We ship a diagnosis we cannot explain. Mitigation: every alert prints its three largest feature changes, and the README carries the physics table.

Kill criteria, in the order they can fire:
- At the briefing, if they say the deliverable is a study or a service concept and the score is on the business plan, switch the demo concept to the one phone site walk: 30 second checkups on several machines, ranked, with the euro case as the deliverable.
- At the briefing, if they say the target machines already have condition monitoring and the ask is to use their historian, take their data by Friday 23:00 or switch to the public data replay and say so on screen.
- H4, 23:30 Friday: if `make demo` does not scroll a recorded trace, drop React before dropping the sensor.
- H9, 04:30 Saturday: if the card cycle does not work end to end, drop the phone and ship the replay with the same latency measurement.
- H18, 13:30 Saturday: if the median is over 2 minutes or there is more than 1 false alarm per hour, drop the early warning claim and ship the "diagnosis from a 30 second recording" claim, which is still true and still measurable.
- H21, 16:30 Saturday: if the fan cannot be heard over the hall, the table becomes the prop and the demo becomes the 3 minute video.

## 10. Questions for the partner Q&A
1. Of the five published judging lines, which one decides your top three when two teams both have a working demo?
2. When you compare us with the next team in this challenge, what would make you pick theirs?
3. What result would you call a toy, in one number?
4. Who inside your organisation has to be convinced after the weekend, and what do they read first?
5. Is there a machine in the region where a two week pilot would be cheap for you to arrange, and what usually blocks it?
6. What data would you never allow to leave a customer's site, so that we can show our on-premise design as the answer?
7. Which is worse for you, a missed fault or a false alarm? That sets our threshold.
8. If you were us, what would you cut from this plan on Saturday morning?

## 11. How it scores: company vs participant vote
Company gate. Strong on "it works" and on "understanding the system": we can show the signal chain, name the physics behind each label, and print the evidence for every alert. Technical quality is defensible because the proof is a timed physical intervention and a false alarm count, not a screenshot. Real-world relevance is the weak line: Business Turku is a development company, not the machine owner, and the brief is the broadest in the set, so a euro figure we invented is the fastest way to lose the room. Against Valmet, whose brief is site-scale and visual, our answer can read as small; against Traficom, whose result is a measurable detection problem, ours is the same kind of number but with a machine instead of a radio. The privacy line is where we win points cheaply: no cloud, no account, no data leaving the shop, and one paragraph that says what we deliberately do not collect.

Participant vote. The physical machine is the best asset in this group: a fan that breaks on the table and a screen that names the break is understood in 15 seconds by a builder who has never heard of prognostics. The weakness, and it is the same weakness the team already recorded, is that a vibration chart looks like homework and there is no dramatic artefact: no factory floor, no radio jammer. Traficom has the better "jammer against detector" theatre, Valmet has the better physical world. Our fix is narrow: the judge's own hand applies the fault, the alert is loud and red, one euro number is large on screen, and the fault sound is played out loud for 3 seconds.

## 12. IP, NDA and data handling
IP terms from the public summary: "Your team owns what you build. Business Turku can use it in its business." No NDA appears in the summary, unlike FORCIT. So the repo stays ours and public under MIT, and no signature blocks the build. If a named customer's machine data arrives, it becomes restricted by default until its terms are in writing: not in the repo, not in the video, not in the deck, kept in a gitignored `restricted/` folder on one laptop and reported only as an aggregate.

What the design does not collect: no audio stored beyond the run, no location, no device identifiers, no account, no upload, no analytics. The sensor stream lives on the local network between one phone and one laptop and is deleted with the run. The committed sample is a small feature-table CSV, not a clip, and never any customer's machine. The fan recording used for the replay stays in `data/`, which is gitignored, because the repo bans media.

Repo, video and public summary: the README repeats the clause that the numbers come from `make eval` and that the machine is staged, names the NASA and UCI sources with their URLs, and states what is mocked. The video shows no faces of other teams, no other team's screen, and no customer name without the written yes asked for by 18:00 Saturday. If the company shares anything restricted, the submission carries a public-safe summary instead of the raw evidence, and the video is re-cut before upload rather than after.
