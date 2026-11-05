# Challenge plans, eight candidates

Written Thursday 5 November 2026, 18:45 EET, from the public summaries alone. The full brief and the company materials open Friday at 19:30, and only for the team that selected that company. This document is the planning head start for the Friday choice: one plan per challenge, a ranked call, and the reasoning the team can disagree with.

The eight are the challenges the team named in chat: Valmet, FORCIT Group, Europress, Traficom, Takomo Golf, Turku Energia, Elisa and Business Turku. The other seven summaries are in [challenge-summaries.md](challenge-summaries.md) for reference.

Each plan follows the same twelve sections and is written to be read alone:

| Challenge | Tier | Plan |
| --- | --- | --- |
| Valmet | bid candidate | [plans/valmet.md](plans/valmet.md) |
| Traficom | bid candidate | [plans/traficom.md](plans/traficom.md) |
| Business Turku | bid candidate | [plans/business-turku.md](plans/business-turku.md) |
| Turku Energia | fallback | [plans/turku-energia.md](plans/turku-energia.md) |
| Europress | fallback | [plans/europress.md](plans/europress.md) |
| Takomo Golf | fallback | [plans/takomo.md](plans/takomo.md) |
| Elisa | fallback | [plans/elisa.md](plans/elisa.md) |
| FORCIT Group | fallback | [plans/forcit.md](plans/forcit.md) |

## 1. What the team said, and where that leaves the choice

The chat names, in order of appearance:

| Time | Who | Named |
| --- | --- | --- |
| 15:14 | Jonas Klinga | Valmet, FORCIT Group, Europress, Traficom, Takomo Golf (his top five, no order) |
| 16:08 | Bolex | Valmet, FORCIT Group, Traficom, and Turku Energia |
| 16:32 | Mirek Kudinoff | Elisa, with the reservation that it is "kanske lite mundane" because it is documentation work |
| 18:24 | Theo Wilenius | Valmet, Traficom, Business Turku |

The tally is Valmet 3, Traficom 3, FORCIT Group 2, and one each for Business Turku, Turku Energia, Europress, Takomo Golf and Elisa.

The card committed at 18:26, [challenge.md](../challenge.md), has Valmet, Traficom and Business Turku, with Traficom as the lean. Two members of the team have named FORCIT Group, which the card leaves off entirely. One member named Business Turku, which the card puts third. That is the substantive disagreement in the room, and it is worth resolving before Friday rather than in the selection window.

The card also contradicts itself on the order: its table puts Valmet first, and the paragraph under it says "Lean: Traficom first". This document takes the lean at its word and recommends Traficom first, with the reason in section 5. If the team prefers Valmet, change that sentence and the order here tonight, so the lead is not deciding under time pressure at 15:00.

The case for FORCIT is the money: €3,000 for first place against €2,000. The case against is in section 5, and it is stronger than it looks, because of a scheduling fact the card does not yet account for.

## 2. The scheduling fact that changes the decision rule

The card's decision rule says the Friday brief must support the direction. The published schedule does not allow that test to happen before the choice:

- Friday 15:00 to 17:30: the lead marks the team ready, then selects the challenge. No changes afterwards.
- Friday 17:00 to 17:30: opening ceremony and challenge intros, selection still open.
- Friday 18:50 to 19:30: company challenge briefing, for teams that already selected.
- Friday 19:30: the full brief and materials open.

So the choice is made before the briefing, from the same four-line summaries we have tonight, the stage intros, and whatever the team already knows about the company. The 18:50 briefing and the 19:30 materials arrive after the commitment. They can change scope, not company.

Three consequences, and they drive everything below:

1. **A kill criterion is a scope decision, not a switch.** If the brief disappoints at 19:30, there is no other challenge to fall back to. The reaction has to be "which of our planned demos still answers a defensible reading of the summary", not "let us pick something else".
2. **The choice must be robust to being wrong.** That favours challenges whose summary is broad enough that two or three different demos all count as answering it. Traficom, Valmet and Business Turku are all in that group. A narrow summary is a trap.
3. **First come, first served means the order matters more than the list.** If Valmet is full at 15:10, the team needs a pre-agreed next name and no discussion. The lead selects, so the lead needs the order in hand before 15:00.

The corollary for FORCIT is blunt. Selecting it means committing at 15:00, signing a paper NDA around 18:50, and first learning what the task really is at 19:30. That is not a bet with a briefing as its safety net. It is a bet on the summary alone, four lines long, deliberately written to say nothing. The extra €1,000 against the chance of a bad fit is a poor trade for a team that wants to demo.

## 3. Baseline expectations every plan is held to

These come from the event rules, not from taste. A plan that cannot meet them is not a plan.

- **A working prototype beats a deck.** Every plan ends in something visible on a laptop, driven by a person, in under two minutes.
- **One demo path.** If the demo needs more than one screen and one interaction, the second screen is cut.
- **Measurable, not asserted.** Each plan names one number and its baseline. "78 percent detection at 3 percent false alarms, against 41 percent for the energy detector" is a result. "Advanced AI" is not.
- **No challenge-specific data dependency.** The materials may be empty, late, NDA-bound or in a format we cannot parse. The demo has to run on data we can generate or download ourselves.
- **The vote is the gate to the finals.** Roughly 1000 builders compare projects pairwise, one finalist per challenge. A domain expert's demo that a tired builder cannot parse in 20 seconds loses to a simpler one that they can.
- **Company judging weighs understanding and responsible data handling, not only the model.** Interviews with the team explain the system, and a clean repo with a real README score.

## 4. Comparison, as planned before the briefs

The numbers come from the eight plans, not from the companies. "Hours to demo" is team hours from Friday 19:30 to the first end-to-end run, not to polish.

| # | Challenge | Prize | Verdict | Hours to demo | Data we can get | Hardest part | Weakest gate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Traficom | €2,000 | bid | 6, and 11 to judge-ready | synthetic signals for the demo; Traficom's real station and licence feeds, verified today | a detector that survives the synthetic-signal objection | the brief may be regulatory |
| 2 | Valmet | €2,000 | bid | 7 | Valmet's public 170 page flow control manual and its VMR003 service table, verified today | OCR on printed plates in venue light | the asset register is invented |
| 3 | Business Turku | €2,000 | bid | 9 | public machine data for the model, a staged fan for the demo | the induced fault has to separate from sensor-position noise | the vote, for lack of novelty |
| 4 | Turku Energia | €2,000 | pivot | 6 | real Fingrid load series and FMI weather, verified today | not losing to Fingrid's own day-ahead forecast | a chart is not an event |
| 5 | Europress | €2,000 | pivot | 11 | synthetic fleet, OSM basemap | the saving number, when the company already advertises the optimisation | least differentiated |
| 6 | Takomo Golf | €2,000 | pivot | 7 | published spec table and drag and lift curves, no shot data | simulation credibility without real shots | weak AI content, full IP transfer |
| 7 | Elisa | €2,000 | pivot | 8 | synthetic only, the company publishes no site data | beating BM25 by a factor of 2.5 on held-out incidents | the vote, and the novelty |
| 8 | FORCIT Group | €3,000 | pivot | 7 | synthetic only, restricted data cannot ship | selecting blind | everything before 19:30 |

What the plans changed from the first read:

- **Traficom's planning layer is real, not aspirational.** The plan hit the live OData feed, and I re-ran the query: exactly nine FM transmitters in Turku, 89.0 to 105.5 MHz, 1 to 3 kW, owners Bauer, Basso, NRJ and Livelaboratorio. The station register also carries per-azimuth radiated power and antenna height, which is what a link budget needs.
- **Valmet's document half is real too.** The plan found the public flow control manual, 170 pages, 7 MB, and the VMR003 service recommendation with real inspection intervals by DN range. I checked both URLs: HTTP 200, `application/pdf`. That closes most of the gap to Traficom, and it means the demo's "page 47 of the real manual" is not a mock.
- **FORCIT's build is quick, seven hours to a working demo,** because it is all simulation. That is also the problem: fast, and blind.
- **Europress's plan found that Europress already advertises the route optimisation** we would claim as the insight. That is why it stays fifth despite a decent number.
- **Takomo already ships a fitting quiz,** so the plan's win has to be numbers the quiz does not print (dispersion width and carry gapping), not a better questionnaire.
- **Business Turku needs nine hours, not five,** to the physical loop, which is the real cost of the strongest vote asset.
- **Elisa has no company data available** and its plan says so, which makes it a demo built on a synthetic corpus we also have to justify.

All eight plans were written to the same twelve sections, scanned for banned dashes (clean), and their data instructions corrected where they conflicted with this repo's `data/` and `*.onnx` rules.

## 5. Ranked call

This is a recommendation with reasons, not a lock. The lead selects on Friday; the team's job tonight is to say where this is wrong.

Each plan also grades its own challenge, and six of the eight conclude "bid" (Traficom, Valmet, Business Turku, Europress, Takomo Golf, FORCIT). That is expected: a plan that makes its own case well should end up believing it. The order below is the portfolio view, where the eight compete for one slot and the participant vote is treated as the gate it is, so a plan's own verdict and its rank here can disagree without either being dishonest. Read them together: the plan tells you how to win that challenge, this section tells you which challenge to win.

**1. Traficom.** The only challenge where the visible half of the demo needs no data at all: we generate the spectrum ourselves, so the demo cannot be blocked by a missing dataset, an NDA or a parse problem. It gives a genuine model result (detection latency, false alarm rate against a baseline detector), it looks like something happening on screen, and the second layer (interference risk for a proposed assignment) runs on real rows: the agency's station register returned nine FM transmitters in Turku tonight, with power, antenna height and per-azimuth radiation. The summary is broad enough to survive a disappointing brief: detection, characterisation, risk scoring and planning are all defensible readings. It also matches the card's existing lean, so selecting it is not a new argument in the room.
Weakness: if the real brief turns out to be a regulatory process task, the technical demo looks like it answered a different question. Mitigation: build both layers, and lead the pitch with risk scoring, which is planning language, then show the detector as the evidence.

**2. Valmet.** The best 20 second story of the eight, and the only one where the physical world is literally on camera. A phone pointed at a machine tag, then the right document and the next action on screen, is a demo a non-expert understands instantly and remembers. It also turns out to have real documents behind it: the public flow control manual, 170 pages, and a service recommendation with intervals by valve size, both verified tonight. The build risk is mostly staging: print nameplate stickers, tape them to whatever machinery the venue offers, and film.
Weakness: there is still no camera dataset and no asset register, so those two parts are ours to invent, and the demo has to say so out loud. If the brief says the task is document Q&A only, this collapses toward the Elisa problem and the demo gets much less interesting.

**3. Business Turku.** The safest build on the list: one phone on one machine, a signal pipeline, an anomaly score, an alert. Physically present, hard to fake, and cheap. It should be held third rather than first because of the vote: generic predictive maintenance is the most predictable idea in the hall, and winning the company prize requires differentiating on something the plan has to name explicitly. The plan does name it (retrofit, no install, any forty-year-old machine, five minutes to attach). If the team cannot say that sentence with conviction, this is a fourth place finish.
Weakness: no novelty, and the company may have seen ten maintenance dashboards by Saturday.

**4. Turku Energia.** The cheapest real-data head start available to any of the eight, and the only one where the forecast can be honestly validated against public history. Fingrid load data, market prices and weather are all open, and the decision layer turns a chart into euros. It ranks below the three above only because of the vote: uncertainty bands on a chart do not make a tired builder stop scrolling.
Weakness: a chart is not an event. If the demo cannot show a decision being made and a number changing, it will not survive the pairwise vote.

**5. Europress.** Same shape as Business Turku with a better business number (kilometres saved, missed pickups avoided) and a map, which reads well on screen. Below Turku Energia because the data is synthetic and the company is small, so there is less public material to be right about.
Weakness: least differentiated of the operational challenges.

**6. Takomo Golf.** The most fun to build and the best vote story of the fallbacks: a golfer enters their numbers, sees a trajectory, sees the dispersion shrink. But the "AI" is a physics simulation plus a rules engine, the company may read the output as a lead-generation form, and the IP terms hand the work to Takomo with no use after the event. It wins if the brief turns out to be about the fitting logic itself. It is not worth a top three slot on a summary this thin.

**7. Elisa.** The teammate who named it called it mundane, and that instinct is right. "Capture know-how from chats" is the most crowded idea of the weekend, and a knowledge graph is a thin defence against a hall full of RAG chatbots. Last of the fallbacks with a real company.

**8. FORCIT Group.** Highest prize, best-funded challenge, and the only one where the team cannot know what it is building before committing. Two teammates named it, so it deserves a real analysis rather than a dismissal, and the plan provides one: a synthetic blast-cycle simulator that answers a defensible version of "safer, smarter decision-making in demanding industrial operations" without any FORCIT data, plus a ten minute go/no-go checklist. But the checklist has to be run at 15:00 with no information, which makes it a coin flip with a €1,000 bonus. The team's remaining weekend is worth more than that.

The order above is what the lead should carry into Friday: **Traficom, then Valmet, then Business Turku, then Turku Energia**. The last four are recorded so that a last-minute change of heart is still an informed one, not so that they get picked.

If the lead's own judgement differs, the one thing not to do is open the selection window without an order. The slot allocation is first come, first served, and a ten minute argument at 15:10 is how a team ends up with its fifth choice.

### The seat that is actually scarce

Both halves of the demo can now be generated: agents write the pipeline, and ElevenLabs or similar narrates the video. That moves the scarce work rather than removing it.

What a voiceover cannot do is answer a question. The company evaluates "how well the team understands and explains the system", and the evaluators talk to the team at the Saturday Q&A windows (09:00 to 12:00 and 14:30 to 18:00), then to a finalist for six minutes after the pitch. So one person still owns the claim: they sign off the numbers `make proof` prints, they decide at H+18 that the measured result missed the win bar, and they rewrite the script to match. An agent can generate ten scripts; it cannot decide which one is honest.

The second consequence is ordering. A synthesised voice depends on a finished script, and the script depends on the measured number, which arrives around H+18 to H+21. Narration therefore moves the writing earlier rather than saving the evening. Draft the 90 second script tonight with placeholders for the two numbers, and record the voice last.

## 6. Friday protocol, by the clock

| Time | Action | Owner |
| --- | --- | --- |
| Thu evening | Read this page and the one plan for your preferred challenge. Disagree in chat, not at 15:00. | everyone |
| Fri 14:45 | Meet outside, 15 minutes: confirm the order, confirm who selects if the lead is delayed. | whole team |
| Fri 15:00 | All members check in in person at EduCity. No check-in, no team. | everyone |
| Fri 15:00 to 15:20 | Lead marks the team ready and selects the first available name in order. Do not wait for the intros. | lead |
| Fri 15:20 | Post the chosen challenge in the team chat, with the plan link. Start the pre-build list in section 7. | lead |
| Fri 17:00 to 17:30 | Opening and challenge intros. For our company only: write down every number and criterion stated on stage. | one note-taker |
| Fri 18:50 to 19:30 | Company briefing. Write the criteria verbatim into [challenge.md](../challenge.md), not a paraphrase. Sign nothing that was not read. | note-taker |
| Fri 19:30 | Read the real brief. Compare it to the plan's section 2 and section 9. Re-scope to one demo path. | whole team |
| Fri 22:00 | Something that runs end to end exists in the repo, even if it is ugly. | builder |

The 17:00 intros are the last new information before the lock. If a company says something on stage that contradicts its summary, that is the moment to change the order, and it is the only moment.

## 7. Pre-build list for tonight and Friday morning

Cheap, reversible, and useful whichever challenge is chosen. Anything downloaded or written before the event is pre-existing work and must be declared in the submission.

- [ ] Fix the two checker failures now, not Sunday: push the repo and add the remote, add a LICENCE once the IP terms are known. Run `node scripts/sinceai_check.mjs`.
- [ ] Add `.env.example` with every variable name and no values.
- [ ] Scaffold the house stack once, on a branch, so Friday 19:30 starts from a running app rather than from `npm create`.
- [ ] Download the public extracts into `data/` (gitignored) with a committed fetch script, plus one small fixture in `fixtures/` under 256 KB. Never commit the extract, the model weights or anything large: the checker fails a tracked file over 1 MB and warns over 256 KB.
- [ ] Warm the caches: OSM tiles for Turku, any ONNX model weights, one working Gemini call with a key in `.env`.
- [ ] Print a sheet of nameplate stickers if Valmet is the pick: twenty tags, one per photo, plus one damaged tag to test OCR failure.
- [ ] Charge two phones and pack a tape roll, a fan, and a cable for the Business Turku staging.
- [ ] Dry run `make demo` from a clean clone. A setup that only works on one laptop is a Sunday failure.
- [ ] Claim the ElevenLabs Creator month through its own Discord process before the event, and test one generation on a script that contains a real number. Disclose the tool in the submission's GenAI field, and check the MLH ElevenLabs category on the same form.
- [ ] Fix the video method now, because it decides the Saturday schedule: PowerPoint, a screen recording of the real page, ElevenLabs voice. That is the pattern the team won the Kongsberg grand prize with last year, and it costs an evening, not a filming shoot. What it cannot survive is a weak first sentence, so the screen recording has to show the product doing the thing before any slide title.
- [ ] Draft the 90 second script now, with the two numbers left as placeholders. Sunday morning is for editing, not writing.

### Data leads verified tonight

Three of the eight have a real public-data head start, and all three were checked on Thursday evening rather than assumed:

- **Traficom:** the agency publishes spectrum open data over OData v4 at `opendata.traficom.fi`. The useful dataset is "Radio stations in Finland": station name, location, technical details and licence details, updated daily. Also there: the frequency allocation table, TV stations, and the free frequencies for radio microphones. Opened at [tieto.traficom.fi/en/open-data](https://tieto.traficom.fi/en/open-data). This turns a Turku map of licensed transmitters into real data, with the detector as the validation layer.
- **Turku Energia:** Fingrid Open Data is a real REST API with free registration, covering consumption, production and forecasts, and it is the natural input for a Finnish load forecast. Opened at [data.fingrid.fi](https://data.fingrid.fi/en/). Register and pull a two year extract tonight, not on Friday.
- **Valmet:** the flow control division publishes real documents, not a marketing shell: a 170 page flow control manual ([PDF](https://www.valmet.com/globalassets/sharepoint/imported/flowcontrol_manual.pdf), 7 MB) and VMR003, an application-based service recommendation with inspection intervals by valve size ([PDF](https://www.valmet.com/globalassets/sharepoint/imported/vmr003en.pdf)). Both returned HTTP 200 tonight. The manual is all rights reserved, so the PDFs and the extracted text stay out of the repo and only short quotes ship.

Attribution matters for all three: state the source and licence in the README, keep the extract in `data/` where it is gitignored, and commit only the fetch script and a tiny fixture.

## 8. The house stack, so Friday has one fewer decision

Every plan is written against this. Deviate only where the challenge forces it, and say why in the README.

- **Python 3.12 with uv** for anything numeric: signal processing, simulation, forecasting, anomaly detection. FastAPI on localhost serving JSON, one endpoint per view.
- **One React front end**, Vite and Tailwind. Charts in plain SVG or Recharts. Maps in Leaflet with OpenStreetMap tiles cached locally, because the venue wifi is shared and unreliable.
- **scikit-learn** for classical models. A small ONNX model, or the Gemini API for language and vision, with the key in `.env` and the call on the backend only. Every model call has a recorded offline fallback.
- **SQLite or small parquet files in `data/`, which is gitignored.** Commit the fetch script and one tiny fixture under `fixtures/`, so a clean clone still runs the demo offline. Do not commit the extract itself, and do not commit model weights: `*.onnx` and `data/` are both ignored, and the submission checker enforces the size rules. No database server, no Docker, no message queue.
- **One `make demo`** that starts the server and the front end on a laptop, with a `DEMO=1` replay mode that shows a recorded good run if live compute fails on stage.
- **The submission is the repo plus a two minute MP4.** No deploy requirement, so nothing is spent on hosting. Do not discover on Sunday that the demo needs the internet.

**The data rule, which overrides any plan that says otherwise.** `data/` and `*.onnx` are gitignored in this repo, and the submission checker fails any tracked file over 1 MB and warns over 256 KB. So no plan ships an extract, a model file, a recording or a PDF: each one fetches into `data/` with a committed script, and only text fixtures under 256 KB live in `fixtures/`. Where a plan says "committed data", read it that way.

## 9. What would change this document

- The company says something on stage at 17:00 to 17:30 that contradicts its summary.
- A plan's writer finds that a challenge's public data does not exist or is unusable, which drops that challenge.
- The team is not unanimous on the first name. Then the order changes tonight, not at 15:05.
- The roster is not five people after check-in. Then cut the last fallback first, and keep the read depth to the top three.
