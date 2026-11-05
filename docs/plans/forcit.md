# FORCIT Group: Drill and Blast Cycle Intelligence
**Tier:** fallback. **Verdict:** conditional bid: highest upside and highest risk on the board, weakest vote story, and the only challenge where the product can be finished before we are allowed to see the data. Written Thu 5 Nov 2026 from the public summary only.

## 1. The 20 second story
One bench is 48 holes and 18,000 tonnes of rock, planned days before the shot: drilling, explosives, loading and crushing, about €82,000. The holes never come out where the plan put them, and the bill arrives later as boulders too big for the crusher and a second blast. We price that mistake before the trigger and hand back a cheaper pattern. On the demo bench the same holes go from €4.76 to €4.28 per tonne and oversize from 13.2% to 6.9%, from records the site already keeps.

## 2. What the company said, and what we infer
Summary, verbatim: "Explore how AI could support safer, smarter decision-making in demanding industrial operations."
Verified today (pages opened, URLs in 6a):
- Group: explosives services since 1893, with blasting and charging services, environmental impact management and insensitive munitions defence technologies; markets Finland, Sweden and Norway; 500 professionals; Hanko address. The defence-chemical side is real: the group site reports a foundation stone for a new TNT production facility (15 Sep 2026) and a €30 million European Commission grant for it (14 Oct 2026).
- The Explosives arm sells charging, transport, technical support, storage and licensing, and training; products include bulk emulsion (KEMIITTI 510, 610, 810), ANFO, ANEX and HYDRANEX, detonating cord and electronic detonators (uni tronic 600, eDev II).
- It is the exclusive Nordic and Baltic retailer of O-Pitblast, whose published features include 3D plan design, borehole deviation measurement (O-Pitdev), fragmentation and vibration prediction (O-Pitsurface), greenhouse gas estimation (O-Pit Eco) and field QA (O-Pitapp). They already sell prediction. A better dashboard is not a contribution; a decision that changes the pattern is.

The cycle, reconstructed; sourced unless marked Inference.
1. Plan: holes on a grid, burden (distance to the free face) and spacing from rock and hole diameter. Inference: burden 25-35 times diameter, spacing 1.1-1.4 times burden.
2. Drill and survey: holes to bench depth plus subdrill (Inference), then a downhole probe measures where they went (O-Pitdev, sourced), so the real burden is not the designed one.
3. Charge: mass per hole from a powder factor. ANFO is 94% ammonium nitrate and 6% fuel oil: cheap, sold in bulk, needs a booster, produces carbon monoxide and nitrogen oxides. Inference: powder factor 0.5-1.1 kg/m3.
4. Stem: inert material above the charge confines the gas (sourced). Inference: short stemming sends gas up the hole, so flyrock, noise and coarse rock.
5. Sequence: holes fire in a designed order milliseconds apart, and positions, depths, charge and timing together decide the result. Inference: 8-25 ms between holes, 42-100 ms between rows.
6. Break, muck, haul, crush. Inference: fragmentation, muck pile and backbreak, vibration, then oversize that is broken again or jams the crusher, and charge per delay at the nearest structure caps the pattern.
7. Cost per tonne: drilling, explosives, detonators, labour, load and haul, crushing, secondary break. Inference: the quantity a customer buys, and our headline metric.

Confirm at the Friday briefing:
1. Is the material hole-level (plan, survey, charge, detonator log) or bench aggregates?
2. Which quantity is scored: cost per tonne, fragmentation or oversize, deviation, cycle hours, or safety events?
3. Is there one bench where plan and outcome are both known? That is our private calibration case.
4. What is their oversize definition and crusher opening, and what does a secondary break cost per tonne?
5. Is timing a decision they want changed, or fixed practice?
6. What may we say publicly, in one paragraph they approve?

## 3. The 90 second demo
One laptop, localhost, wifi off. Live unless marked replay.
1. 0:00 Plan view, 48 holes with depth, charge and delay. Header: 18,040 t, €4.54/t. (live)
2. 0:12 Click "Load survey". Holes shift to measured positions; hole 27 turns amber, 1.9 m off at 15.8 m depth, stemming 1.4 m instead of 3.0 m. (replay fixture, committed seed)
3. 0:22 Click hole 27: a section shows the charge 0.5 m from the collar and the 4.1 m burden it now faces. Risk 0.81, one reason string, no black box. (live)
4. 0:32 Click "Price it": the header counts up to €4.76/t, +€3,990, oversize 13.2%, cycle 47.5 h. (live)
5. 0:45 Click "Recommend": hole 27 from 111 to 92 kg, 1.6 m more stemming, 12 kg to each neighbour, rows 3-5 retimed from 42 to 50 ms, and a 9% trim of the marginal kilograms in the other rows, each change with a reason and a euro value. Header falls to €4.28/t. (live, under 1 s)
6. 0:58 Click "Fire": a 2D section fires in delay order over 1.8 s, the muck pile heaves, the fragmentation curve draws itself, oversize drops to 6.9%, cycle to 44.6 h, one recorded low thump under it in the video. Then click "Compare": €4.76 against €4.28 as the largest text, and switch to the evaluation page, 50 held-out benches, median 5.7%, shuffled control 0.4%. Stop talking. (live animation, recorded audio, then replay)

Live: model, optimiser, anomaly score, counters. Replay: the survey fixture and the 50-bench table, both generated by seed before the event. Nothing touches the network; nothing can fail on stage except the laptop.

## 4. The proof number
Claim: on 50 held-out synthetic benches, the recommender cuts cost per tonne by a median 5.7% against the fixed-rule plan (0.80 kg/m3, 42 ms row delay) run on the same measured holes, with oversize no worse and no constraint violations.
How measured: `make eval` runs 200 benches, tunes on 150, reports on 50 whose rock factor and rates sit outside the tuning range, and writes JSON plus a table. Two controls decide whether it is a win or a toy:
- Shuffled control: each recommendation applied to a different bench; median gain must fall below 1%. If shuffling also gains 5%, the model is not doing the work.
- Sensitivity: the reference delta moves from -6.1% to -12.5% as secondary break goes €3 to €9 per tonne of oversize; explosive price €2.20 to €3.40/kg does not move it, because both plans scale.

Win: median at least 4%, shuffled control at most 1%, at most 2 of 50 benches violating a constraint. Below that the README says so and the demo is a cautionary tool. Not claimed: that this predicts a real blast; it is a transparent model plus a search over it. Figures here come from the reference bench and the rate card in 6b; the README quotes the `make eval` run, not this page.

## 5. System design
```
seed + bench spec
  -> generator -> fixtures/synthetic/bench_*.json
  -> cycle model (x50, oversize, PPV, cost/t, hours)
  -> anomaly layer (planned vs measured, risk score)
  -> optimiser (grid + constraints, informed by both)
  -> FastAPI 127.0.0.1:8000 (3 JSON routes + built SPA)
  -> React + Vite (SVG plan, SVG firing section, Recharts curve, counters)
  make eval -> eval.json (50 held-out benches, shuffled control)
```
- Generator: seed and bench spec in, bench JSON out (holes, rock factor, rate card). Deterministic.
- Cycle model: geometry, charge and delay in; fragmentation curve, oversize, PPV, cost per tonne and cycle hours out. Closed form, no training.
- Anomaly layer: planned against measured per hole in; risk score and one reason out. Fitted at startup in under 2 s.
- Optimiser: bench plus constraints in; admissible pattern and a delta table out. Discrete search, no solver dependency.
- API and UI: `/bench`, `/price`, `/recommend` and the built SPA in one process on one port; one screen, no navigation.

Real: the formulas, the search, the anomaly fit, the held-out evaluation, the seed-to-identical-output guarantee. Mocked: every FORCIT input, the survey fixture, the rate card, the rock mass. The header says synthetic, not the small print.

## 6. Data strategy
**(a) Verified public material, opened today:**
- <https://forcitgroup.com>: group facts above.
- <https://forcitexplosives.fi/en/services/> and <https://forcitexplosives.fi/en/products/>: charging, transport, technical support, storage and licensing, training; bulk emulsion, ANFO, cord, electronic detonators.
- <https://forcitexplosives.fi/en/o-pitblast/>: design suite, deviation measurement, fragmentation and vibration prediction, field QA.
- <https://en.wikipedia.org/wiki/Drilling_and_blasting> and <https://en.wikipedia.org/wiki/ANFO>: procedure, pattern, stemming, timing; ANFO 94/6, cheap, needs a booster, fumes.
- <https://data.mendeley.com/datasets/v9grvgsrh9/1>: "benchmark for rock blasting", DOI 10.17632/v9grvgsrh9.1, images of blast piles, muck, haulage and fragmentation with COCO annotations.

No open tabular dataset of drill and blast cost, deviation or cycle time was found; the open material is images and textbook method, which is why the demo is synthetic. The images are a bonus, not a dependency.

**(b) Synthetic generator.** Reference bench: 12 rows of 4 holes, burden 3.2 m, spacing 2.9 m, bench 15 m, 102 mm holes, 2.70 t/m3, 18,040 t. Rate card (Inference throughout): explosive €2.70/kg, drilling €4.50/m, detonator €25/hole, charging labour €40/hole, load and haul €1.80/t, crush €0.90/t, secondary break €6.50/t of oversize, €800 fixed per bench.
Physical structure (Inference unless sourced):
- charge = powder factor x hole volume, powder factor drawn 0.5-1.1 kg/m3;
- fragmentation as a Kuz-Ram style x50 from rock factor, charge and explosive strength, with a Rosin-Rammler spread; oversize is the fraction above the crusher opening;
- saturating response, so the marginal kilogram buys less and less fragmentation: the economics the optimiser works on;
- vibration from scaled distance (charge per delay, distance) as a hard constraint; deviation tail-heavy, short stemming in 4% of holes, charge error in 3%; cycle hours from tonnes plus an oversize penalty; fume clearance 30 minutes (fumes sourced, the 30 minutes Inference).

What a company plausibly hands over, and what we can fake in two hours (record types real, per the sources; contents Inference):

| Handed over | 2 h | How |
| --- | --- | --- |
| Bench design plan, CSV/XLSX | 30 min | seeded grid generator |
| Downhole deviation survey, CSV | 20 min | design plus angular and depth error |
| Charging record, CSV | 15 min | planned kg, noise, faults |
| Detonator timing log | 15 min | delay table |
| Cost and production report, XLSX | 20 min | rate card with ranges |
| Fragmentation photos, orthophoto | no | needs real images; the Mendeley set if licence allows |

**(c) Restricted-data rules.** Their data stays in one room, on one laptop volume outside the checkout. No screenshots, no paste into a chat model, no cloud upload, no printouts. Nothing derived from it is committed; calibration may inform only rounded parameter bands, and only with written permission, after which the README says "ranges from industry practice and a private calibration, no client data". Ask FORCIT for a written public one-paragraph description, permission for that calibration sentence, the scored metric, one labelled bench if it can be shared, and what must not appear in the video. If they say no to all of it, the build does not change: the demo runs on our data either way.

## 7. Build plan to freeze

| Milestone | Clock, hour mark | Done when | Box |
| --- | --- | --- | --- |
| M0 scaffold | Fri 19:30 (H+0) to 20:30 | `make demo` opens a page with 48 holes from a committed JSON, offline | 60 min |
| M1 model | 20:30 (H+1) to 22:30 | powder factor moves cost/t and x50 the right way, and one hand calculation matches the code | 120 min |
| M1 loop | 22:30 (H+3) to 00:30 | the 6-click demo runs three times in a row, offline, on battery | 120 min |
| M2 proof | Sat 00:30 (H+5) to 02:30 | `make eval` prints median, shuffled control and violations in under 60 s | 120 min |
| Stop line | Sat 02:30 (H+7) | sleep, 4 off, 1 on call | 4.5 h |
| M2 polish | Sat 07:00 (H+11.5) to 10:00 | reasons, compare view, sensitivity table on screen | 180 min |
| Q&A, then model freeze | 10:00 (H+14.5) to 15:00 (H+19.5) | metric confirmed or changed, answers in the README, no physics after 15:00 | 300 min |
| M3 video and README | 15:00 (H+19.5) to 18:00 (H+22.5) | 4 takes, one edit, under 2:00; README runs from a clean clone | 180 min |
| Q&A 2, then submit-ready | 18:00 (H+22.5) to 22:00 (H+26.5) | public-safe wording approved, submission fields drafted, no code changes | 240 min |

Cut order: emissions and vibration panels at H+5 if the model slips; cycle hours at H+11.5; the compare view at H+16.5; the firing animation at H+19.5, with a static before and after in the video. The optimiser is never cut, because without it the claim shrinks to "the mistake costs €0.22/t". If the loop is not working at Sat 02:30, we sleep, finish it between 07:00 and 10:00, and put one number on screen instead of the evaluation table.

## 8. Default stack and what we cut
- Python 3.12 and uv; numpy and pandas; scikit-learn for IsolationForest only; the optimiser is numpy.
- FastAPI on 127.0.0.1:8000, serving JSON and the built SPA from one process and one port.
- React and Vite with Tailwind; Recharts for the fragmentation curve; plain SVG for the plan and the firing section.
- JSON fixtures in `fixtures/synthetic/`, produced by `make data` from a committed seed; no database. (`data/` is gitignored, so fixtures live outside it.)
- `make demo`: uv sync, make data, build the SPA if missing, start uvicorn. One command, no network, no keys.
- Video: OBS or ffmpeg x11grab, 1080p, under 2 minutes; the README is the only document.

Cut: any FORCIT data in the product, training beyond the anomaly layer, 3D and point clouds, drone imagery, live sensors, cloud, login, a database server, LLM chat, mobile layout, an emissions module unless FORCIT names it, any deck over 5 slides.

## 9. Risks and kill criteria

| # | Risk | Mitigation |
| --- | --- | --- |
| 1 | The brief needs their data for the core answer | The product is a simulator plus a decision layer; their data is calibration, never dependency. If the scored deliverable cannot exist without their numbers we lose the company gate but keep a demo and a video. |
| 2 | The vote: 1,000 builders, 20 seconds, unknown domain | Three numbers, one hole turning amber, one second of sound; no jargon in the first 10 seconds. |
| 3 | An expert calls the physics shallow | Say it is a transparent approximation, show sensitivity and the shuffled control, make the decision layer the contribution. |
| 4 | Overfitting our own generator | 50 held-out benches, a shuffled control, and the control printed on the evaluation page. |
| 5 | Wifi, dependencies or scope at build time | Warm uv and node caches before Friday, one airplane-mode run, no CDN assets, one screen, features frozen Sat 22:00. |
| 6 | NDA signing splits the team | One named signer, paper ready at 18:50, the other four start M0 at 19:30 without them. |
| 7 | Safety optics around explosives | No real coordinates, site names or security detail; synthetic "Bench 14"; the subject is cost and safety decisions. |

Go/no-go, 10 minutes, 18:50 to 19:00, before signing:

| Check | Select if | Drop if |
| --- | --- | --- |
| Scored output | one number is named in the first 3 minutes (cost/t, oversize, deviation, cycle hours) | "we will know it when we see it" |
| Data shape | hole-level or bench-level tabular data, at the briefing or by Sat 09:00 | a cloud system, or data arriving Saturday afternoon |
| The ask | decision support over the cycle | a dashboard over their data |
| Synthetic demo | accepted, and they will judge the method | "the demo must use our numbers" |
| Public line | a one-paragraph public description is possible and approvable | everything, including the problem, is confidential |

4 of 5 select and zero drops means sign and build. One drop means do not sign: stay at M0, aim at the company gate with the synthetic demo, and the lead records the loss. Two of us wanted this; that is the bar their interest has to clear. Selection is final at 17:30, before the briefing, so choosing FORCIT takes us out of the queue for Valmet, Traficom and Business Turku, whose places may be gone by Friday afternoon: the downside is not €1,000 but a weekend on a challenge we cannot score. That is why a pre-check runs at 16:45 to 17:15 with what is public and whoever is at the FORCIT stand, and 4 of 5 must be answerable there.
Stop hour: if the loop does not run offline by Sat 02:30, we cut to the anomaly plus the cost of the mistake and ship that smaller story at 22:00.

## 10. Questions for the partner Q&A
Saturday 09:00 to 12:00, Joki. Ask what they score, not what to build.
1. When you rank the top three on Sunday, what do you look at first: the running demo, the README, or the video?
2. Two teams reach the same number, one on real data and one on synthetic. How do you break the tie?
3. Which result would you put in front of an operations manager on Monday: lower cost per tonne, less oversize, or a shorter cycle?
4. What mistake do you expect teams to make about blasting? We would rather hear it now.
5. What single number from a simulator would you compare with your own experience before believing it?
6. Do you want to approve our public-safe paragraph before Sunday 10:00, and who signs it off?

## 11. How it scores: company vs participant vote
Company gate. "Works and answers the brief" stays open until 19:30 and no plan closes it. Relevance and business value are our strong claim: 5.7% off the fixed-rule plan is €4,700 on this bench, and the same rate on 200,000 t a year is about €52,000 (our arithmetic on our own simulated rate, not a FORCIT figure). Technical quality is real but modest: closed-form model, constrained search, anomaly layer fitted at startup, held-out evaluation with a shuffled control. Understanding the system is the gate we can lose; a blasting engineer will know in two questions whether we have stood on a bench, so one of us spends Saturday morning with a domain person. Responsible data handling is the strongest answer in the room: we never needed their data, and we can say exactly what we would and would not do with it.

Participant vote. This is the weakest vote story of the 15 unless the demo is physical and loud. There is no product to touch, the domain is unfamiliar, and the result lives in a unit a voter does not use. In a 20 second comparison, a pattern of dots and a euro figure lose to a face, a map or a robot. The narrow mitigations: the hole turning amber, one second of the shot with sound, the fall from €4.76 to €4.28 in text readable at arm's length, and a video that opens with the blast rather than the architecture. If the animation does not land in the first 10 seconds, the vote is gone whatever the model does. Expected value: first prize is €3,000 against €2,000, so the premium is €1,000, or 50%, and any drop of more than a third in our chance of a scoreable demo cancels it. Against that, selecting blind and a thinner vote story are both real. This is a bet on the best brief of the weekend, not on the best odds.

## 12. IP, NDA and data handling
- IP, from the public summary: "Your team owns what you build. FORCIT Group can use it only to evaluate the event and for internal decision-making. Wider use is agreed directly with your team." Every member ticks this personally before submission.
- NDA: paper, signed on site with a FORCIT representative at the Friday briefing, before any data; selecting the challenge is not signing it. Read the confidentiality term, ask for a copy, record who signed for FORCIT, and sign only after the go/no-go.
- Restricted data: never in the repo, the video, the deck, the submission text or a model prompt. Not committed, not filmed, not screenshotted. In the room only, on a laptop volume outside the checkout, wiped after the event; our notes record what we received, not what it said. Video and deck use the synthetic run only, no FORCIT logo (the name in text is enough), no site names or coordinates.
- Derived work: rounded parameter bands only, with written permission; no client figures, verbatim tables or fitted coefficients that can be inverted.
- Repo: `restricted/` and `challenge-material/` stay gitignored; the README states "synthetic data only, no client data"; the generator and seeds are the evidence.
- Public-safe summary, about 90 words, for FORCIT to approve: "Blasting is planned days before a shot, from a pattern and estimates. Our prototype takes a bench plan, a measured hole survey and a cost card, prices the effect of deviation and overcharge per tonne, then searches for a cheaper admissible pattern and shows the change before firing. On a synthetic bench: €4.76 to €4.28 per tonne, oversize 13.2% to 6.9%. No client data was used; the model, the rock and the rates are synthetic, and the method is what transfers."
