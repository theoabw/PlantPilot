# Europress: Insights from smart waste-management equipment
**Tier:** fallback. **Verdict:** bid only as a fallback: the before and after number is reachable in about 9 hours and a rehearsed demo in 11, but night-one data is synthetic and Europress already advertises the optimisation we would claim as our insight. Written Thu 5 Nov 2026 from the public summary only.

## 1. The 20 second story

One city fleet, 300 waste containers, six trucks. Today every container is emptied on a fixed weekday whether it is full or nearly empty, so a few overflow and part of the driving is spent on containers that did not need a visit.

We predict the day each container fills, plan the week around that, and send the truck only where it is needed. One container starts filling three times faster than its own normal: that is not a truck job, it is a contract job for the account manager. The screen ends on two numbers, kilometres per month before and after, on the same 300 containers.

## 2. What the company said, and what we infer

Task sentence, verbatim from the public summary:

> Smart waste-management equipment can generate valuable operational signals. Explore how AI could turn those signals into insights that improve service decisions and create customer value.

What Europress publishes (pages opened 5 Nov 2026; URLs at the end of section 6):

- Finnish manufacturer of waste compactors and balers, founded in the 1970s, with headquarters, R&D and manufacturing in Kerava and subsidiaries in Sweden, Norway and Poland (company page).
- "Europress SMART" already connects devices to a cloud and shows real-time fill level, device condition and upcoming maintenance needs, and it explicitly optimises emptying intervals so a device is emptied only when the target fill level is reached (SMART page). Named signals include fill and emptying events, usage and safety-switch data, GPS position, motion and temperature, and on scale-equipped machines fill is estimated from weight, with a preset weight limit sending a full notification (weighing page).
- Published SMART averages: 40 % lower annual waste-management cost, 37 % fewer emptyings, 50 % fewer service visits, 58 % higher fill level, 40 % lower CO2, 40 h more equipment uptime per year; a customer quote on the homepage adds that 90 % of that customer's technical problems are solved remotely (SMART page, homepage).
- CitySolar, its smart street bin, uses a standard 240 L inner bin at 5:1 compaction, so one full bin holds about 1200 L of loose waste and shows its fill level on the front panel (accessories page).

Inference:

- Inference: the challenge cannot be a fill-level gauge screen, because that product already exists. The unserved part is the weekly decision and the economics behind it.
- Inference: the user is a service planner at Europress SMART Center or at a waste operator, and the number they sign off is empties, kilometres, euros and technician visits per month on a named fleet.
- Inference: their percentages are marketing averages on an unpublished baseline. Our result must be a delta on our own stated model, not a validation of theirs.
- Inference: a paired simulation is the honest demo: same demand, same trucks, only the scheduling policy changes.
- Inference: the 20 second moment is one device behaving impossibly, because it ends in a named human action rather than a colour.

Confirm at the Friday briefing:

1. Is there a SMART telemetry export we can have, even 10 anonymised devices for 30 days, and in what schema?
2. Which decision do they want improved: emptying intervals, service-visit planning, contract sizing, or fault response?
3. Who is the user: their SMART Center, or the customer's own waste manager?
4. Which savings metrics do they already track, and what are today's values for one real fleet?
5. What is the typical device mix and sensor set: 240 L bins, 4 to 6 m3 compactors, CitySolar, retrofitted third-party machines?
6. What is their target fill level, and what counts as overfull?
7. Are there contract or municipal minimum emptying intervals, for example hygiene limits on biowaste, that a plan must respect?
8. If real customer data arrives, what may appear in a public repo or a video?

## 3. The 90 second demo

One laptop, wifi off in front of the judge, browser on localhost, `make demo` already running.

1. Map of Turku, 300 containers coloured by predicted days to full. Header: "300 containers, 6 trucks, 1 week".
2. "Run fixed schedule": six routes draw, counters read 255 lifts, 386 km, 6 overfull container-days, and two containers turn dark red before their scheduled day.
3. "Re-plan with forecasts": same demand, same trucks, only the plan changes. Routes get visibly tighter and one street is never entered. Counters read 212 lifts, 318 km, 0 overfull.
4. Drag one cost slider (euro per km, euro per lift, technician hour). The monthly saving recomputes live, so the number is not one hidden assumption. Default: about EUR 6,400 per month on this fleet.
5. Exceptions tab, three cards, each with a sparkline and two numbers: container 0142 filling 3.1x its own baseline for six days (capacity shortfall, account manager, resize the contract); compactor 0219 whose weight-based fill jumps 14 points with no usage events, which is density rather than volume (SMART Center, remote check, no truck); container 0088 with 14 usage events in nine days and fill flat at 12 % (sensor fault, field technician). Each card shows the visit avoided.
6. End card: "318 km instead of 386, 212 lifts instead of 255, 0 overfull instead of 6. Demand is synthetic, calibrated to published Finnish annual volumes. The planner, the arithmetic and the exception rules are real."

Live: everything on screen, including the OR-tools solve (2 to 4 s) and the sliders. Replay: the four-week demand series is generated at startup from a fixed seed, so no step waits; the submitted MP4 is a screen recording of the same offline run.

## 4. The proof number

Claim: over four simulated weeks on 300 containers, replacing the fixed weekly schedule with predicted emptying plus route re-planning cuts truck kilometres by 15 to 25 % and lifts by 12 to 20 %, while cutting overfull container-days from 6 per week to 0.

Baseline: the fixed schedule each container gets today, by type (240 L bins weekly, compactors every second week, CitySolar weekly), with no view of fill level.

Measurement: one demand realisation, fixed seed, two policies, identical fleet, trucks, weeks and demand. Metrics from one Python module and shown on screen: lifts per week, km per week from the distance matrix that `make matrix` builds into `data/`, overfull container-days (container-days above 95 % fill), cost per week from three exposed assumptions. The demand is synthetic, calibrated so annual tonnes and lifts per container fall inside the ranges in HSY's published annual statistics and per-capita municipal waste matches Statistics Finland's 447 kg for 2024.

Win, not a toy: at least 15 % fewer km, no increase in overfull container-days, and every cost assumption visible and adjustable. Below 10 % we say so in the video and README, and show the per-100-container number so a service manager can judge scale. We never present our delta as a reproduction of the company's published 37 % fewer emptyings.

## 5. System design

```
 synthetic event CSV (generated from a committed seed)      [optional] real telemetry from the company
        |                                              |
        v                                              v
 [1] loader and generator -> events.parquet
        |
        +--> [2] forecaster -> forecasts.parquet
        +--> [3] planner: threshold + OR-tools CVRP -> plans/{fixed,planned}.json
        +--> [4] exception rules -> actions.json
        |
        v
 [5] metrics -> metrics.json (lifts, km, overfull, cost, false alarms)
        |
        v
 [6] FastAPI 127.0.0.1:8000, JSON only -> [7] React + Vite + Tailwind, Leaflet, Recharts
```

- [1] Input: generated event CSV or a company export. Logic: schema check, daily resample, device metadata join. Output: parquet.
- [2] Input: fill and usage history. Logic: per-container rate model with weekday and holiday factors, gradient boosting as the optional upgrade. Output: predicted day of reaching 85 % with an interval.
- [3] Input: forecasts, container capacity, truck capacity, shift length. Logic: select containers due before the next visit, then CVRP with a 3 s limit. Output: two comparable week plans.
- [4] Input: residuals from [2] plus raw usage and emptying events. Logic: five named rules with stated thresholds. Output: action cards with an owner and a euro value.
- [5] Input: plans plus demand. Logic: paired simulation and counters. Output: one metrics file that both the UI and the README quote.
- [6] Input: those JSON files. Logic: serve and aggregate. Output: four endpoints, no auth, localhost only.
- [7] Input: the API. Logic: map, counters, sliders, exception cards. Output: the demo.

Real: the optimiser, the forecasting loop, the distance matrix from real road geometry, all arithmetic, the app, the exception rules. Mocked: demand series and planted faults, whose ground truth is known, which is why recall on synthetic data is not evidence of field accuracy. Unknown until Friday: the real sensor schema.

## 6. Data strategy

(a) Verified public data. None of it has container-level fill or route data, so the time series must be synthetic. Helsinki Region Infoshare opened, but its dataset listing timed out twice, at 25 s and 50 s, so nothing is cited from it: to verify.

- https://stat.fi/en/statistics/jate , Statistics Finland waste statistics: municipal waste 447 kg per capita in 2024, page updated 4 Aug 2026. Used to check total tonnage.
- https://avoindata.suomi.fi/data/fi/dataset/paakaupunkiseudun-jatehuollon-vuositilasto , HSY annual waste-management statistics: operational volumes for customer properties, including table 1.4 "Tyhjennykset jätelajeittain" (emptyings by waste type). The best calibration anchor found.
- https://avoindata.suomi.fi/data/fi/dataset/sekajatteen-koostumus , HSY mixed-waste composition: 11 categories, kg per person per year, 2024 one-week study. Used to make contamination and fast-filling cases realistic.
- https://avoindata.suomi.fi/data/api/3/action/package_search?q=j%C3%A4tehuolto&rows=15 , 13 datasets match "jätehuolto" nationally, including Oulu's nightly WFS of public litter bins: real bin inventories are public only for unsensored litter bins, and there is no fill series and no collection route in any of them.
- https://data.turku.fi/ , Turku's 238 published datasets; filtering for "jäte" returns 2, a wastewater service area and small-area statistics, so there is no Turku collection or container data.
- https://operations.osmfoundation.org/policies/tiles/ : OSM tiles forbid bulk download and prefetch and require visible attribution, HTTPS and a real User-Agent, so we do not pre-scrape tiles and instead build a basemap once from https://download.geofabrik.de/europe/finland.html , the Finland extract.
- Europress pages used for the facts in section 2: https://europressgroup.com/fi/ , https://europressgroup.com/fi/smart/ , https://europressgroup.com/fi/retrofit/ , https://europressgroup.com/fi/lisalaitteet/ , https://europressgroup.com/fi/vaakaratkaisut/ , https://europressgroup.com/fi/skip-container-tracking/ , https://europressgroup.com/fi/yritys/ .

(b) Synthetic fleet and generator. 300 devices: 180 x 240 L bins, 90 compactors of 4 to 6 m3, 30 CitySolar bins at about 1200 L effective. Structure that makes it credible: per-container log-normal demand with a device random effect; weekday profile (Monday highest, Sunday near zero at commercial sites); Finnish public holidays from a committed list (to verify against the official calendar); December peak and a July and Midsummer drop; a simulated temperature and rain series, with rain adding 3 to 8 % to mixed-waste mass and a density drift on scale-equipped compactors; 4 % of devices silent for 2 to 10 days, 1 % with a stuck fill reading, 3 planted misuse cases; fill quantised to 5 % steps with 0.5 % of readings dropped. One committed seed file, so every judge sees the same run.

(c) Ask the company for: a telemetry export (device id, timestamp, fill %, usage events, last emptying) by Friday 21:00, even 10 devices for 30 days; their target fill level and current scheduling rule by Friday 21:00; three anonymised device histories with a known problem at the Saturday Q&A. Cut-off: if no real export is in hand by Saturday 09:00 we stay on synthetic and say so, because swapping data at H+13 is how a demo dies.

## 7. Build plan to freeze

Hour marks from Friday 19:30. Freeze is H+26.5, Saturday 22:00.

- M0 scaffold, H+0.5 to H+3.5: repo, JSON schemas, generator, `make demo`, map with 300 containers and the fixed plan. Done when a second laptop with wifi off runs it end to end.
- M1 demo loop, H+3.5 to H+9: forecast, planner, one button that flips fixed to planned with four counters. Done when the same week gives different numbers on demand. This is make or break and it is allowed to be ugly.
- M2 the proof, H+13 to H+18, after four hours of sleep from H+9: four-week paired run, metrics file, cost sliders, three exception cards, false-alarm count. One person covers the 09:00 to 12:00 Q&A for 45 minutes and reports back. Done when every number on screen comes from metrics.json.
- M2b second act, H+18 to H+21: exception cards readable in 20 seconds, from symptom to euro avoided. The same person covers the second Q&A window.
- M3 video and README, H+21 to H+26.5, with a buffer at the end: 2 minute MP4 recorded offline, README with clean-clone steps, provenance and what is mocked, final clean-clone run, pitch skeleton. Done when a stranger runs `make demo` from the README alone. No code after 22:00.

Cut order: at H+6 (Sat 01:30) if the planner does not beat the fixed schedule on one week, drop route optimisation and keep prediction plus a skip decision on the existing route pattern. At H+9 if `make demo` fails on a fresh machine, cut to two map frames and four counters. At H+13 if there is no paired number, cut the exception model to one hard-coded case and put everything into the number. At H+18 cut the weather term, CO2 and the four-week animation to one week. At H+21 cut the sliders to three printed assumptions. Never cut: the paired number, offline `make demo`, README, video.

## 8. Default stack and what we cut

House stack, adjusted: Python 3.12 with uv and a committed lockfile for generator, forecaster, planner and metrics; FastAPI on 127.0.0.1:8000 serving JSON only; one React + Vite + Tailwind front end; Leaflet on a small simplified GeoJSON basemap built once by `make basemap` from the Finland extract into `fixtures/`, kept under 256 KB, with OSM attribution visible, because the tile policy forbids bulk prefetch; Recharts for the before and after bars and the exception sparklines, plain SVG for fill bars; OR-tools CVRP with a 3 s limit and a greedy plus 2-opt fallback behind a flag; SQLite or parquet in `data/` (gitignored), never committed, with the seeded generator as the source of truth; `make demo` syncs, builds, starts both processes and opens the browser, tested with the network down.

No LLM in the critical path: exception sentences come from templates, and any local model is the first thing cut at H+18. Not building: live device integration, auth, multi-tenancy, streaming, a real-time clock, mobile, any deployment, a model training UI, 10k-device scale, time windows and driver break rules, live traffic, gauge-only screens, and the CO2 module, which rests on an assumed factor and is cut at H+18.

## 9. Risks and kill criteria

1. Redundancy: Europress already advertises fill-based emptying optimisation. Mitigation: read the 19:30 brief before building, lead with the exception and economics layer, and test the redundancy question at the Saturday Q&A.
2. Synthetic data makes accuracy claims hollow. Mitigation: calibrate to HSY and Statistics Finland volumes, publish the model, never print an accuracy figure as if measured in the field.
3. It reads as the generic IoT dashboard, and route optimisation is a commodity. Mitigation: the landing screen is a weekly plan and two counters, not gauges; the second act is the exception queue and the person it assigns.
4. Solver or app too slow on a venue laptop. Mitigation: a distance matrix built once and cached in `data/`, 3 s solver limit, plans cached to JSON, greedy fallback.
5. Wifi or a missing package at demo time. Mitigation: fully offline, wheels pre-fetched Friday, video recorded from a local run as the last resort.
6. Five people, three subsystems, no integration, then a real export arrives late. Mitigation: one owner of the JSON contracts from H+0, integration check every four hours, and only the loader changes if data lands, with a frozen cut-off Saturday 09:00.
7. Privacy if real data arrives, or an OSM tile policy breach. Mitigation: restricted folder outside git, jittered coordinates, no customer names, offline vector basemap, attribution on screen.

Kill criteria: switch away if the briefing says the scoring is about a resident-facing app or about extra hardware, because this plan is B2B operations. Switch if they say SMART already ships fill-based emptying optimisation and the brief wants something else, because our delta is then their existing feature. Switch if they cannot name a user or a decision. Inside the build: at H+6 if the planner does not beat the fixed schedule at all, cut to prediction only; at H+9 if `make demo` does not run on a fresh machine, cut to the two-frame demo; at H+13 if there is no paired number, ship a single-number demo and stop adding features.

## 10. Questions for the partner Q&A

1. When two entries are close on Sunday, what single thing moves one above the other?
2. Is the person scoring us from service operations, product, or sales?
3. Which would you rather sign off: a 17 % kilometre saving on a modelled fleet, or a working forecast on your own devices?
4. What would make you distrust a number on our screen?
5. If we had one screen only, do you want the fleet plan or the device exceptions?
6. How do you present customer data to customers today: aggregated, masked, or at device level?
7. Your published 37 % fewer emptyings: what baseline is that measured on, and would you want ours aligned to it?

## 11. How it scores: company vs participant vote

Company gate. It can answer the brief and it produces a number a service manager would act on, with assumptions exposed and nothing leaving the laptop. The weakness against Valmet and Traficom is redundancy: Europress already advertises fill-based emptying optimisation and a SMART Center, so judges may see a rebuilt feature rather than an insight, and our data is synthetic while a Traficom entry can at least show a real signal captured on real recordings.

Participant vote. The weakest of the fallbacks here: route planning is B2B logistics, with no human, no sound and no drama, and 1,000 builders have seen fleet dashboards. It survives on the before and after counter, where 318 against 386 needs one second, and on the one container that behaves impossibly, the only moment with a face. Against a Valmet demo with moving machinery it loses unless the video opens on the two counters and the fault card, before any map appears.

## 12. IP, NDA and data handling

The summary says: "Your team owns what you build. Europress can use it in its business." No NDA is stated, and this is not the FORCIT challenge, so nothing here needs a paper signature, but every member still accepts the terms personally in sinceai.app before the team can submit.

If a real telemetry export arrives, treat it as restricted by default: keep it in a gitignored folder outside the committed tree, ask for written permission before any screenshot or video frame, jitter or aggregate coordinates in any map, and drop attribute names. The submitted repo ships a synthetic dataset only, with a README provenance section stating what is generated, with what seed, and what is real. Licences to confirm from each dependency's own licence file before submission: OR-tools, Leaflet, Recharts, FastAPI, React and Vite, plus ODbL attribution for OSM data. The public-safe summary in the submission form contains no customer names, no real device identifiers and no site addresses.
