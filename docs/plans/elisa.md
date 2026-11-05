# Elisa: Capturing network operations know-how
**Tier:** fallback. **Verdict:** Pivot or drop: a cited cause trail with a measured replay is the only version worth building, and it still has the weakest vote story of the eight. Written Thu 5 Nov 2026 from the public summary only.

## 1. The 20 second story

A cell site dies at 02:00. The engineer on call knows the alarm, not the cause, so the fix goes through the ticket system and then through whoever is awake. This tool answers with receipts: "This alarm pattern happened 3 times before. Twice it was a broken part at the mast, once a wrong setting on the neighbouring mast. Here are the 3 cases, what was tried and failed, the fix that worked, and who did it, each linked to the sentence it came from." One bar chart closes it: on 120 incidents it never saw, it names the right cause first 2.6 times as often as keyword search, and every sentence it writes has a source. The ratio is the target we measure in section 4, not a result we have yet.

## 2. What the company said, and what we infer

Task sentence, verbatim from the public summary: "Essential know-how in network operations often lives in everyday discussions rather than formal systems. Explore how AI could capture and connect that knowledge to support more autonomous operations."

Opened and verified this session (URLs in section 6):
- Elisa Oyj is a Finnish telecom and entertainment provider: consumer mobile and home broadband, plus carrier services including mast site services and site surveys. It runs a public coverage map and a public fault map, "Verkkoapuri ja häiriökartta".
- Elisa's own article of 18 Aug 2026 says its network has moved toward autonomous operations for over a decade, that faults are down by over 83 percent while traffic multiplied, and that an AI agent now spots an anomaly, analyses the cause and starts the fix before the customer notices.

Inference:
- Detection and repair are largely solved in their own story. The residue is what is left: new fault shapes, cross-vendor cases, and the reason one fix was chosen over another. That is where a human still reads chat.
- "More autonomous operations" in their scoring likely means the next step after their agents: a machine-readable cause record an agent can act on, not a chat window for humans.
- The know-how sits in chat, ticket resolution notes, and shift handover. Only the first two are capturable in one night.
- A RAG chatbot over a wiki adds nothing they cannot buy. The gap is a cause record with provenance and a measured hit rate.

Confirm at the Friday briefing (each answer changes the plan):
1. Does the full brief ask for explanation, or for autonomous action on the network?
2. Which artefact would they show their own leadership: a UI, or a cause record an agent consumes?
3. Will they supply real incident threads, and under what redaction?
4. Do they score a measured result, or a walkthrough?
5. Which alarm and cause vocabulary do they use (TMF642, X.733, vendor codes), and does an internal knowledge tool already exist?

## 3. The 90 second demo

Live unless marked replay. One laptop, no network, a "synthetic data" banner on every screen.

1. Open on a held-out incident: "TKU-KUP-3, 21 alarms in 90 s, cell out of service, uplink loss of signal". Click Analyse.
2. The graph draws itself: 21 alarm nodes collapse into 3 past incidents, then into 2 causes with counts, "faulty optical module 2, neighbour relation mismatch 1". This is the visible moment: 21 becomes 3 becomes 1.
3. Click the majority cause. Three cited threads open beside it with the decisive sentence highlighted, plus ticket id, date, time to fix, and the failed attempts: "restarted the card, it came back, failed again in 10 min".
4. Ask the follow-up a person actually asks: "what did we try that did not work?" The answer is a list, every item linked.
5. Click any sentence: the source span opens. Click a claim with no span: the UI refuses to render it. Say that out loud.
6. Scoreboard (replay, recomputed by `make eval`; target numbers, not measured yet): cause named first, ours 0.60 against keyword 0.23; top three 0.88 against 0.50; unsupported claims 0 of 214.
7. Switch to the keyword view: 40 unordered hits, no cause, no ranking. Ten seconds, then stop.

Live: retrieval, graph, citations, template answer. Replay: the two bars (a recorded `make eval` run), the LLM extraction (run before the demo, cached), the MP4.

## 4. The proof number

Claim: on 120 held-out incidents, the correct root cause is ranked first at least 2.5 times as often as by keyword search over the same corpus, and 100 percent of written claims carry a source span.

- Comparison, same corpus and same information budget of 3 results: baseline is BM25 over the thread and ticket text, scored a hit if the true cause appears in its 3 incidents; ours returns 3 ranked candidate causes, scored a hit if the true cause is in the list.
- Data: generator seed 7, eval split, causes never shown to the retriever; 30 extra storm and overlap cases reported separately.
- Target and win bar: top-1 0.60, top-3 0.88, baseline top-1 0.23, baseline top-3 0.50; so top-1 at least 2.5 times baseline and top-3 at least 0.85, with an ablation that removes graph edges costing at least 8 points. If it costs less than 5 points, the graph is decoration and the README says so.
- Integrity: 0 unsupported claims out of at least 200, checked by a script that resolves each citation to a span and re-checks the named entity.
- Not trivially easy: measure the baseline first, before any graph work, on the same split. If keyword top-3 is already above 0.75, harden the split (drop 20 percent of alarms, raise the overlap rate) or report a negative result. Add a shuffled-cause control: permuting causes across incidents must collapse the score to baseline.
- Reference: the arXiv alarm paper reports top-1 0.650 for a one-line rule on similar synthetic alarm data, 0.600 for an LLM. Landing near 0.60 is credible; above 0.80, suspect leakage and rerun the shuffle.

## 5. System design

```
 synthetic NOC corpus, seed 7: threads + tickets + alarms (JSONL + ground truth)
        |
        +--> [5 eval] held-out hit@1, hit@3, ablation, shuffle -> the two bars
        |
        v  [1 extractor]  text -> claims with span ids (cached LLM, regex fallback)
        v  [2 graph]      claims -> nodes and edges, 12 cause codes, SQLite
        v  [3 retrieve]   BM25 (FTS5) + MiniLM ONNX rerank over incident nodes
        v  [4 answer]     symptom -> incident -> cause -> fix, template assembly
        |                 an edge without a span id is not rendered
        v  FastAPI 127.0.0.1:8000 JSON -> React + SVG graph -> citation panel
```

- Corpus generator: config and seed in; the open telecom pack expands a real Topology Zoo backbone into sites, cards and links, and our thread synthesiser adds chat; JSONL out. Real generator, synthetic text.
- Extractor: messages in; Gemini with a strict schema, cached, regex fallback; claims with span ids out.
- Graph: claims in; entity resolution plus a 12-code cause vocabulary; SQLite out. Real.
- Retriever: alarm text in; BM25 plus 384-d embedding rerank; ranked incidents out. Local, no service.
- Answerer: incidents in; path walk plus templates; a cause card whose every clause is an edge. Deterministic, so it cannot invent a cause.
- Eval: ground truth in; hit@1, hit@3, ablation, shuffle; a table out. Real.
- Mocked: the live network, the people (fictional staff), the chat product.

## 6. Data strategy

(a) Opened and verified:
- https://github.com/samyama-ai/telecom-synthetic-data-generator (read via its raw README, Apache-2.0): a seeded generator for telecom NOC data. Real Topology Zoo backbone (CC BY 4.0), synthetic sites, cards and ports; faults of card, device, port, crash, config change, fibre cut and site power loss; alarms emitted from network state on the resource that would report them; noise as missing alarms, flapping, duplicates and per-device clock skew; history and eval splits with ground truth and resolution notes. `uv run sdg generate` takes about 2 s and `validate` writes realism.json. 99.5 percent synthetic on the GÉANT 2012 backbone.
- https://arxiv.org/abs/2610.30004: the paper behind it, 21 Oct 2026. States that operator logs are confidential and that published work shares causal graphs between alarm types, not per-incident causes. Supplies the baseline numbers we check ourselves against.
- https://huggingface.co/datasets/SamalaSharan/TelecomTS/blob/main/README.md (MIT): real 5G testbed observability, 32k samples, 1M+ observations, KPI names, natural language descriptions and troubleshooting tickets. Not our incident corpus; the source of realistic KPI and ticket wording.
- https://elisa.fi/kuuluvuus/ and https://elisa.fi/verkkoapuri/: Elisa's public coverage map and fault map. No cell ids or site names published, so there is nothing to seed from and nothing to infer from. Do not scrape. Company context only from https://elisa.fi/, https://elisa.fi/operaattoreille/ and https://yrityksille.elisa.fi/ideat/elisa-rakentaa-tieta-6g-aikaan-tekoalyohjatulla-verkolla. Internet Topology Zoo is to verify: its site timed out from this machine, but the generator vendors the topologies, so we do not need it.

(b) Synthetic corpus: the open pack plus a thread synthesiser we write. Realism comes from real fault classes and real alarm emission order; standard vocabulary (TMF642, X.733, RFC 8632 severity, NORIA-O causes) with unknown terms failing the run; noise that real NOCs have; and Finnish ops habits, code-switched English, site codes like TKU-KUP-3, shift handover, failed attempts. Two checks before we trust it: 30 of our messages and 30 real TelecomTS tickets, shown blind to 3 team members, target at most 70 percent correct identification (an obviously generated corpus is too easy); and a keyword baseline that is not obviously dumb (section 4).

(c) Ask the company, with arrival deadlines: 3 to 5 redacted real incident threads by Saturday 09:30, vocabulary only; their alarm type and cause code list by 09:30; written confirmation that a synthetic demo with a banner is acceptable, by 09:30. Nothing arriving after Saturday 12:00 can change the corpus, because measurement and recording need the remaining hours.

## 7. Build plan to freeze

Clock times from Friday 19:30. Five people: corpus and eval, backend, UI, demo and video, and a floater who owns the baseline.

| Mark | Hours | Done when |
| --- | --- | --- |
| M0 | +0 to +3 (22:30) | `make demo` serves; 300 history incidents from seed 7; graph renders; the keyword baseline prints top-1 and top-3 on 120 eval incidents. |
| M1 | +3 to +8 (03:30) | The 90 second path runs end to end on 5 fixed queries: alarm in, 3 incidents, 2 causes with counts, citations open. |
| M2 | +9 to +16 (09:30 to 16:30) | `make eval` prints ours, baseline, ablation and shuffle; the two bars render; the integrity script passes. |
| M3 | +16 to +25 (16:30 to 20:30) | Video recorded, README with reproduction steps, `make demo` on a clean clone, licence and data statement in place. |

Night: hard stop 04:00, back 09:30, one person on call for corpus regeneration. Cuts: at +8, if a citation will not open, drop the animation, never the citation. At +11, if the benchmark is not running, cut to 20 incidents and label the number small-n. At +16, freeze features. At +20, no code changes, only video and README. Cut first: the graph layout animation, the second query set, the Finnish sample text. The ablation is not cut.

## 8. Default stack and what we cut

- Python 3.12 + uv; FastAPI on 127.0.0.1:8000, JSON only.
- React + Vite + Tailwind; graph in plain SVG with a 60 line force layout and a fixed seed, no cytoscape.
- SQLite with FTS5 for BM25; tables for nodes, edges, spans and incidents. No graph database: at 5k edges SQL is enough.
- Embeddings: all-MiniLM-L6-v2 int8 ONNX, fetched once by `make setup`, cached in `.cache/` (gitignored). If it fails, BM25 alone is the baseline and the demo still runs.
- LLM: Gemini at corpus build time only, strict schema, every response cached in `data/cache/`. Zero LLM calls at demo time, so no network and no hallucination.
- `make demo` starts the backend and a built front end; `make eval` prints the table; `make data` regenerates the corpus from the seed. Deliverable: the repo README plus a 2 minute MP4.

Not building: Teams, Slack or ServiceNow connectors, auth, multi-user, any deploy, a graph database, fine-tuning, agentic actions on the network, a Finnish UI, real customer data, streaming answers, mobile layout, a second challenge.

## 9. Risks and kill criteria

Ranked, one mitigation each:
1. The vote. A text tool loses pairwise to anything that moves. Mitigation: 21 to 3 to 1 in four seconds, two bars, one fixed 95 second run.
2. A corpus that is too easy, so the proof is theatre. Mitigation: the floater builds the keyword baseline first, before any graph work.
3. Wrong extraction, confidently presented. Mitigation: no span, no render; precision over recall.
4. Wifi and time. Mitigation: everything cached, `make demo` offline, MP4 recorded Saturday, the hour marks above.
5. Relevance: they want autonomy, we deliver explanation. Mitigation: emit a cause record in TMF642 shape and show an agent consuming it.
6. Real employee data arriving late. Mitigation: it never enters the repo; vocabulary notes only, then a redaction pass on synthetic lookalike data.

Kill criteria: selection closes Friday 17:30 and the briefing is 18:50, so we cannot leave this challenge after hearing it. The only real switch is at 17:30: take Elisa only if the top three are gone. Inside the challenge, switch at the briefing if they say explanation is not scored, or that a citation-backed knowledge tool already runs: cut to the eval harness and the cause record, stop building UI. Hard hour: if the baseline number does not exist by +6 (01:30), the proof cannot happen and the plan drops to a demo without a claim.

## 10. Questions for the partner Q&A

Saturday 09:00 to 12:00. Ask what they will score, not what to build.
1. When you rank the top three, what separates first from second: the working output or the measurement behind it?
2. What does "more autonomous" mean in your scoring: fewer manual steps, or a better explanation for a human?
3. Which weighs more: a correct cause with a citation, or a faster answer without one?
4. What evidence would make a synthetic result credible to you?
5. Would a cause record in TMF642 shape be usable by your automation, or only inside your own tooling?
6. Where does the know-how that never reaches a ticket live in your NOC today?
7. Which past entry on this challenge came closest, and what did it miss?

## 11. How it scores: company vs participant vote

Company: workable, and the strongest part is the measured replay with an ablation, because it answers "does the graph earn its place" instead of asserting it. Relevance is good: Elisa already automates detection and repair, so the residue is exactly the know-how in chat, and a cause record in a standard shape is a plausible input to their next agent. Technical quality is honest for one night: open generator, pinned cause vocabulary, provenance on every edge, no LLM at demo time, a shuffled control. Privacy scores well: synthetic only, redaction shown, nothing real in the repo. Weakness: no Elisa data, so this is a method demo, not their network.

Vote: the hard gate, and where the challenge loses. A thousand builders compare pairs in 20 seconds, and ours asks them to read three sentences of telecom language before anything happens. Nothing physical moves, no camera, no map of Finland, no sound. The mitigations make it legible, not memorable. Expect a company top three at best, an unlikely finalist place, and a real chance of losing the pair to a robot arm from another challenge.

## 12. IP, NDA and data handling

- IP: the summary says the team owns what it builds and Elisa can use it in its business. No NDA is stated for Elisa; that is FORCIT. Our code gets MIT, the generated corpus CC BY 4.0 with the generator and Topology Zoo attributed.
- If an Elisa NDA appears on the day, sign only what covers evaluation, and keep restricted material in a gitignored `restricted/` directory deleted before submission.
- Employee chat is personal data. We do not receive it, copy it or show it. If it is shown to us, we take vocabulary notes and nothing else: no screenshots, no exports, no quotations.
- The demo handles privacy by construction: synthetic threads carry fake names, phone numbers and customer ids, and a redaction pass runs before indexing. That pass is on screen for 10 seconds.
- Repo and video: synthetic banner, fictional staff, no Elisa logo or system screenshots, no claim about their network. Data statement in the README, generator config and seed committed, full corpus regenerated by `make data`, no binaries, no real data, `.env.example` only. Company mentions stay factual and sourced.
- Public summary: one paragraph, synthetic data, method, measured numbers, and what would need proving on real data.
