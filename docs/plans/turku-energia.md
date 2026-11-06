# Turku Energia: Short-term energy forecasting under uncertainty
**Tier:** fallback. **Verdict:** pivot only. The best real-data story of the eight and the weakest vote story, so it earns a bid only if the earlier shortlist disappoints at the briefing and a Turku load series arrives on Friday night. Written Thu 5 Nov 2026 from the public summary only.

## 1. The 20 second story

A plant operator has a heat store, a boiler and tomorrow's prices. We show tomorrow's load as a band, not a line, and the band decides when the boiler runs. Drag the confidence band and the charge plan changes and the euro number changes with it. The uncertainty is the control, not the decoration.

## 2. What the company said, and what we infer

The summary's task sentence, verbatim: "Energy markets change rapidly as electricity production and demand shift. Explore how AI could improve short-term forecasts and help experts make informed decisions under uncertainty."

Verified today from https://www.turkuenergia.fi/en (page opened, not remembered): Turku Energia sells electricity contracts, district heating, cooling, solar panels and charging points, and runs electricity networks. One retail product is priced as a quarter-hourly market-price contract plus 0.42 c/kWh.

- Inference: the deliverable is a forecast plus a decision aid, not a forecasting library. "Help experts make informed decisions" is the half of the sentence they will score, and they already have a competent day-ahead forecast, so the differentiator is calibrated uncertainty and the decision on top, not a smaller MAE.
- Inference: "experts" are district heating operators and electricity portfolio managers working from a spreadsheet and experience, not data scientists.
- Inference: temperature drives heating load, so a heating-load demo that ignores weather will read as naive to them.
- Inference: their metering data is customer data. A demo that never touches customer-level rows is safer and scores better on the privacy criterion.
- Inference: a quarter-hourly retail product means hour-level price decisions already reach their customers, which makes the decision layer commercially real rather than academic.

Confirm at the Friday briefing, in this order, because each answer changes the plan:

1. Which single series do you want forecast: your network load, district heating load, district cooling, or the FI day-ahead price? At what horizon and resolution?
2. What do you use for it today, and what error does that have? May we see the current forecast so we compare rather than assert?
3. Can you hand us 2+ years of that series before midnight Friday, with units, timezone and known outages? File or API?
4. What decision follows the forecast, who makes it, and what does a wrong call cost in euros or MWh?
5. Which flexible assets do you dispatch (heat pumps, electric boilers, heat storage, cooling storage, CHP), with what limits and efficiencies, and may we use those numbers as declared assumptions?
6. Which constraint must never break: supply temperature, comfort floor, contract minimum, reserve obligation?
7. Who scores on Sunday, what would make you say "we could run this on Monday", and what may appear in a public repo and video: FI-wide aggregates only, or your series too? Any NDA?

## 3. The 90 second demo

1. `make demo`, then open http://127.0.0.1:8000: one page, no login, no network. Panel one, "Tomorrow, 24 h ahead, Finnish electricity load", a fan chart with the P10-P90 band, the P50 line, yesterday's actual in grey and a persistence line, with two MAE tiles above it, ours and persistence, read from `metrics.json` (illustrative until `make proof` runs).
2. Visible moment one: press "hide our model". The band collapses to the persistence envelope and visibly misses the evening peak. Press again. Two seconds, no explanation needed.
3. Panel two, "so what": a 2 MWh heat store and a 1 MW boiler, 24 hourly cells, each coloured by the published day-ahead price. Two plans side by side, fixed night schedule against ours, each with a euro total per MW of flexible load.
4. Visible moment two: drag the confidence slider from 80% to 50%. Four cells flip from charge to wait, the euro figure moves, and the risk line under the grid changes. At 95% the plan turns conservative and the euros fall. This is the moment a judge remembers.
5. Press "replay 12 held-out weeks": the backtest steps week by week, the euro counter climbs to the total, and a table fills with our plan, the fixed schedule, and the perfect-foresight ceiling.
6. Close on the ceiling line: "we capture N% of the value that perfect information would give". Named honestly as a ceiling, not a result.

Live: model inference, the planner, the slider, every number, computed on the laptop from a local parquet cache in under a second. Replay: the input series, which ends at the last download. Nothing in the demo path touches the network.

## 4. The proof number

Single claim: on 12 held-out weeks of real Finnish load and real day-ahead prices, a 24 h forecast with calibrated 80% intervals plus a band-aware charge plan beats a fixed night schedule by N euros per MW of flexible load per day, captures at least 60% of perfect-foresight value, and never breaks the heat floor. Every number comes from committed real data through one command, `make proof`, fixed seed, with the test window dates written into `metrics.json` and the README.

- Forecast: MAE and MAPE at 24 h ahead on a fixed test window. Baselines computed in the same script on the same rows: persistence (same 15-minute slot yesterday), weekly seasonal naive (same slot last week), and Fingrid's published day-ahead consumption forecast (dataset 165) printed as the professional reference we do not claim to beat.
- Win bar: at least 20% lower MAE than persistence, and MAE within 15% of Fingrid's 165 series. Both numbers printed together, always.
- Uncertainty: empirical coverage of the 80% interval between 0.75 and 0.85, pinball loss below a residual-quantile baseline, and mean interval width in MW printed so a 3x-too-wide band cannot pass. Coverage without width is cheating.
- Decision: euros per MW per day against the fixed 23:00-06:00 schedule, at the same comfort floor. Hours below the floor must be zero. Report the percentage of perfect-foresight value captured, since that is the only honest upper bound.

A win rather than a toy: at least 20% MAE gain over persistence, coverage inside 0.75 to 0.85, at least 10 euros per MW per day over the fixed schedule, at least 60% of perfect foresight, zero floor violations. If the MAE gain, the coverage or the euros miss, the README is rewritten to the number that was measured, not the other way round.

## 5. System design

```
  BEFORE THE EVENT, ONCE                    AT DEMO TIME, OFFLINE
  Fingrid API 124 / 201 / 165 --\
  FMI WFS t2m, Turku ----------> scripts/download.py
  Nord Pool or ENTSO-E prices -/         |
                                         v
                                data/raw/*.csv  (gitignored, fetched once tonight)
                                         |
                          scripts/build_dataset.py -> data/processed/load.parquet
                                         |
                     +-------------------+-------------------+
                     v                                       v
            model/forecast.py                       model/plan.py
      features as of T -> P10/P50/P90         prices + band + store
      plus persistence baselines              -> 24 hourly decisions
                     |                                       |
                     +------------> evaluation/metrics.json <+
                                         |
                                         v
                       api/main.py -> JSON -> web/ React + Vite + Tailwind
                       fan chart, plan grid, confidence slider, backtest replay
```

- `download.py`: three HTTP endpoints in, raw CSV out. Never runs during the demo.
- `build_dataset.py`: raw CSV in, one parquet out with load, temperature, price and calendar columns, resampled to 15 minutes, plus `gaps.csv`.
- `forecast.py`: features up to the issue time in, per-horizon quantiles out (LightGBM quantile objective), with the naive baselines in the same module so they cannot drift apart.
- `plan.py`: quantiles, prices and asset limits in, 24 charge or wait decisions and a euro total out. Greedy hour by hour with a store constraint, not a solver.
- `api/main.py`: query parameters in, JSON out, reading the parquet and running the model in process. No auth, no CORS to anyone but localhost.
- `web/`: that JSON in, three panels out. The slider sends one request; the plan recomputes server-side in under 200 ms.

Real: every series, every price, the model, the planner. Mocked and declared in the README: the flexible asset (2 MWh store, 1 MW boiler, 92% round-trip efficiency), the comfort floor, and the operator who clicks. No company data unless Friday delivers it.

## 6. Data strategy

(a) Open data, verified by opening it today.

- Fingrid open data API, https://data.fingrid.fi/instructions. Free, registration needs only a working email, key goes in the `x-api-key` header, 10,000 queries per day and one query every 2 seconds. Endpoint confirmed in the technical documentation at https://developer-data.fingrid.fi/api-details: `GET https://data.fingrid.fi/api/datasets/{datasetId}/data?startTime=&endTime=&format=csv&pageSize=20000`, page size capped at 20000. Without a key the endpoint answers 401, reproduced today.
- Dataset 124, Electricity consumption in Finland, 15 minutes, MWh/h, valid from 1.1.2014, licence Creative Commons Attribution: https://data.fingrid.fi/en/datasets/124. This is the main target.
- Dataset 165, Electricity consumption forecast, published the previous day at 12:00 EET for a 24 h horizon, 15 minutes, MW, Creative Commons Attribution: https://data.fingrid.fi/en/datasets/165. The professional baseline, not our product. Dataset 201, Cogeneration of district heating, 3 minutes, MW, same licence: https://data.fingrid.fi/en/datasets/201, the only district-heating-adjacent series available without the company.
- FMI open data, https://en.ilmatieteenlaitos.fi/open-data-manual-time-series-data. WFS at https://opendata.fmi.fi/wfs, no key, stored query `fmi::observations::weather::timevaluepair` with `parameters=t2m`, `place=turku`; Creative Commons, 20,000 requests per day. Run today: HTTP 200 with hourly temperatures for station Turku Artukainen (fmisid 100949). The manual also documents a HARMONIE point forecast stored query, which is the correct future-temperature input for the live path.
- Prices: ENTSO-E Transparency Platform, https://transparency.entsoe.eu/, opened today, free and open to all with free registration, publishes day-ahead prices and load. Programmatic access uses a security token, request procedure to verify. Alternative: Nord Pool Data Portal, https://data.nordpoolgroup.com/auction/day-ahead/prices, opened today and readable without login, showing 15-minute delivery periods in EUR/MWh with FI in the area list; whether the Excel export works logged out is to verify.

Pre-event download, run tonight, about 2 minutes:

```
export FINGRID_API_KEY=...        # sign up at https://data.fingrid.fi, Products -> Open Data starter
for id in 124 165 201; do for y in 2022 2023 2024 2025 2026; do
  curl -sS -H "x-api-key: $FINGRID_API_KEY" \
    "https://data.fingrid.fi/api/datasets/${id}/data?startTime=${y}-01-01T00:00:00Z&endTime=${y}-12-31T23:59:59Z&format=csv&pageSize=20000" \
    -o "data/raw/fingrid_${id}_${y}.csv"
done; done
curl -sS "https://opendata.fmi.fi/wfs?service=WFS&version=2.0.0&request=getFeature&storedquery_id=fmi::observations::weather::timevaluepair&place=turku&parameters=t2m&starttime=2022-01-01T00:00:00Z&endtime=2026-11-05T00:00:00Z&timestep=60" -o data/raw/fmi_turku_t2m.xml
```

One commit, tonight, message "pre-event data download, Thursday 5 Nov", so both the date and the pre-existing status are provable. Then never write to `data/raw` again; the parquet is regenerated from it by `make data`.

(b) Synthetic fallback, if no key exists by Friday 20:30. `scripts/synth.py` generates a series with the structure that makes it usable rather than decorative: a double daily peak (07:00-09:00, 17:00-20:00), a weekday effect of about 8% over weekend, a piecewise-linear degree-day response with a breakpoint near 15 C and a steeper slope below -5 C, an AR(1) daily weather term so cold spells last days rather than hours, Finnish holidays and a midsummer dip, three injected anomalies, and positive-only noise whose variance grows with load so the intervals are not constants. Every chart carrying synthetic data gets a badge, and the README states the switch. Synthetic data never appears in the headline metric.

(c) From the company, and when it must arrive: one hourly or 15-minute series, 2+ years, with units, timezone and outages; the asset parameters for the decision (store size, boiler power, efficiency, comfort floor); and one sentence on the decision they actually make. Drop-dead arrival Saturday 02:00. After that it cannot be validated, so it stays out of the headline number and can appear only as a footnote.

## 7. Build plan to freeze

Hour 0 is Friday 19:30.

- M0, scaffold, 0 to 1.5 h, hard stop 21:00. Skeleton, committed parquet, `make demo` serving one page. Done when a clean clone plus `make demo` shows one real number on screen, offline.
- M1, demo loop, 1.5 to 6 h, hard stop 01:30. Fan chart on real history, three baselines printed, static plan grid with a euro number. Done when the forecast, the baselines and the plan are all on one page from committed data with wifi off. This is the 6 hour demo.
- M2, the proof, 6 to 13.5 h, hard stop Saturday 09:00. Twelve-week backtest, quantile model with calibration, planner with the floor constraint, `make proof` writing `metrics.json`, slider wired. Done when the README number equals `metrics.json` and the slider moves both the plan and the euro number.
- M3, video and README, 13.5 to 26 h, freeze 22:00. Two minute MP4 recorded from the offline app, README with setup, provenance, mocked items, licence and the honest metric table. Done when the MP4 plays from a fresh download with the network off and every number in it matches `metrics.json`.

Cut first, in this order: the price forecast at hour 3 (day-ahead prices for tomorrow are published before tomorrow, so forecasting them adds little); the district heating second target at hour 8 unless company data arrived; the second asset type at hour 10; the slider at hour 14, replaced by three preset buttons if it is not smooth; the replay animation at hour 18; district cooling never started. If hour 6 arrives with no page and no euro number, drop every feature and ship the fan chart plus one plan.

## 8. Default stack and what we cut

House stack, adjusted to this problem:

- Python 3.12 with uv and one lockfile. pandas and numpy for 15-minute series, LightGBM with the quantile objective for the forecast, scikit-learn for the baselines and scaling. No statsmodels, no torch, no notebook in the demo path.
- FastAPI on 127.0.0.1:8000, JSON only, four endpoints: `/forecast`, `/plan`, `/backtest`, `/metrics`, reading parquet in `data/processed` (one file, about 2 MB) and running the model in process. SQLite only if the backtest needed a table, which it does not.
- React, Vite and Tailwind, one page, three panels. Recharts for the fan chart (two Areas for the band, one Line for the median). Plain SVG for the 24-cell plan grid, because 24 rectangles do not need a library.
- `make demo` runs `uv sync`, builds data if missing, starts uvicorn and opens the browser. `make proof` runs the backtest and writes `metrics.json`. No Docker, no services, no deploy.
- The submitted demo is a recorded MP4 under two minutes plus the README. The repo is the evidence; the video is the argument.

Deliberately not built: a price trading bot (not survivable in 26 hours and not what they asked), any cloud deploy, a live Fingrid poller during the demo, authentication, a database service, a district heating network model, a mobile layout, a chat panel over the chart (it would attract every question and defend nothing), multi-target forecasting, and any optimisation harder than greedy dispatch with a store constraint.

## 9. Risks and kill criteria

1. Losing to a naive baseline. Mitigation: all baselines run in the same script on the same rows from hour 2, printed next to the model every run, and the README quotes a delta against persistence rather than a stand-alone MAPE.
2. Wifi or the venue laptop. Mitigation: nothing in the demo path touches the network. Record the MP4 the moment M1 lands, re-record after M2, and test with the wifi off before showing anyone.
3. A chart with no decision, which is this challenge's natural failure mode. Mitigation: the euro number and the plan grid are in M1, not M2. A page with no euro number is not a demo.
4. Gaps and revisions in real data. Mitigation: `gaps.csv`, interpolation of at most two steps, and any week with more than 1% missing rows excluded from the metric window and counted in the report.
5. Leakage, using information that did not exist at the forecast issue time. Mitigation: one `features.py` with an explicit `as_of`, an assert that every input timestamp is at or before it, and a test that moves `as_of` back an hour and confirms the metrics get worse, not better.
6. The company series arrives late or unusable (Excel, thermal units, local time across DST, 3 minute sampling). Mitigation: a 45 minute adapter budget and the Saturday 02:00 drop-dead.
7. Five people on one thread of work. Mitigation: two on data and model pairing on the same file, one on API and planner, one on the front end, one on video, README and the record of what is mocked.

Ranked kill criteria, each with the hour it is checked:

- Friday 19:45, from the briefing: if the brief is a price-forecasting product only, or they expect a market-data tool with no physical driver, switch challenge. A price chart gives no visible physical story and no decision we can defend in one night.
- Friday 21:00, technical: no Fingrid key, no parquet, no price series. Build on the synthetic generator; if the ENTSO-E token is still missing, run the decision on Fingrid's published imbalance price from the key we already have, declared as a substitute. If 01:30 arrives with no real series at all, this challenge has lost its only advantage over the other three.
- Saturday 09:00, M2 hard stop: if MAE is not 10% below persistence after the first model, stop modelling, keep persistence as the demonstrated forecast and move the whole claim to the decision layer.
- Saturday 12:00: if the plan loses money against the fixed schedule, report it as a negative result and pivot the story to "the band stops you losing money", which still contains a decision. Do not hide it.
- Saturday 18:00: if the MP4 does not exist, stop all work and record it. After 18:00 the video is the only artefact that still matters.

## 10. Questions for the partner Q&A

Saturday 09:00 to 12:00. Ask what they will score, not what to build.

1. When you compare two submissions on Sunday, what is the first thing you look at, and what makes you stop reading?
2. Is a forecast that matches yours but adds calibrated intervals and a decision worth more to you than one that is 1% more accurate, or less?
3. Which error metric do your planners use for this series, and what value do they call good?
4. What decision is made from that forecast today, by whom, and how long does it take?
5. Which flexible asset is your largest and most price-sensitive, and what stops you moving it every hour?
6. If we build on FI-wide public load instead of your Turku series, is that still relevant, or does it look like the wrong product?
7. What would be irresponsible in your eyes: showing customer-level data, publishing your series, or trusting a wide band?
8. Would you rather see one target done honestly, or three done roughly?

## 11. How it scores: company vs participant vote

Company gate. Strong on data handling: every series is real, licensed and attributed, and no customer-level row is touched, which is an easy and credible privacy answer. Strong on understanding if the demo names the physical chain (temperature to heating load to fuel or power cost) and respects a hard constraint rather than optimising freely. Weakest on "improves your forecast": their own day-ahead series is the professional baseline, so if we cannot beat dataset 165 the honest claim shrinks to calibration plus the decision. The fix is to claim what the metrics show and to make feasibility obvious: LightGBM on about 140k rows retrains in about a minute on a laptop, and we will time it rather than assume it.

Participant vote. This is the weak gate, and the weakness is structural, not fixable by polish: a forecasting artefact is a chart, and two lines 8% apart mean nothing to a builder who has been awake for 40 hours. Traficom can show a jammer and a detector, Valmet can show a machine. Our only counter is to make the first ten seconds show a decision whose number moves when the band moves. If the video opens on the fan chart instead of the plan grid, this challenge loses the vote however good the model is. The model is for the company; the slider is for the vote.

## 12. IP, NDA and data handling

- IP: the Thursday summary states "Your team owns what you build. Turku Energia can use it in its business." No NDA is mentioned for this challenge, unlike FORCIT Group. Confirm at the briefing that nothing about their data overrides that.
- Their data, if it arrives: not ours to publish until they say so in writing. Default it to restricted: `data/company/` in `.gitignore`, never in the repo, never in the MP4, never in the deck, and shown only as aggregates or as a chart they approve. Ask the question directly on Friday: may this series appear in the video?
- Open data licences: Fingrid states Creative Commons Attribution; FMI states Creative Commons, exact variant to verify; ENTSO-E and Nord Pool redistribution terms to verify before committing raw files. Attribution in `data/SOURCES.md`, one line per series with URL, retrieval date and licence, mirrored in the README.
- Pre-existing work: tonight's download, the download script and any scaffolding predate Friday 19:30 and are declared as pre-existing in the README and on the submission form. Committing tonight is what makes that claim checkable.
- Repo, video, public-safe summary: the repo opens while logged out, holds no key (`.env.example` with the variable name only), and the video shows FI-wide public data or synthetic data unless the company agrees otherwise. The submission text names each source and states plainly what is assumed rather than measured.
