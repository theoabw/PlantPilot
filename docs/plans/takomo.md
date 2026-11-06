# Takomo Golf: Personalised golf club fitting
**Tier:** fallback. **Verdict:** bid as the fallback: one night buys a working simulator on the company's own published catalogue, but Takomo already ships an iron fitting quiz, so the win must come from numbers that quiz does not print. Written Thu 5 Nov 2026 from the public summary only.

## 1. The 20 second story

A 20 handicap golfer who slices will never book a launch monitor session. He answers six questions, gets his full iron spec, and watches his next 100 shots land twice: once with the stock set, once with his set. The slice is 34 m wide in the first and 24 m wide in the second, and his clubs stop bunching at the short end. One screen, two clouds, two numbers. It is a simulation and it says so, which is why the comparison is worth reading.

## 2. What the company said, and what we infer

Task sentence, verbatim from the summary: "Explore how AI could make personalised club fitting more accessible using relevant player characteristics and performance signals."

What is already public, opened in this session: Takomo sells nine iron head models (Iron 101 MKII, 201 MKII, 201T MKII, 301 CB, 301 MB and 301 COMBO, plus the older 101, 101T and 201), wedges SF001 and SF002, a driver, a utility iron and gloves, direct to consumer, and it already runs a "Takomo Iron Fitting Tool" described as "answer a few quick questions, receive a 100% accurate, legally-binding iron recommendation. Just kidding". Its published "who should play" bands run from "High to Mid Handicap" on the 101 MKII to "Scratch" on the 301 MB.

Inference:
- The existing tool is a lead form: it answers a product name, not a measurable outcome, and it cannot be argued with. A golf judge will notice the difference only if we print carry, dispersion and gapping.
- A direct-to-consumer brand cannot measure the player, so the only inputs it can honestly use are the ones a customer can supply at home: handedness, handicap, height, wrist-to-floor, typical miss, and a swing speed if the customer happens to know it.
- Their two levers are model choice (7 iron loft 29 to 34 degrees, offset 1.8 to 3.4 mm) and shaft choice (KBS Tour for faster swing speeds, KBS Tour Lite for beginners and lighter, per their own page text). Any fitting engine that does not use both levers is choosing one club feature out of two.
- Wrong fit costs a D2C brand money twice: a return, and a customer who blames the club for his own slice. Both are measurable, and neither is measured today.

Confirm at the Friday briefing:
1. Does the brief accept a physics simulation, or does it demand measured player data?
2. What can production actually change: lie angle range, length options, loft bending, grip sizes? The recommendation must stay inside that set.
3. Are the full spec tables for all nine models available as a sheet, or do we copy them from product pages?
4. Is there any anonymised shot data (fitting sessions, returns reasons, exchange rates) we may use at the event, and on what terms?
5. Does judging compare our recommendation with their fitting tool's answer for the same golfer?
6. May we name their products, print their spec tables and show the tool in a public video and repo?

## 3. The 90 second demo

1. Laptop on the table, wifi off, browser at 127.0.0.1:8000. One screen: six inputs left, three views right, a line reading "simulated ball flight".
2. Enter the golfer: right handed, handicap 20.4, 181 cm, wrist to floor 88 cm, typical miss a slice, clubhead speed "unknown". Press Fit. This is the no launch monitor case and it is the default.
3. In about a second the spec appears as a card: 101 MKII 5 to GW with the full loft set from their published table (7 iron 29 degrees), KBS Tour Lite Regular at the weight on the manufacturer sheet, standard length or 0.25 in short, lie 1 degree flat if production allows, Lamkin Crossline midsize. Each line carries its reason ("offset 3.4 mm against a slice, 29 degree 7 iron for a slow swing").
4. The stock panel draws 100 shots; the cloud walks right and the badge reads 34 m wide. The fitted panel draws 100 shots, badge 24 m. Same seeds, same golfer, so the only difference is the clubs.
5. The side view animates one 7 iron flight per set, about four seconds, with the landing mark labelled in metres. This is the moment something visibly happens.
6. The gap ladder: seven bars, stock gaps (expected, from the published 3 and 5 degree loft steps) about 8, 8, 9, 13, 13, 14 m, fitted gaps 11 to 13 m. The short bar that was 8 m turns green.
7. Optional seventh input: paste a 7 iron launch monitor line and the model re-anchors to his real numbers.

Live: steps 1 to 6, computed on the laptop by FastAPI and Python in about a second, no network. Precomputed: the 200 golfer proof table, which the judge can recompute in about 40 seconds. Replay: a recorded JSON of the same run, used if the machine misbehaves; it is the same numbers, not a mock.

## 4. The proof number

The claim: across 200 synthetic golfers fitted only from the six answers, the 7 iron landing pattern's 90% lateral width falls at least 20% against the named stock set, and every adjacent carry gap in the recommended set lands between 10 and 14 m.

Baseline: Iron 201 MKII, 4 to PW, KBS Tour Lite Regular, stock lie and length. That is the company's own "Mid Handicap" answer, so the baseline is their default, not a straw man.

The 34 m to 24 m in section 3 is the target that would produce this claim, not a measured result. Nothing here has been run yet.

How it is measured: 100 flights per club per set, common random seeds per shot so the difference comes from the clubs and not from luck. Metric 1 is the width in metres containing 90% of lateral landing points. Metric 2 is the six adjacent carry gaps in metres and their spread, maximum minus minimum.

On what data: the published catalogue (verified per club for one head, to verify for the other eight) and 200 synthetic players. No real golfer is measured, and the UI says so.

Win rather than toy: 20% narrower and gap spread under 4 m, held on the 100 players not used to tune the rules, with the model's stock 7 iron carry inside 5% of any real number the company supplies at the briefing. A tool that wins by shortening every club one inch fails the hold-out, and a tool that only renames the stock set is the quiz they already have.

## 5. System design

```
 6 answers  -->  launch model  -->  flight sim  -->  3 views  -->  best spec
 catalogue       (GBM surrogate)   (drag + Magnus)   (scatter,     + delta vs
 (JSON)                             1 kHz, 100 shots  gaps, arc)    stock set
```

- Input form: six fields, React state, JSON profile. Real.
- Catalogue: JSON built from the published per club tables (head, loft, lie, length, offset, shaft model and flex). Real, one model complete, eight to copy.
- Launch model: maps the profile to ball speed, launch angle, spin and spin-axis tilt per club, a gradient-boosted surrogate trained on a synthetic population. Real code, synthetic training data.
- Flight sim: 3 degree-of-freedom point mass, drag and Magnus lift with coefficients interpolated from the cited measured curves and estimated where the curves are unread, spin decay from the cited model, 1 kHz, vectorised across shots. Real maths, estimated coefficients, no wind and no turf.
- Search: exhaustive over about 2,700 specs (9 head models, 6 shaft options, 5 lie steps, 5 length steps, utility iron or 4 iron), each scored by the sim. Real, deterministic, explainable to a golf judge in one sentence.
- Views: plain SVG scatter, gap ladder, side view. Real.
- Mocked: the golfer. Every player, including the demo one, is synthetic.
- Not built: accounts, storage, any network call, any claim of a real fitting.

## 6. Data strategy

(a) Verified in this session. The live site refused with a Cloudflare check (HTTP 403), so these are archived snapshots from 23 and 29 January 2026, nine months before the event, and current line up is to verify at the briefing.
- https://web.archive.org/web/20260123020804/https://takomogolf.com/pages/fitting-tool: the existing iron fitting tool and its tagline; confirms a quiz already exists.
- https://web.archive.org/web/20260123023452/https://takomogolf.com/pages/iron-sets: eight models in its comparison table with type, 7 iron loft, set composition and "who should play" band, plus the direct-to-consumer pricing copy.
- https://web.archive.org/web/20260129181641/https://takomogolf.com/products/iron-201-mkii: the per club table (4 iron 22 degrees, 60.5 lie, 38.75 in, through P wedge 46 degrees, 63.5, 36.00), shaft options KBS Tour and KBS Tour Lite in R, S, XS, swing weight D2 and D1, Lamkin Crossline grips, right and left handed, EUR 649 for 4 to PW.
- http://www.tsfp-conference.org/proceedings/2011/4d2p.pdf: measured drag and lift coefficients for dimpled golf balls over Reynolds 0.5 to 2.7 x 10^5 and spin ratio 0 to 0.5, and the Smits and Smith (1994) spin decay form. This is the only published input to the flight model.

(b) Synthetic population. 200 players sampled over handicap 0 to 36, height 150 to 200 cm, wrist to floor 78 to 95 cm, typical miss neutral, slice or hook, and 7 iron clubhead speed 28 to 40 m/s (ball speed 1.35 times that). The physics is credible because it is standard: a 45.9 g ball at the 42.7 mm rules minimum, air density 1.225, drag near 0.25 and lift near 0.18 at a spin ratio of 0.1 as estimated defaults, to be digitised from the paper's figures if the time exists. Loft to launch and spin, lie to spin-axis tilt, shaft flex to dynamic loft, length to clubhead speed: all four mappings are estimated, each with a stated coefficient, and all printed in one Assumptions panel so a judge can attack them. Since both arms use the same model, model error largely cancels in the delta, which is why the headline is relative and not absolute.

(c) Ask the company for, with deadlines. All nine spec tables and the buildable range (lie, length, loft bending, grips) by H+2, Friday 21:30, or the search space stays at one model. Twenty anonymised fitting or launch monitor sessions by H+9, Saturday 04:30; later than that and calibration becomes a slide, not a result. Return and exchange rates on iron sets by H+3, for the business case in the video. Written permission on product names and spec tables in a public video by H+20, Saturday 15:30.

## 7. Build plan to freeze

H+0 is Friday 19:30. Times are EET.

| Mark | Window | Work | Done when |
| --- | --- | --- | --- |
| M0 | H+0 to H+2 (21:30 Fri) | Repo, uv, FastAPI, Vite shell, catalogue JSON, `make demo` | Fresh clone, one command, page lists the nine models at 127.0.0.1:8000 |
| M1 | H+2 to H+7 (02:30 Sat) | Flight sim, launch model, one golfer end to end, scatter and side view | Six inputs return a spec and two clouds in under 2 s, offline |
| M2 | H+7 to H+16 (11:30 Sat) | Search over the real option space, 200 player run, gap ladder, held-out check | `make proof` prints fitted vs stock for 200 players and the app shows the number |
| M3 | H+16 to H+21 (16:30 Sat) | Video under 2 minutes, README, replay JSON, assets local | Video plays on a phone, a second laptop runs a clean clone with wifi off |
| Buffer | H+21 to H+26.5 (22:00 Sat) | Bug fixes only, no new features | Feature freeze at 22:00, whatever state it is in |

Cut first, in this order: multi-club scatter at H+4, keeping the 7 iron plus one wedge; the gradient-boosted surrogate at H+8, falling back to a hand written launch table; the long irons at H+12, shipping 5 to GW; the launch monitor re-anchor at H+14; the replay mode at H+16 only if the live path is stable.

## 8. Default stack and what we cut

House stack, adjusted to the product. Python 3.12 and uv for the flight model, the launch model and the exhaustive search. FastAPI on localhost serving JSON. One React and Vite front end with Tailwind, all assets local, no CDN. Charts in plain SVG (scatter, gap ladder, side view); no Recharts, because three custom views are less code than fighting a library. scikit-learn only for the surrogate; the search itself is enumeration, because the catalogue is about 2,700 specs and enumeration can be explained to a golfer. SQLite is unnecessary, so the catalogue is one JSON file with a "verified" flag per row. `make demo` starts both processes and opens the browser. No GPU, no deploy, no LLM call in the demo path. The submitted artefact is a recorded MP4 plus the repo README.

Not building: a user account, data storage, a chat interface, 3D rendering, weather or wind, a wedge or putter fitter, a handicap calculator, combo splits between two head models, a mobile app, a recommendation for any model we could not verify, and any claim that a simulated shot is a measured shot.

## 9. Risks and kill criteria

1. The brief is a lead generation ask, not a fitting engine. Mitigation: the engine is the product, the quiz is its front door, and every answer carries a number.
2. No real shot data, so absolute carries are wrong. Mitigation: the headline is fitted versus stock in the same model, so shared error cancels.
3. A golf judge spots an unrealistic flight. Mitigation: one Assumptions panel, stock 7 iron carry sanity band, and a re-anchor path to real numbers.
4. Venue wifi or the laptop fails. Mitigation: no network calls, local fonts and assets, replay JSON, wired test with wifi off at H+16.
5. Eight of the nine spec tables are copied wrong. Mitigation: one source JSON with a verified flag, cross checked against their sheet at the Q&A.
6. IP terms discourage reusing our own existing simulator. Mitigation: a commit at 19:35 Friday marks the boundary, all challenge code is written after it, and any personal library stays in its own repo as know-how only.
7. Scope creep into 3D or a chatbot. Mitigation: one screen, one number, freeze at 22:00 Saturday.

Kill criteria. Switch away if the briefing says the tool must use real customer data we cannot obtain, or that the fitting decision is made in person by a fitter and the challenge wants only a marketing funnel. Switch if the IP terms forbid a public repo or a public video and no written workaround exists by Saturday 12:00. Switch if the buildable range turns out to be one model in one shaft, which leaves nothing to fit. Switch internally at H+7 (02:30 Sat) if the demo loop does not run end to end, and at H+16 (11:30 Sat) if `make proof` has no number.

## 10. Questions for the partner Q&A

1. When you score business value, is it conversion, fewer returns, or a spec that can print on an order form?
2. Will the evaluator put our recommendation next to your fitting tool's answer for the same golfer, and does disagreeing with it count against us?
3. Which of our numbers would you trust in a demo: predicted carry, dispersion width, or the gap between clubs?
4. How much of the score is the working product versus the explanation of the physics?
5. Does responsible data handling mean collect nothing, or show a real-data path we did not build?
6. Would a recommendation that changes what you build (flatter lie, a utility iron instead of a 4 iron) score higher or lower than one that only picks a head?
7. What should the tool say when our simulation disagrees with a customer's real session?
8. Which single number from your business would you accept as the success metric for this?

## 11. How it scores: company vs participant vote

Company gate. It works, it is offline, and it answers the brief with the company's own catalogue and their own shaft rules, which covers "it works" and "understanding the system". Technical quality is real: a vectorised flight model, an explicit option space, a held-out evaluation, and estimated parameters stated as estimated. Privacy is the strongest part of the pitch, because the tool collects nothing and stores nothing. The weakness against the other shortlisted plans is the data story: no measured shots, so every number is model output, and a sceptical evaluator can discount all of it with one question about calibration. Fix by making the relative claim and printing the assumptions.

Participant vote. This is the plan's best gate. Golf is legible, the before and after is two clouds of dots, and the 20 second test passes because a slice moving 10 m left is visible without knowing what a spin axis is. The weakness is relevance to a room of builders who mostly do not play golf, and the risk that a judge reads "simulation" as "made up". Fix by showing the trajectory, the number and the assumed inputs on one screen, and by never calling it a fitting without the word simulated.

## 12. IP, NDA and data handling

Under these terms the work built for the challenge belongs to Takomo Golf. The team keeps its existing code and know-how, which means a clean commit at 19:35 Friday: everything after it is theirs, anything before it and anything imported from a personal library stays ours. Keep a dated commit hash and a one line note in the README, because the boundary will be argued about after the event.

The restriction: the work may not be used after the event without Takomo's prior written consent. That covers more than selling it. Assume it covers the code, the spec tables copied into it, the demo video, screenshots, and any portfolio write up that shows the screens. Practical consequences: the repo must be released under terms the event requires while accepting that we have no licence to reuse it later, so do not plan to build on this code on Sunday or in a job application. Ask in writing at the Q&A for permission to display the demo video and two screenshots publicly as event evidence, and get the answer before the video is finalised at H+20. Do not republish the spec tables as an open dataset.

NDA: none is required by the summary for this challenge, and the team should still not ingest anything the company marks confidential. Data handling: no account, no storage, no analytics, no network call, no personal data collected; the demo golfer is fictional and named as such; if a real golfer is tested on the laptop at the booth, his numbers stay in the browser tab and are gone on refresh, and we say that out loud.
