# Traficom: Radio-frequency interference and spectrum planning
**Tier:** bid candidate. **Verdict:** Bid, because a detect-and-explain demo plus a planner over Traficom's own published records answers both halves of the brief offline on one laptop. Written Thu 5 Nov 2026 from the public summary only.

## 1. The 20 second story

A satellite carrier is still there and you cannot see it: a strong signal 2 MHz away has deafened the receiver. Our tool flags the intruder in 1.5 seconds, names its frequency and width, and lists the licensed transmitters in range that could be behind it. One click notches it out, the noise floor drops 8 dB, and the thin carrier line comes back. The same screen then scores a proposed new transmitter near Turku against the 9 broadcast licences already on the air there. For the submission form: the specialist sees the intruder, the fix, and the planning risk, in that order, in one window.

## 2. What the company said, and what we infer

> Satellite and terrestrial radio systems share limited radio-frequency spectrum. Explore how AI could help specialists identify potential interference risks and support more efficient spectrum planning.

Quoted verbatim from the Thursday summary record in this repo, where the task sentence is the second one. It names two jobs, interference risk and spectrum planning, and that is the single most useful fact we have before Friday: both halves are inside the brief, so the briefing cannot take us by surprise on scope.

- Inference: the user is a spectrum specialist at a national agency, not a consumer. The tool is used a few times a week, under time pressure, and its output may end up in a written statement that another party can challenge.
- Inference: "identify potential interference risks" means two different jobs. Reactive: something is happening now, find it and characterise it. Proactive: a proposed assignment may cause trouble later.
- Inference: Traficom already monitors spectrum continuously and publishes a national situational picture, so our value is speed and ranking, not a new source of truth.
- Inference: "more efficient spectrum planning" is measured in engineer hours per assignment and in rework avoided, not in classifier accuracy alone.
- Inference: no personal data is needed, since the published registers hold corporate licence holders, and a public body cannot defend a black box, so every score decomposes into named terms with units.

Confirm at the Friday briefing, in this order of consequence:

1. Which decision is the one that hurts today: closing an interference case, or answering an assignment request?
2. Is detection in scope, or do measurements always come from your own monitoring stations?
3. What has to be in an interference report for it to be usable: centre frequency, bandwidth, duty cycle, duration, direction, recording?
4. May we use the open OData feed on video, and do we need written confirmation of the licence before shipping a cached extract?
5. Is there one real recording, spectrogram or anonymised case we may look at before Saturday 10:00?
6. What separates a useful risk score from a toy for you: agreement with your propagation model, agreement with an engineer's judgement, or an explainable breakdown?
7. Which propagation model do you coordinate with, and may we use free-space path loss plus terrain as a stated simplification?
8. Is anything in this briefing restricted, and what may not appear in the repo or the video?

## 3. The 90 second demo

One laptop, one browser tab at 127.0.0.1, no network cable at any point. Left pane a scrolling waterfall, right pane a Leaflet map of the Turku area.

1. 0:00 One window, no login. The waterfall is already moving. Live: 2 MS/s synthetic I/Q generated in the same process at 20 frames per second.
2. 0:06 A thin carrier sits at the centre of the waterfall, drifting about 15 kHz per second. Readout: carrier 8.2 dB above noise.
3. 0:12 The operator presses "Inject interferer". A bright block appears 2 MHz to the right and the whole pane gets brighter: the noise floor lifts 8 dB and the carrier line disappears. This is the moment the judge sees something happen to a picture they were already watching.
4. 0:14 Within 1.5 s a flag appears: "narrowband, 300 kHz, +18 dB, blocking suspected", with an outline drawn around the block. Latency shown is measured in this run, not scripted.
5. 0:30 The map highlights 9 licensed FM transmitters in Turku from the cached snapshot and lists the ones within 30 km whose band and power could produce this. On screen: "candidate list, not a culprit".
6. 0:45 The operator clicks "Notch". The pane goes dark again, the carrier returns, and a before/after strip shows measured SNR, -3.9 dB then +5.4 dB.
7. 1:00 The operator drags a proposed transmitter onto the map and types 1 kW, 30 m, 100.1 MHz. A score appears, 78 of 100, decomposed into co-channel overlap with an existing 1 kW assignment 6.2 km away, adjacent channel spacing 400 kHz, and terrain profile in the path. Closing line at 1:20: the flag came from the detector, the risk came from Traficom's own records, and both ran with the network cable out.

Live: the waterfall, the detector, the classifier, the notch, the score arithmetic. Replay: the signal itself is synthetic and the licence rows are a cached snapshot. The rows are real; the satellite carrier is a modelled carrier, not a real satellite, and we say so.

## 4. The proof number

One claim: at a false-alarm budget of 1 flag per 10 minutes of noise-only stream, the detector flags a 300 kHz interferer at 0 dB in-band SNR in 1.5 s median (90th percentile 2.5 s).

Baseline: a single-frame energy threshold at 8 dB above the median cell power on the same spectrogram, no persistence, no morphology, tuned to the same false-alarm budget. That is the obvious first-year implementation and it is what an expert will compare us to.

How it is measured: 30 minutes of streamed synthetic I/Q, 40 interferer events from -6 to +12 dB SNR, 10 noise-only minutes, 5 seeds, model fitted on seeds 1 to 3 and tested on 4 and 5. Latency runs from the generator's ground-truth onset to the first flag that survives two consecutive frames. A false alarm is any flag inside a noise-only segment. `make proof` writes latency, false-alarm rate, the baseline at matched latency, a 4-class confusion matrix and both curves to `proof.json`, and the UI reads that file, so no number in the video is typed by hand.

Win rather than toy: median 2.0 s or less at 0 dB, at least 5 false flags per 10 minutes avoided relative to the baseline at the same latency, and 4-class accuracy of at least 0.90 against a 0.25 majority baseline. Toy is slower than 6 s, or a false-alarm rate only reachable by a threshold that misses the low-SNR events, or accuracy under 0.60, or any figure taken on a seed the model trained on. Every one of those numbers is a target until M2 overwrites it with the measured value. Supporting number for the mitigation half: measured carrier SNR goes from -3.9 dB to +5.4 dB on the notch, and the flag-to-fix path is under 10 s of wall clock. The plan layer is not claimed as accuracy: it is checked for rank against Traficom's own answer to "which frequencies are free here", in section 7.

## 5. System design

```
[I/Q generator] numpy, 2 MS/s, seeded: carrier + interferer + receiver blocking + noise
   v
[spectrogram] 1024 FFT, Hann, hop 128, dB
   +--> [detector] CFAR cells + 2-frame persistence + island filter
   |       +--> [classifier] 3-frame patch, ONNX CNN or sklearn GBM
   v
[waterfall UI]  +  [characteriser] centre, -3 dB width, SNR, duty, hop period
                          |
              +-----------+-----------+
              v                       v
   [notch / retune, re-measure]   [attribution: cached licence rows under 30 km]
              |                       |
              +-----------+-----------+
                          v
              [planner] risk 0-100 with three named terms
                          v
              [FastAPI JSON, React + Vite, Leaflet with cached tiles]
```

- Generator: input is a scenario file (seed, carrier, interferer type, timings), logic is numpy signal synthesis plus a receiver compression curve, output is float32 I/Q frames and a ground-truth onset list.
- Spectrogram: input I/Q frames, logic FFT with Hann window and hop 128, output a dB matrix per frame.
- Detector: input the dB matrix, logic cell-averaging CFAR over a median noise estimate plus two-frame persistence, output candidate boxes with a SNR estimate.
- Classifier: input a 3-frame patch per box, logic a small CNN exported to ONNX, or a gradient-boosted tree on 24 hand features if the CNN does not train, output class and confidence over 4 classes.
- Characteriser: input the box and the matrix, logic -3 dB width, duty cycle and hop period over a 5 s window, output the numbers a report needs.
- Mitigation: input the detected centre, logic an FIR notch at that frequency and a 10 dB input attenuator, plus a retune target taken from the cached free-window list, output the re-measured carrier SNR.
- Attribution: input the characteriser output, logic a distance and band-overlap ranking against cached licence rows, output a short candidate list with licence number and owner.
- Planner: input a proposed site, power, antenna height and frequency, logic free-space path loss plus terrain obstruction from a 2 m elevation profile and a protection ratio, output a 0 to 100 risk score with three named terms and their units.
- UI and API: input the JSON payloads, logic FastAPI on localhost and a React build served from the same process, output one page with a waterfall pane and a map pane.

Real: the licence rows, the frequency allocation rows, the free-window answers, the elevation profile, all detector and classifier code, and all measured numbers. Mocked: the received signal, the interferer, the receiver, and the operator's clicks. There is no direction finding, so attribution is a ranked hypothesis and the UI says so.

## 6. Data strategy

- (a) Public data I opened in this session. The hub at https://tieto.traficom.fi/fi/tietotraficom/avoin-data lists the spectrum feeds and says they are OData v4. Taajuusjakotaulukko is the national frequency allocation table: band limits, services in Finland, sub-band limits in Hz, width, usage, mode of traffic, class of station, direction, radiated power, transmitter power, channel spacing, bandwidth, duplex separation, class of emission, comment, updated once or twice a year, and the live feed at https://opendata.traficom.fi/api/v13/Taajuusjakotaulukko returns 5917 rows.
- Live feed, broadcast stations: https://opendata.traficom.fi/api/v13/Radioasematiedot returns 2378 rows with municipality, station name, frequency in Hz, transmitter power in W, antenna height, maximum effective height, polarisation, latitude and longitude in a degrees and minutes string, licence number, licence owner, end date, directivity, and radiated power attenuation plus antenna effective height at every 10 degrees of azimuth. Updated daily.
- Turku extract from that feed: 9 rows, 89.0 to 105.5 MHz, 1 to 3 kW, antennas 70 to 85 m, all at 60N2853 22E2009, owners Bauer Media Oy, Oy Basso Media Ltd., NRJ Finland Oy Ab, Livelaboratorio Oy.
- Live feed, TV stations: https://opendata.traficom.fi/api/v13/TVAsematiedot returns 1066 rows. Nearest to Turku centre: Kaarina, 9.1 km, Mux-A 538.0 MHz, Mux-C 594.0 MHz, Mux-D 634.0 MHz, 70 kW, 310 m antenna, Digita Oy.
- Live feed, free microphone frequencies: https://opendata.traficom.fi/api/v13/RadiomikrofonitVapaatTaajuudet takes lat and lng in degrees plus optional f1 and f2 in MHz, and returns free windows in Hz. At Turku 60.451, 22.266 it returns 6 windows between 470 and 480 MHz (for example 470.10 to 470.20, 470.80 to 472.95, 476.80 to 476.95) and none between 537 and 539 MHz, where Mux-A sits.
- Portal records with licences: https://avoindata.suomi.fi/data/en_GB/dataset/taajuusjakotaulukko and https://avoindata.suomi.fi/data/en_GB/dataset/radioasemat-suomessa both name Creative Commons Attribution 4.0. https://avoindata.suomi.fi/data/en_GB/dataset/radiomikrofonit says License Not Specified, so we validate against it and do not republish its responses in bulk. The same records still show an internal open flag of false, which is a metadata inconsistency; that is a question for the briefing, not something to resolve by assumption.
- Terrain: https://www.maanmittauslaitos.fi/en/maps-and-spatial-data/expert-users/product-descriptions/elevation-model-2-m describes the Elevation model 2 m, a 2 m grid in N2000 heights on EPSG:3067, from laser scanning, accuracy 0.3 m in class I and 0.3 to 1 m in class II, open data under CC BY 4.0 with attribution, not available in parts of the outer archipelago and the eastern border.
- Context for why this matters, from Traficom's own news of 21 April 2026 (https://www.traficom.fi/en/news/interference-affecting-mobile-communications-and-satellite-navigation-services-continues-finland): interference against GNSS and mobile networks increased in spring 2026, GNSS interference is seen around the clock in aviation in southern and central Finland, and its effects at ground level diminish rapidly with terrain, vegetation and buildings. That is the argument for a terrain-aware link budget rather than free space alone. The same page states that Traficom monitors interference daily through spectrum monitoring and interference reports and produces a national situational picture.

- (b) The synthetic generator. Purpose: zero data dependency for the visible half. The demo never asks the venue wifi for anything, and the same seed always produces the same video.
- Legitimate signal: an OFDM carrier of 1.536 MHz with a cyclic prefix, 64-QAM on the data cells, a slowly drifting oscillator and a Doppler ramp of about 15 kHz per second. That is a standard structure, not a claim about a specific satellite service.
- Interferers: four types, a narrowband FM voice carrier, a pulsed chirp, an adjacent channel spillover with a real emission mask, and a hopper that changes channel every 2 s. Each has a ground-truth onset, centre and width, which is what makes latency measurable.
- Receiver: a compression curve and a simple AGC, so a strong off-centre signal lifts the noise floor and hides a weak carrier across the band. This is the one piece of physics that makes a notch filter matter, and it is how a real front end fails. Without it, a notch would be cosmetic.
- Channel and impairments: two-tap multipath, phase noise, IQ imbalance, frequency drift, receiver noise figure. Stated simplification: single antenna, no equaliser, no channel coding, no co-site intermodulation.
- Honesty rule: the README labels every synthetic element, states the absent physics, and explains why an SNR-threshold detector is fairly tested on synthetic input. The plan layer is validated on real data instead, which is where the credibility comes from.

- (c) What to ask for, and by when. One real recording or spectrogram of any interference case, and one anonymised case with its resolution, by Saturday 09:00. A recording is useful only if it arrives before then; after that we cannot fit it and will not pretend to.
- Written word on redistributing a cached extract of the 9 Turku rows and the allocation table rows, by Saturday 12:00. Until then the repo ships the fetch script and a 40 row extract in `fixtures/` with attribution, because `data/` is gitignored.
- Their propagation model and protection ratios, by Saturday 12:00. Arriving later, it is read but not built on.
- Whether we may show the microphone availability responses on video, by Saturday 12:00. Default if no answer: off camera, mentioned as validation only.

## 7. Build plan to freeze

Hours are from Friday 19:30, so H+0 is 19:30 Friday and H+26.5 is the 22:00 Saturday freeze.

- M0 scaffold, H+0 to H+2 (21:30). Done when a clean clone runs `make demo` and shows a 20 frame per second scrolling waterfall from the generator, with `/health` answering on localhost, committed on main with the loop verified once with the network cable out.
- M1 demo loop, H+2 to H+6 (01:30). Done when one button injects the interferer, a flag with a class and a latency appears within 3 s, one click of Notch restores the carrier, and the measured SNR delta is on screen. This is the first end-to-end run, at H+6.
- Night shift, H+6 to H+9 (04:30): proof harness and a first latency and false-alarm table on 5 minutes of stream. Two people on, two asleep, swap at 02:30. Do not run the full sweep on the demo laptop while someone is demoing on it.
- M2 the proof, H+9 to H+12 (07:30). Done when `make proof` writes `proof.json` with latency, false alarms, the baseline row, the confusion matrix and the seed split, and the UI reads only that file. A demo you could put in front of a judge exists here, at H+12.
- Rest, H+12 to H+14 (09:30), staggered, at least one person asleep at all times.
- Map and planner, H+14 to H+19 (14:30). Done when dragging a proposed transmitter gives a 0 to 100 score with three named terms and units, and the attribution list shows cached licence numbers and owners.
- Plan validation, H+19 to H+21 (16:30). Done when 10 locations times 4 test frequencies show our score separating the windows Traficom calls free from the TV channel frequencies it returns nothing for, with the table in `proof.json`.
- M3 video and README, features frozen at H+21 (16:30). Done when the MP4 plays end to end from a clean clone and the README steps work as written. Shot list and recording H+21 to H+23.5 (19:00), README and submission text H+23.5 to H+25 (20:30), final edits and a watched playback H+25 to H+26.5 (22:00).

Cut order and the hour that forces it:

1. Between the two demo presets, keep the one that reads better at 21:30 Friday; the other one goes at H+2.
2. The pulsed and hopper interferer classes go at H+9 if the classifier is not at 0.90; two classes still make a real classifier.
3. Live streaming goes at H+9 (04:30 Saturday): the demo replays a 90 s recorded I/Q file at real speed, the flag is still computed live, and only the input becomes a file.
4. Terrain profile goes at H+16 (11:30 Saturday), leaving free-space path loss with a stated caveat.
5. The map goes at H+19 (14:30 Saturday), leaving a sorted table of the same rows, and the attribution list goes at H+21 (16:30 Saturday).
6. If the video is not recorded by H+23.5 (19:00 Saturday), no more code changes happen, at all.

## 8. Default stack and what we cut

- Python 3.12 with uv: numpy and scipy for synthesis, FFT, CFAR and the FIR notch; no CUDA, no GPU, and LUMI registration closed on 30 October, so nothing depends on it.
- FastAPI on localhost serving JSON only, one process, no database: `proof.json` and `snapshot_turku.json` are the store.
- React with Vite and Tailwind, one page, two panes. The waterfall is a canvas with a fixed colour map, not a chart library, because a 20 frame per second heatmap is cheap in canvas and painful in SVG. Recharts or plain SVG only for the two measured plots, the latency curve and the confusion matrix.
- Leaflet with OpenStreetMap tiles pre-downloaded for a Turku bounding box at three zoom levels and served from disk, with the attribution shown on the map.
- Classifier: scikit-learn gradient boosting first, because it trains in seconds and its features are explainable to a spectrum engineer; ONNX Runtime with a small CNN is the stretch, swapped in only if it beats the tree on the held-out seeds. No Gemini call on the demo path: a key in `.env` and a recorded fallback is one more thing that can fail in front of a judge, and the challenge is not a text challenge.
- `make demo` starts the API, serves the built front end and opens the browser. `make proof` regenerates the numbers. `make fetch` is the only target that touches the network.
- Not building: a regulatory chatbot over PDFs (the trap, and the least defensible thing we could demo), direction finding, live SDR capture from hardware we do not have, multi-user accounts, any deployment, any cloud service on the demo path, a coverage heat map for the whole country, and an automatic mitigation that acts without a human click.

## 9. Risks and kill criteria

1. The brief is planning and regulation, not detection. Mitigation: the planner ships as a first-class layer over real Traficom rows, and the detector is the evidence that a plan was tested. The summary already promises both, which is the main reason this challenge is safe enough to pick before the briefing.
2. The vote does not get it in 20 seconds. Mitigation: the story is a line that vanishes and returns, with one number attached, and the video opens on that before any axis label or product name appears.
3. One person owns the DSP. Mitigation: fixed module interfaces at H+2, a second owner for the metrics harness from H+0, and a generator that anyone can run with one command.
4. The company reads synthetic signals as fake. Mitigation: printed generator physics, absent physics named, and the plan layer validated against Traficom's own availability answer rather than against our own opinion.
5. Wifi and CPU only. Mitigation: every byte cached, no cloud call in the demo path, and a network-cable-out test at M0 and again at freeze.
6. The CNN does not train well enough in time. Mitigation: the tree ships, the CNN is dropped at H+9 without discussion.
7. The real rows may not be redistributable. Mitigation: fetch script plus a small attributed extract, and the licence question asked at the briefing.

Kill criteria, and one timing fact that shapes them. The challenge choice is final at Friday 17:30 and the company briefing ends at 19:30, so a briefing surprise cannot change the company. There is no switch away at the briefing, only a switch of product. The real switch point is the 15:00 to 17:30 selection window.

- Before 17:30, do not select Traficom if the team reads the summary as a document and regulation task rather than a spectrum task, or if nobody on the team is willing to own signal processing for 26 hours.
- Heard at the briefing, switch the product: "interference is already detected, the gap is deciding licence applications." Then the planner and the written risk report lead, the detector becomes the supporting evidence, and the map stays.
- Heard at the briefing, switch the other way: "planning is out of scope, we want monitoring." Then the map and planner are dropped on the spot and the 26 hours go into detection, characterisation, attribution and the report format.
- Hour rule: if the live loop cannot flag an injected interferer within 3 s on the demo laptop by H+6, the demo becomes a replay and the headline number becomes the offline measurement.
- Hour rule: if the planner cannot produce a score with three named terms from the cached snapshot by H+21, the map and planner are cut and the entry is a detector story.
- Standing rule: if the demo needs the network to run, it is not the demo.

## 10. Questions for the partner Q&A

Saturday 09:00 to 12:00. Ask what they will score, not what they would build.

1. If we showed you the same tool twice, once with lower latency and once with a clearer explanation of the score, which one would you rate higher, and why?
2. Which of your decisions should get faster, and by how much, for this to be worth using on a Monday?
3. What evidence in an interference report do you trust, and what do you discount as unsupported?
4. What would make you distrust a risk score: a wrong ranking, a score you cannot decompose, or a model you cannot inspect?
5. Is responsible data handling scored separately, and what would you want to see from us: no personal data, a documented retention rule, or something else?
6. Which of our two layers is the weaker half in your eyes today, so we know where to spend the last four hours?
7. May we cite the open feeds and show their responses on video, and does the portal licence text need anything else from us?
8. What would your own engineers say is the hardest part of this problem, and would they expect a one night prototype to get near it?

## 11. How it scores: company vs participant vote

Company gate. This is the strongest fit of our shortlist on substance: a real signal processing pipeline, a measured latency and false-alarm result with a stated baseline, a planner built on the agency's own machine readable records, and an honest boundary around what a single receiver can and cannot attribute. Responsible data handling is easy here because no personal data is needed at all, and the one dataset that does hold personal data, the amateur call sign register, is excluded on purpose. Weakness against the other shortlisted challenges: the artefact is a specialist instrument, so "business value" has to be argued in engineer hours, which is a weaker pitch than Valmet's direct physical-world story, and any evaluator who wanted a written compliance process will find our tool too low level.

Participant vote gate. The strength is that something visibly happens twice, a line disappears and comes back, and a score changes as a shape is dragged across a map, and both are legible without knowing what a spectrogram is. The weakness is the same one the whole challenge carries: at a glance it can read as an oscilloscope, and the most technical of the eight challenges is the easiest to under-explain. The counter is discipline in the artefact: one screen, one button, one number with units, no jargon in the first five seconds of the video, and the map reduced to "this assignment is risky because of that transmitter". Against Valmet and Business Turku we win on the "it actually works and you can see it" axis and lose on the "I know what this product is for" axis unless the video spends its first five seconds on the disappearing line.

## 12. IP, NDA and data handling

- IP terms from the summary, verbatim: "Your team owns what you build. Traficom can use it in its business." No NDA is mentioned for this challenge; the event brief names FORCIT as the only NDA challenge, so we sign nothing for Traficom unless asked on Friday.
- If Traficom hands over recordings, case files or internal tooling at the briefing, that material is restricted until they say otherwise in writing: it stays out of the repo, the video and the deck, and it is read on one laptop only. Everything currently in this plan comes from pages open to anyone.
- Personal data: none. The station and allocation registers hold companies, not people, and we deliberately do not load the amateur call sign register because call signs identify individuals. The demo's signals are generated by us, so no one's transmission is recorded.
- Licences and repo contents: our code MIT with a NOTICE file listing data sources; Creative Commons Attribution 4.0 with the agency named for the allocation table, the station registers and the 2 m elevation model; the microphone availability service marked License Not Specified, so we cite it as validation and do not ship its responses in bulk; OpenStreetMap attribution on screen. The repo holds the fetch script, a 40 row attributed Turku extract in `fixtures/`, the scenario files and `proof.json`, no bulk feed copies until the licence question is answered, and no model weights at all: `*.onnx` is gitignored and `make models` fetches the small CNN into `data/` if it ships.
- Public-safe summary: we can publish the whole thing, because it is synthetic signals plus open data. If Traficom asks for redaction after seeing it, the video is re-cut from the same `proof.json` and the same cached extract, which costs an hour and no rebuild.
